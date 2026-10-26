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
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.async_api import Error as BrowserError
from playwright.async_api import TimeoutError as BrowserTimeout

from .browser import (
    BrowserScanner,
    Capture,
    TransientFetchError,
    UnusableControl,
    adapter_signature,
    infer_scenarios,
)
from .commercial import verify_offers
from .communication import measure
from .compare import compare
from .extract import is_listing_title, page_identity
from .images import image_difference, ocr_context, visual_evidence, visual_text
from .model import Change, Result, Scenario, Site, Snapshot, digest, json_bytes, local_day, now_iso, slug
from .observations import visual_description
from .offers import primary_offer
from .report import install_outputs, resume_data, write_outputs
from .state import StateStore


@dataclass
class RunOptions:
    day: str = ""
    concurrency: int = 3
    domain_timeout: float = 150
    budget_seconds: float = 3600
    max_scenarios: int = 30
    retries: int = 1
    browser_executable: str | None = None
    navigation_timeout: int = 25000
    settle_ms: int = 500
    retention_days: int = 180
    ocr: bool = True
    resume: bool = False
    repair_domains: list[str] | None = None


def preserve_same_day_reads(results: list[Result], previous: list[Result], state: dict, sites: list[Site], output: Path, staging: Path, day: str) -> list[dict]:
    """A failed retry does not erase a verified observation from this day."""
    prior = {(r.domain, r.page): r for r in previous if r.scenario == "podstawowy"}
    configured = {s.domain: s for s in sites}
    retained = []
    for failed in list(results):
        if failed.scenario != "podstawowy" or not failed.error or failed.observed_at:
            continue
        old = prior.get((failed.domain, failed.page))
        if not old or not old.observed_at or old.error or old.data_quality not in {"ok", "partial", "visual"}:
            continue
        if local_day(datetime.fromisoformat(old.observed_at)) != day:
            continue
        snapshot = state["snapshots"].get(f"{old.domain}/{old.page}/podstawowy", {})
        if old.offer.get("field_key") in configured[old.domain].unreliable_price_keys:
            continue
        folder = Path(day) / slug(old.domain) / old.page / "podstawowy"
        if not (output / folder).is_dir():
            continue
        if old.data_quality == "ok":
            if snapshot.get("observed_at") != old.observed_at:
                continue
        else:
            # Keep a documented partial observation for display, never in the
            # trusted baseline. Its quality and original date remain intact.
            source = output / folder / "odczyt.json"
            try:
                manifest = json.loads((output / day / "manifest.json").read_text())
                record = manifest["files"][(folder / "odczyt.json").as_posix()]
                archived = json.loads(source.read_text())
                if manifest.get("owner") != "pracownie-monitor:v1" or digest(source) != record["sha256"]:
                    continue
                if any(archived.get(k) != v for k, v in {"domain": old.domain, "page": old.page, "scenario": "podstawowy", "observed_at": old.observed_at, "quality": old.data_quality}.items()):
                    continue
            except (OSError, KeyError, ValueError):
                continue
        shutil.copytree(output / folder, staging / folder, dirs_exist_ok=True)
        failed.scenario = "ponowienie-podstawowego"
        failed.scenario_label = "Nieudane ponowienie odczytu podstawowego"
        results.append(copy.deepcopy(old))
        retained.append({"domain": old.domain, "page": old.page, "observed_at": old.observed_at, "quality": old.data_quality, "retry_error": failed.error})
    return retained


async def run_scan(sites: list[Site], store: StateStore, output: Path, options: RunOptions) -> dict:
    started = time.monotonic()
    day = options.day or local_day()
    run_id = now_iso().replace(":", "").replace("+", "-") + "-" + uuid.uuid4().hex[:8]
    metadata = {"run_id": run_id, "day": day, "started_at": now_iso(), "domains": len(sites)}
    state = store.begin(day, options.retention_days)
    results: list[Result] = []
    pending: dict[str, tuple] = {}
    base_elapsed: dict[str, float] = {}
    sites_by_domain = {site.domain: site for site in sites}
    reused, previous_metadata = set(), {}
    previous_results: list[Result] = []
    if options.resume:
        reused, results, previous_metadata = resume_data(output, day, sites, store.read(), options.repair_domains)
        if previous_metadata:
            for raw in json.loads((output / day / "zmiany.json").read_text())["results"]:
                raw["changes"] = [Change(**change) for change in raw["changes"]]
                previous_results.append(Result(**raw))
    if options.repair_domains and not previous_metadata:
        raise ValueError("Naprawa wybranych domen wymaga zatwierdzonego raportu z tego samego dnia")
    metadata["repair_domains"] = options.repair_domains or []
    metadata["reused_domains"] = sorted(reused)
    metadata["resumed_from"] = previous_metadata.get("run_id")
    semaphore = asyncio.Semaphore(options.concurrency)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scan-", dir=output) as temporary:
        staging = Path(temporary)
        for domain in reused:
            previous = output / day / slug(domain)
            if previous.is_dir():
                shutil.copytree(previous, staging / day / slug(domain))
        async with BrowserScanner(options.browser_executable, options.navigation_timeout, options.settle_ms) as scanner:
            async def capture_retry(site, kind, url, scenario, dest):
                for attempt in range(options.retries + 1):
                    try:
                        return await scanner.capture(site, kind, url, scenario, dest)
                    except Exception as exc:
                        # Permanent denials and invalid content do not improve with retries.
                        retryable = isinstance(exc, (TransientFetchError, BrowserTimeout)) or (
                            isinstance(exc, BrowserError) and any(code in str(exc) for code in (
                                "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_TIMED_OUT", "ERR_NETWORK_CHANGED",
                            ))
                        )
                        delay = max(min(2 ** attempt, 4), getattr(exc, "retry_after", 0))
                        if attempt == options.retries or not retryable or delay > 30:
                            raise
                        await asyncio.sleep(delay + 0.05)

            async def record(capture: Capture):
                snapshot = capture.snapshot
                excluded_prices = sites_by_domain[snapshot.domain].unreliable_price_keys
                before = store.previous(state, snapshot.key)
                snapshot.image = store.image(capture.screenshot)
                changes, retained = compare(before, snapshot, excluded_prices)
                communication, copy_changes = measure(before, snapshot)
                changes.extend(copy_changes)
                folder = staging / day / slug(snapshot.domain) / snapshot.page / slug(snapshot.scenario)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "odczyt.json").write_bytes(json_bytes(snapshot.to_dict()))
                if snapshot.scenario == "podstawowy":
                    (folder / "kontrolki.json").write_bytes(json_bytes({
                        "title": snapshot.title, "url": snapshot.url,
                        "controls": capture.payload.get("controls", []),
                        "headings": capture.payload.get("headings", []),
                        "prices": capture.payload.get("prices", []),
                        "warnings": snapshot.warnings,
                    }))
                evidence = {}
                result_warnings = list(snapshot.warnings)
                after_path = folder / "po.png"
                before_path = folder / "przed.png"
                difference_path = folder / "roznice.png"
                visual = None
                if before and before.renderer.split("|extractor=")[0] == snapshot.renderer.split("|extractor=")[0]:
                    visual = await asyncio.to_thread(image_difference, store.root / before.image, capture.screenshot, difference_path)
                elif before:
                    result_warnings.append("Zmieniono wersję przeglądarki; porównanie obrazu pominięto, a dane porównano ostrożnie.")
                if before and visual and visual.changed:
                    text, note = "", "Zmiana obrazu wymaga oceny; może wynikać również ze zmiany układu."
                    if options.ocr and snapshot.scenario != "podstawowy":
                        text, ocr_note = await asyncio.to_thread(ocr_context, capture.screenshot, folder / "fragment-ocr.png", visual.bbox)
                        note += " " + ocr_note
                    details = visual_description(before, snapshot, visual)
                    changes.append(Change("visual", "obraz", details["description"], None, text or details["position"], before.observed_at, snapshot.observed_at, snapshot.url, snapshot.scenario, note=details["basis"], details=details))
                if changes or before is None or snapshot.scenario == "podstawowy":
                    shutil.copy2(capture.screenshot, after_path)
                    evidence["po"] = after_path.relative_to(staging).as_posix()
                    if before:
                        shutil.copy2(store.root / before.image, before_path)
                        evidence["przed"] = before_path.relative_to(staging).as_posix()
                    if difference_path.exists():
                        evidence["roznice"] = difference_path.relative_to(staging).as_posix()
                    if before and visual and visual.changed and snapshot.scenario == "podstawowy":
                        crops = await asyncio.to_thread(visual_evidence, store.root / before.image, capture.screenshot, folder, visual)
                        evidence.update({k: p.relative_to(staging).as_posix() for k, p in crops.items()})
                        if options.ocr and not details.get("facts") and not details.get("rotation") and not details.get("unreliable"):
                            ocr = await asyncio.to_thread(visual_text, crops)
                            if ocr:
                                details["ocr"] = ocr
                                details["description"] = "Zmieniła się zawartość obrazu: " + details.get("area", "zaznaczony obszar")
                    if (folder / "fragment-ocr.png").exists():
                        evidence["fragment_ocr"] = (folder / "fragment-ocr.png").relative_to(staging).as_posix()
                elif difference_path.exists():
                    difference_path.unlink()
                for change in changes:
                    change.evidence = evidence
                status = "baseline" if before is None else "review" if changes and all(c.kind == "review" for c in changes) else "changed" if changes else "unchanged"
                if result_warnings:
                    status = "partial"
                results.append(Result(snapshot.domain, snapshot.page, snapshot.scenario, status, snapshot.url, changes, result_warnings, observed_at=snapshot.observed_at, evidence=evidence,
                                      data_quality=snapshot.quality, scenario_label=capture.payload.get("scenario_label", snapshot.scenario),
                                      offer=primary_offer(snapshot, excluded_prices) if snapshot.page == "projekt" else {},
                                      before_offer=primary_offer(before, excluded_prices) if snapshot.page == "projekt" else {},
                                      compared_at=before.observed_at if before else None, variant=capture.payload.get("variant", ""), communication=communication))
                if snapshot.quality == "ok" or snapshot.quality == "visual" and (before is None or not before.fields):
                    state["snapshots"][snapshot.key] = retained.to_dict()

            async def interactions(site: Site, kind: str, url: str, base: Capture, work: Path):
                explicit = [s for s in site.scenarios if s.page == kind]
                inferred, warnings = infer_scenarios(base.payload, kind, options.max_scenarios)
                queue = explicit + inferred
                seen = set()
                action_seen = {json.dumps(s.actions[-1], sort_keys=True) for s in queue if s.actions}
                completed = set()
                count = 0
                consecutive_failures = 0
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
                        consecutive_failures = 0
                        completed.add(scenario.id)
                        nested, nested_warnings = infer_scenarios(captured.payload, kind, options.max_scenarios)
                        warnings.extend(nested_warnings)
                        for child in nested:
                            if any(a.get("cart") for a in scenario.actions) and any(a.get("cart") for a in child.actions):
                                continue
                            action_key = json.dumps(child.actions[-1], sort_keys=True)
                            if action_key in action_seen:
                                continue
                            if sum(bool(a.get("inferred")) for a in scenario.actions) >= 2:
                                warnings.append("Dalsze zależne opcje wymagają jawnego scenariusza adaptera.")
                                continue
                            action_seen.add(action_key)
                            actions = scenario.actions + child.actions
                            identity = "nested-" + hashlib.sha256(json.dumps(actions, sort_keys=True).encode()).hexdigest()[:12]
                            queue.append(Scenario(identity, scenario.label + " / " + child.label, actions, page=kind))
                    except Exception as exc:
                        consecutive_failures += 1
                        results.append(Result(site.domain, kind, scenario.id, "unavailable" if isinstance(exc, UnusableControl) else "error", url, error=str(exc)[:2200], scenario_label=scenario.label))
                        if consecutive_failures >= 3:
                            warnings.append(f"Przerwano interakcje po 3 kolejnych nieudanych próbach; {len(queue)} pozostałych scenariuszy nie odczytano.")
                            break
                prior = {key.split("/", 2)[-1] for key in state["anchor"] if key.startswith(f"{site.domain}/{kind}/") and not key.endswith("/podstawowy")}
                for missing in sorted(prior - completed):
                    warnings.append(f"Poprzedni scenariusz nie został poprawnie odtworzony: {missing}; nie potwierdzono usunięcia funkcji.")
                if warnings:
                    results.append(Result(site.domain, kind, "pokrycie-interakcji", "partial", url, warnings=list(dict.fromkeys(warnings))))

            def reuse_base(site: Site, kind: str, url: str):
                if not options.resume or site.domain in (options.repair_domains or []):
                    return None
                old = next((r for r in previous_results if r.domain == site.domain and r.page == kind
                            and r.scenario == "podstawowy" and r.url == url and not r.error
                            and r.data_quality == "ok" and r.observed_at
                            and local_day(datetime.fromisoformat(r.observed_at)) == day), None)
                folder = Path(day) / slug(site.domain) / kind / "podstawowy"
                raw_path = output / folder / "odczyt.json"
                if not old or not raw_path.is_file():
                    return None
                snapshot = Snapshot.from_dict(json.loads(raw_path.read_text()))
                if (snapshot.observed_at != old.observed_at or not (store.root / snapshot.image).is_file()
                    or snapshot.renderer.split("|extractor=")[0] != scanner.renderer + ('-headed' if site.browser_headed else '')
                    or snapshot.document.get("adapter") != adapter_signature(site, Scenario("podstawowy", ""), kind)):
                    return None
                if old.offer.get("field_key") in site.unreliable_price_keys:
                    return None
                shutil.copytree(output / folder, staging / folder, dirs_exist_ok=True)
                results.append(copy.deepcopy(old))
                payload = snapshot.document.get("payload", {})
                return Capture(snapshot, payload, store.root / snapshot.image, payload.get("controls", []))

            async def process_site(site: Site):
                work = staging / ".work" / site.domain
                work.mkdir(parents=True, exist_ok=True)
                try:
                    home = reuse_base(site, "glowna", site.home_url)
                    if home is None:
                        home = await capture_retry(site, "glowna", site.home_url, Scenario("podstawowy", "Strona główna"), work / "home.png")
                        await record(home)
                except Exception as exc:
                    results.append(Result(site.domain, "glowna", "podstawowy", "error", site.home_url, error=str(exc).splitlines()[0][:600]))
                    home = None
                selection = state["selections"].get(site.domain)
                correction = site.selection.get("initial_choice_correction")
                if selection and correction and selection["url"] == correction.get("from_url") and is_listing_title(selection.get("name", "")) and local_day(datetime.fromisoformat(selection["selected_at"])) == correction.get("selected_day"):
                    metadata.setdefault("selection_corrections", []).append({"domain": site.domain, "from": selection, "reason": correction["reason"]})
                    state.setdefault("selection_corrections", {})[site.domain] = {"from": selection, "reason": correction["reason"], "corrected_at": now_iso()}
                    del state["selections"][site.domain]
                    for group in ("snapshots", "anchor"):
                        state[group] = {key: value for key, value in state[group].items() if not key.startswith(site.domain + "/projekt/")}
                    selection = None
                project = None
                if site.project_url:
                    if selection and selection["url"] != site.project_url and page_identity(selection["url"]) == page_identity(site.project_url):
                        metadata.setdefault("source_address_updates", []).append({"domain": site.domain, "before": selection["url"], "after": site.project_url})
                        selection = {**selection, "url": site.project_url}
                    if selection and selection["url"] != site.project_url:
                        raise ValueError("Konfiguracja zmienia zapamiętany projekt. Wymagana jawna migracja punktu odniesienia.")
                    selection = selection or {"url": site.project_url, "name": site.project_name or site.project_url, "basis": site.selection.get("basis", "Jawny wybór w konfiguracji"), "source": site.selection.get("source", site.home_url), "selected_at": now_iso()}
                if not selection and home:
                    selection, project, selection_warnings = await scanner.discover_project(site, home, work)
                    if selection_warnings:
                        results.append(Result(site.domain, "projekt", "wybor", "partial", site.home_url, warnings=selection_warnings))
                if selection:
                    try:
                        cached = reuse_base(site, "projekt", selection["url"])
                        project = project or cached or await capture_retry(site, "projekt", selection["url"], Scenario("podstawowy", "Wariant podstawowy"), work / "projekt.png")
                        # Selection is frozen only after a product page was successfully validated.
                        if site.project_name:
                            selection["name"] = site.project_name
                        state["selections"][site.domain] = selection
                        if cached is None:
                            await record(project)
                    except Exception as exc:
                        previous = store.previous(state, f"{site.domain}/projekt/podstawowy")
                        results.append(Result(site.domain, "projekt", "podstawowy", "error", selection["url"], error=str(exc).splitlines()[0][:600], before_offer=primary_offer(previous, site.unreliable_price_keys), compared_at=previous.observed_at if previous else None))
                        project = None
                else:
                    results.append(Result(site.domain, "projekt", "podstawowy", "unavailable", site.home_url, error="Nie ustalono karty projektu. Nie zastąpiono jej losowym adresem."))
                pending[site.domain] = (site, home, project, selection, work)
                if site.inspection != "verified":
                    results.append(Result(site.domain, "zakres", "inspekcja-adaptera", "partial", site.home_url, warnings=["Adapter nie ma potwierdzonej inspekcji tej domeny. Automatyczny odczyt nie oznacza pełnego pokrycia wszystkich interakcji."]))

            async def bounded(site: Site, detail: bool = False):
                async with semaphore:
                    remaining = options.budget_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        results.append(Result(site.domain, "zakres", "limit-czasu", "error", site.home_url, error="Wyczerpano czas skanu; domena niesprawdzona."))
                        return
                    elapsed = time.monotonic()
                    try:
                        timeout = options.domain_timeout - base_elapsed.get(site.domain, 0) if detail else options.domain_timeout
                        if timeout <= 0:
                            return
                        async with asyncio.timeout(min(timeout, remaining)):
                            if detail:
                                _, home, project, selection, work = pending[site.domain]
                                previous = [old for kind in ('glowna', 'projekt')
                                            if (old := store.previous(state, f'{site.domain}/{kind}/podstawowy'))]
                                await verify_offers(site, [home, project], results, previous, scanner,
                                                    work, staging / day / slug(site.domain))
                                if project and selection:
                                    await interactions(site, "projekt", selection["url"], project, work)
                                if home:
                                    await interactions(site, "glowna", site.home_url, home, work)
                            else:
                                await process_site(site)
                    except TimeoutError:
                        phase = scanner.phases.get(site.domain, "nieustalony etap")
                        if not detail:
                            for page, url in [("glowna", site.home_url), ("projekt", state["selections"].get(site.domain, {}).get("url") or site.project_url or site.home_url)]:
                                if not any(r.domain == site.domain and r.page == page and r.scenario == "podstawowy" for r in results):
                                    results.append(Result(site.domain, page, "podstawowy", "error", url, error=f"Przekroczono czas domeny ({phase}); odczyt strony nieukończony."))
                        results.append(Result(site.domain, "zakres", "limit-czasu", "partial", site.home_url, error=f"Przekroczono czas domeny ({phase}); pozostały zakres nie został sprawdzony."))
                    except Exception as exc:
                        results.append(Result(site.domain, "zakres", "blad", "error", site.home_url, error=str(exc).splitlines()[0][:600]))
                    if not detail:
                        base_elapsed[site.domain] = time.monotonic() - elapsed
                    print(f"{'Interakcje' if detail else 'Odczyt bazowy'}: {site.domain}", flush=True)

            await asyncio.gather(*(bounded(site) for site in sites if site.domain not in reused))
            metadata["base_reads_finished_at"] = now_iso()
            # Install a verified base checkpoint before expensive interactions.
            # A normal exception can publish it; a killed runner leaves an artifact.
            metadata["retained_same_day_reads"] = preserve_same_day_reads(results, previous_results, state, sites, output, staging, day)
            checkpoint_metadata = dict(metadata, scan_phase="base-checkpoint", finished_at=now_iso(),
                                       elapsed_seconds=round(time.monotonic() - started, 3))
            with tempfile.TemporaryDirectory(dir=output) as checkpoint_dir:
                checkpoint = Path(checkpoint_dir)
                if (staging / day).exists():
                    shutil.copytree(staging / day, checkpoint / day)
                checkpoint_results = copy.deepcopy(results)
                for site in sites:
                    if site.domain in pending:
                        checkpoint_results.append(Result(site.domain, "zakres", "checkpoint", "partial", site.home_url,
                            warnings=["Zapisano odczyty podstawowe; interakcje nie zostały jeszcze ukończone."]))
                write_outputs(checkpoint, day, checkpoint_results, checkpoint_metadata, state["selections"], [s.domain for s in sites])
                install_outputs(checkpoint, output, day, slug(run_id) + "-base")
            store.commit(state)
            await asyncio.gather(*(bounded(site, detail=True) for site in sites if site.domain in pending))
        metadata["scan_phase"] = "complete"
        results.sort(key=lambda result: (result.domain, result.page, result.scenario))
        metadata.update(finished_at=now_iso(), elapsed_seconds=round(time.monotonic() - started, 3), renderer=scanner.renderer)
        metadata["snapshot_bytes"] = sum((store.root / image).stat().st_size for image in {s["image"] for s in state["snapshots"].values()})
        metadata["evidence_bytes"] = sum(p.stat().st_size for p in (staging / day).rglob("*.png"))
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
            owner = json.loads((directory / "manifest.json").read_text()).get("owner")
        except (OSError, ValueError):
            continue
        if owner != "pracownie-monitor:v1":
            continue
        try:
            parsed = date.fromisoformat(directory.name).isoformat()
        except ValueError:
            continue
        if parsed <= cutoff:
            shutil.rmtree(directory)
            (output / f"{parsed}.txt").unlink(missing_ok=True)
    return {"metadata": metadata, "results": results, "state": copy.deepcopy(state)}
