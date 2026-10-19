from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .browser import BrowserScanner, Capture, infer_scenarios
from .compare import compare
from .images import image_difference, ocr_context
from .model import Change, Result, Scenario, Site, json_bytes, local_day, now_iso, slug
from .report import install_outputs, write_outputs
from .state import StateStore


@dataclass
class RunOptions:
    day: str = ""
    concurrency: int = 3
    domain_timeout: float = 150
    budget_seconds: float = 1800
    max_scenarios: int = 30
    retries: int = 1
    browser_executable: str | None = None
    navigation_timeout: int = 25000
    settle_ms: int = 500
    retention_days: int = 180
    ocr: bool = True


async def run_scan(sites: list[Site], store: StateStore, output: Path, options: RunOptions) -> dict:
    started = time.monotonic()
    day = options.day or local_day()
    run_id = now_iso().replace(":", "").replace("+", "-") + "-" + uuid.uuid4().hex[:8]
    metadata = {"run_id": run_id, "day": day, "started_at": now_iso(), "domains": len(sites)}
    state = store.begin(day, options.retention_days)
    results: list[Result] = []
    semaphore = asyncio.Semaphore(options.concurrency)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scan-", dir=output) as temporary:
        staging = Path(temporary)
        async with BrowserScanner(options.browser_executable, options.navigation_timeout, options.settle_ms) as scanner:
            async def capture_retry(site, kind, url, scenario, dest):
                for attempt in range(options.retries + 1):
                    try:
                        return await scanner.capture(site, kind, url, scenario, dest)
                    except Exception as exc:
                        # Permanent denials and invalid content do not improve with retries.
                        if attempt == options.retries or isinstance(exc, ValueError):
                            raise
                        await asyncio.sleep(min(2 ** attempt, 4))

            async def record(capture: Capture):
                snapshot = capture.snapshot
                before = store.previous(state, snapshot.key)
                snapshot.image = store.image(capture.screenshot)
                changes, retained = compare(before, snapshot)
                folder = staging / day / slug(snapshot.domain) / snapshot.page / slug(snapshot.scenario)
                folder.mkdir(parents=True, exist_ok=True)
                if snapshot.scenario == "podstawowy":
                    (folder / "kontrolki.json").write_bytes(json_bytes({
                        "title": snapshot.title, "url": snapshot.url,
                        "controls": capture.payload.get("controls", []),
                        "headings": capture.payload.get("headings", []),
                        "warnings": snapshot.warnings,
                    }))
                evidence = {}
                after_path = folder / "po.png"
                before_path = folder / "przed.png"
                difference_path = folder / "roznice.png"
                visual = None
                if before and before.renderer == snapshot.renderer:
                    visual = await asyncio.to_thread(image_difference, store.root / before.image, capture.screenshot, difference_path)
                elif before:
                    changes.append(Change("review", "obraz", "Zmiana wersji przeglądarki lub sposobu renderowania", before.renderer, snapshot.renderer, before.observed_at, snapshot.observed_at, snapshot.url, snapshot.scenario, note="Porównanie wizualne pominięto; porównanie danych zachowano."))
                if before and visual and visual.changed:
                    text, note = "", "Zmiana obrazu wymaga oceny; może wynikać również ze zmiany układu."
                    if options.ocr:
                        text, ocr_note = await asyncio.to_thread(ocr_context, capture.screenshot, folder / "fragment-ocr.png", visual.bbox)
                        note += " " + ocr_note
                    changes.append(Change("review", "obraz", "Zmiana wyglądu lub treści graficznej", None, text or "Patrz obrazy przed/po", before.observed_at, snapshot.observed_at, snapshot.url, snapshot.scenario, note=note))
                if changes or before is None:
                    shutil.copy2(capture.screenshot, after_path)
                    evidence["po"] = after_path.relative_to(staging).as_posix()
                    if before:
                        shutil.copy2(store.root / before.image, before_path)
                        evidence["przed"] = before_path.relative_to(staging).as_posix()
                    if difference_path.exists():
                        evidence["roznice"] = difference_path.relative_to(staging).as_posix()
                    if (folder / "fragment-ocr.png").exists():
                        evidence["fragment_ocr"] = (folder / "fragment-ocr.png").relative_to(staging).as_posix()
                elif difference_path.exists():
                    difference_path.unlink()
                for change in changes:
                    change.evidence = evidence
                status = "baseline" if before is None else "review" if changes and all(c.kind == "review" for c in changes) else "changed" if changes else "unchanged"
                if snapshot.warnings:
                    status = "partial"
                results.append(Result(snapshot.domain, snapshot.page, snapshot.scenario, status, snapshot.url, changes, snapshot.warnings, observed_at=snapshot.observed_at, evidence=evidence))
                if snapshot.quality == "ok":
                    state["snapshots"][snapshot.key] = retained.to_dict()

            async def interactions(site: Site, kind: str, url: str, base: Capture, work: Path):
                explicit = [s for s in site.scenarios if s.page == kind]
                inferred, warnings = infer_scenarios(base.payload, kind, options.max_scenarios)
                queue = explicit + inferred
                seen = set()
                action_seen = {json.dumps(s.actions[-1], sort_keys=True) for s in queue if s.actions}
                completed = set()
                count = 0
                while queue:
                    scenario = queue.pop(0)
                    signature = str(scenario.actions)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    if count >= options.max_scenarios:
                        warnings.append("Osiągnięto limit scenariuszy; pozostałe interakcje nie zostały sprawdzone.")
                        break
                    count += 1
                    try:
                        captured = await capture_retry(site, kind, url, scenario, work / f"{kind}-{slug(scenario.id)}.png")
                        await record(captured)
                        completed.add(scenario.id)
                        nested, nested_warnings = infer_scenarios(captured.payload, kind, options.max_scenarios)
                        warnings.extend(nested_warnings)
                        for child in nested:
                            action_key = json.dumps(child.actions[-1], sort_keys=True)
                            if action_key in action_seen:
                                continue
                            action_seen.add(action_key)
                            actions = scenario.actions + child.actions
                            identity = "nested-" + hashlib.sha256(json.dumps(actions, sort_keys=True).encode()).hexdigest()[:12]
                            queue.append(Scenario(identity, scenario.label + " / " + child.label, actions, page=kind))
                    except Exception as exc:
                        results.append(Result(site.domain, kind, scenario.id, "error", url, error=str(exc).splitlines()[0][:600]))
                prior = {key.split("/", 2)[-1] for key in state["anchor"] if key.startswith(f"{site.domain}/{kind}/") and not key.endswith("/podstawowy")}
                for missing in sorted(prior - completed):
                    warnings.append(f"Poprzedni scenariusz nie został poprawnie odtworzony: {missing}; nie potwierdzono usunięcia funkcji.")
                if warnings:
                    results.append(Result(site.domain, kind, "pokrycie-interakcji", "partial", url, warnings=list(dict.fromkeys(warnings))))

            async def process_site(site: Site):
                work = staging / ".work" / site.domain
                work.mkdir(parents=True, exist_ok=True)
                try:
                    home = await capture_retry(site, "glowna", site.home_url, Scenario("podstawowy", "Strona główna"), work / "home.png")
                    await record(home)
                except Exception as exc:
                    results.append(Result(site.domain, "glowna", "podstawowy", "error", site.home_url, error=str(exc).splitlines()[0][:600]))
                    home = None
                selection = state["selections"].get(site.domain)
                project = None
                if site.project_url:
                    if selection and selection["url"] != site.project_url:
                        raise ValueError("Konfiguracja zmienia zapamiętany projekt. Wymagana jawna migracja punktu odniesienia.")
                    selection = selection or {"url": site.project_url, "name": site.project_name or site.project_url, "basis": site.selection.get("basis", "Jawny wybór w konfiguracji"), "source": site.selection.get("source", site.home_url), "selected_at": now_iso()}
                if not selection and home:
                    selection, project, selection_warnings = await scanner.discover_project(site, home, work)
                    if selection_warnings:
                        results.append(Result(site.domain, "projekt", "wybor", "partial", site.home_url, warnings=selection_warnings))
                if selection:
                    try:
                        project = project or await capture_retry(site, "projekt", selection["url"], Scenario("podstawowy", "Wariant podstawowy"), work / "projekt.png")
                        # Selection is frozen only after a product page was successfully validated.
                        state["selections"][site.domain] = selection
                        await record(project)
                    except Exception as exc:
                        results.append(Result(site.domain, "projekt", "podstawowy", "error", selection["url"], error=str(exc).splitlines()[0][:600]))
                        project = None
                else:
                    results.append(Result(site.domain, "projekt", "podstawowy", "unavailable", site.home_url, error="Nie ustalono karty projektu. Nie zastąpiono jej losowym adresem."))
                if home:
                    await interactions(site, "glowna", site.home_url, home, work)
                if project and selection:
                    await interactions(site, "projekt", selection["url"], project, work)
                if site.inspection != "verified":
                    results.append(Result(site.domain, "zakres", "inspekcja-adaptera", "partial", site.home_url, warnings=["Adapter nie ma potwierdzonej inspekcji tej domeny. Automatyczny odczyt nie oznacza pełnego pokrycia wszystkich interakcji."]))

            async def bounded(site: Site):
                async with semaphore:
                    remaining = options.budget_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        results.append(Result(site.domain, "zakres", "limit-czasu", "error", site.home_url, error="Wyczerpano czas skanu; domena niesprawdzona."))
                        return
                    try:
                        async with asyncio.timeout(min(options.domain_timeout, remaining)):
                            await process_site(site)
                    except TimeoutError:
                        results.append(Result(site.domain, "zakres", "limit-czasu", "partial", site.home_url, error="Przekroczono czas domeny; pozostały zakres nie został sprawdzony."))
                    except Exception as exc:
                        results.append(Result(site.domain, "zakres", "blad", "error", site.home_url, error=str(exc).splitlines()[0][:600]))
                    print(f"Sprawdzono {site.domain}", flush=True)

            await asyncio.gather(*(bounded(site) for site in sites))
        results.sort(key=lambda result: (result.domain, result.page, result.scenario))
        metadata.update(finished_at=now_iso(), elapsed_seconds=round(time.monotonic() - started, 3), renderer=scanner.renderer)
        metadata["snapshot_bytes"] = sum((store.root / image).stat().st_size for image in {s["image"] for s in state["snapshots"].values()})
        write_outputs(staging, day, results, metadata, state["selections"], [site.domain for site in sites])
        install_outputs(staging, output, day, slug(run_id))
        store.commit(state)
        store.collect(state)
    # Delete only date directories accompanied by this tool's manifest.
    cutoff = (date.fromisoformat(day) - timedelta(days=options.retention_days)).isoformat()
    for directory in output.iterdir():
        if not directory.is_dir() or not (directory / "manifest.json").is_file():
            continue
        try:
            parsed = date.fromisoformat(directory.name).isoformat()
        except ValueError:
            continue
        if parsed <= cutoff:
            shutil.rmtree(directory)
            (output / f"{parsed}.txt").unlink(missing_ok=True)
    return {"metadata": metadata, "results": results, "state": copy.deepcopy(state)}
