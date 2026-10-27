"""Rebuild a committed report from verified captures, without visiting websites."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from .communication import measure
from .compare import compare
from .github import GitHubStore
from .images import image_difference, visual_evidence, visual_text
from .model import (
    Change,
    Result,
    Site,
    Snapshot,
    digest,
    json_bytes,
    load_sites,
    local_day,
    now_iso,
    safe_path,
    slug,
)
from .observations import visual_description
from .offers import primary_offer
from .pipeline import preserve_same_day_reads
from .report import bundle_report, restore_report, verify_outputs, write_outputs
from .state import StateStore


def enrich_communication(results: list[Result], output: Path, state: dict) -> None:
    """Use original timestamp-matched captures, never fetch a historical page."""
    for result in results:
        if not result.observed_at or result.scenario == "ponowienie-podstawowego":
            continue
        key = f"{result.domain}/{result.page}/{result.scenario}"
        # Folder uses the report's Warsaw day, which can differ from UTC.
        path = output / local_day(datetime.fromisoformat(result.observed_at)) / slug(result.domain) / result.page / slug(result.scenario) / "odczyt.json"
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            raw = state.get("snapshots", {}).get(key)
        if not raw or raw.get("observed_at") != result.observed_at or (raw.get("domain"), raw.get("page"), raw.get("scenario")) != (result.domain, result.page, result.scenario):
            continue
        prior = state.get("anchor", {}).get(key)
        before = Snapshot.from_dict(prior) if prior and prior.get("observed_at") == result.compared_at else None
        result.communication, changes = measure(before, Snapshot.from_dict(raw))
        checks = {(c.field_key, c.before, c.after, c.before_at, c.after_at, c.url): c.details['commercial_check']
                  for c in result.changes if c.details.get('commercial_check')}
        # Rebuild is idempotent and keeps the original source evidence.
        result.changes = [c for c in result.changes if not c.field_key.startswith("communication:")]
        for change in changes:
            change.evidence = dict(result.evidence)
            identity = (change.field_key, change.before, change.after, change.before_at, change.after_at, change.url)
            if identity in checks:
                change.details['commercial_check'] = checks[identity]
        result.changes.extend(changes)


def repair_archived_quotes(results: list[Result], output: Path, day: str) -> list[dict]:
    """Correct the reviewed header parsing error from its original field text."""
    corrected = []
    for result in results:
        if result.domain != "projektyszkieletowe.pl" or result.page != "projekt" or result.offer.get("field_key") != "adapter:cena-projektu":
            continue
        path = output / day / slug(result.domain) / result.page / slug(result.scenario) / "odczyt.json"
        try:
            raw = json.loads(path.read_text())
            if raw.get("observed_at") != result.observed_at or raw.get("domain") != result.domain or raw.get("page") != result.page or raw.get("scenario") != result.scenario:
                raise ValueError("Niezgodna tożsamość źródła")
            quote = primary_offer(Snapshot.from_dict(raw))
        except (OSError, KeyError, ValueError):
            quote = {}
        if result.offer != quote:
            corrected.append({"domain": result.domain, "scenario": result.scenario, "observed_at": result.observed_at, "before": result.offer.get("amount"), "after": quote.get("amount"), "basis": "Korekta parsera z oryginalnej treści zapisanego pola; nie jest zmianą oferty"})
            result.offer = quote
    return corrected


def enrich_visual_results(results: list[Result], output: Path, store: StateStore | None = None) -> None:
    """Describe actual archived image differences, without inventing site changes."""
    output = output.resolve()
    state = store.read() if store else {}
    for result in results:
        visuals = [c for c in result.changes if c.category == "obraz" and not c.details.get("communication_asset")]
        if not visuals or result.scenario != "podstawowy" or not all(result.evidence.get(k) for k in ["przed", "po"]):
            continue
        before = safe_path(output, result.evidence["przed"])
        after = safe_path(output, result.evidence["po"])
        difference = image_difference(before, after, after.parent / "roznice.png")
        if not difference.changed:
            continue
        archived_crops = {}
        for key in ('fragment_przed', 'fragment_po'):
            path = safe_path(output, result.evidence[key]) if result.evidence.get(key) else None
            if path and path.is_file():
                archived_crops[key] = digest(path)
        crops = visual_evidence(before, after, after.parent, difference)
        result.evidence.update({k: p.relative_to(output).as_posix() for k, p in crops.items()})
        old = Snapshot(result.domain, result.page, result.scenario, result.url, result.compared_at or "", "", {}, [], "", "")
        new = Snapshot(result.domain, result.page, result.scenario, result.url, result.observed_at or "", "", {}, [], "", "")
        for name, candidate, at in [("anchor",old,result.compared_at),("snapshots",new,result.observed_at)]:
            raw = state.get(name,{}).get(f"{result.domain}/{result.page}/{result.scenario}")
            if raw and raw.get("observed_at") == at:
                candidate.quality = raw.get("quality","unknown")
                candidate.warnings = raw.get("warnings",[])
                candidate.document = raw.get("document",{})
        # Re-evaluate archived observations with the repaired asset matching;
        # do not keep an old positional comparison as a confirmed design fact.
        if all(s.document.get("visual", {}).get("schema") == 1 for s in (old, new)):
            details = visual_description(old, new, difference)
        else:
            details = next((c.details for c in visuals if c.details.get("facts")), None) or visual_description(old, new, difference)
        ocr = {} if details.get("facts") or details.get("rotation") else visual_text(crops)
        if not ocr and not details.get('facts') and not details.get('rotation') and len(archived_crops) == 2:
            # OCR is optional in a formatting runner. Keep the recorded text
            # only when BOTH regenerated evidence crops are byte-identical.
            if all(key in crops and digest(crops[key]) == value for key, value in archived_crops.items()):
                ocr = next((dict(c.details['ocr']) for c in visuals if c.details.get('ocr')), {})
        if ocr:
            details["ocr"] = ocr
            details["description"] = "Zmieniła się zawartość obrazu: " + details.get("area", "zaznaczony obszar")
        for change in visuals:
            change.kind = "visual"
            change.label = details["description"]
            change.details = details
            change.evidence = dict(result.evidence)
            change.note = details["basis"]


def recover_from_snapshots(results: list[Result], store: StateStore, output: Path, day: str, sites: list[Site]) -> list[dict]:
    from datetime import datetime

    state = store.read()
    prior = []
    configured = {site.domain: site for site in sites}
    cache = store.root / "verified-read-cache"
    for failed in results:
        if failed.scenario != "podstawowy" or not failed.error or failed.observed_at:
            continue
        raw = state["snapshots"].get(f"{failed.domain}/{failed.page}/podstawowy")
        if not raw:
            continue
        snapshot = Snapshot.from_dict(raw)
        if snapshot.quality != "ok" or local_day(datetime.fromisoformat(snapshot.observed_at)) != day:
            continue
        snapshot.fields = {key: field for key, field in snapshot.fields.items() if (field.observed_at or snapshot.observed_at) == snapshot.observed_at}
        excluded = configured[snapshot.domain].unreliable_price_keys
        # Do not restore a quote from a publisher field known to be incorrect.
        if excluded and not any(key.startswith("adapter:") for key in snapshot.fields):
            continue
        before = store.previous(state, snapshot.key)
        changes, _ = compare(before, snapshot, excluded)
        folder = Path(day) / slug(snapshot.domain) / snapshot.page / "podstawowy"
        target = cache / folder
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(store.root / snapshot.image, target / "po.png")
        evidence = {"po": (folder / "po.png").as_posix()}
        if before:
            shutil.copy2(store.root / before.image, target / "przed.png")
            evidence["przed"] = (folder / "przed.png").as_posix()
            if before.renderer.split("|extractor=")[0] == snapshot.renderer.split("|extractor=")[0]:
                visual = image_difference(store.root / before.image, store.root / snapshot.image, target / "roznice.png")
                if visual.changed:
                    evidence["roznice"] = (folder / "roznice.png").as_posix()
                    changes.append(Change("review", "obraz", "Zmiana wyglądu lub treści graficznej", None, "Patrz obrazy przed/po", before.observed_at, snapshot.observed_at, snapshot.url, snapshot.scenario))
        for change in changes:
            change.evidence = evidence
        (target / "odczyt.json").write_bytes(json_bytes(snapshot.to_dict()))
        prior.append(Result(snapshot.domain, snapshot.page, "podstawowy", "review" if changes else "unchanged", snapshot.url, changes, list(snapshot.warnings), observed_at=snapshot.observed_at, evidence=evidence, data_quality=snapshot.quality, scenario_label="Zachowany poprawny odczyt", offer=primary_offer(snapshot, excluded) if snapshot.page == "projekt" else {}, before_offer=primary_offer(before, excluded) if snapshot.page == "projekt" else {}, compared_at=before.observed_at if before else None))
    return preserve_same_day_reads(results, prior, state, sites, cache, output, day)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "MateuszD0/Pracownie"))
    parser.add_argument("--namespace", default="monitor")
    parser.add_argument("--root", type=Path, default=Path(".monitor/report-rebuild"))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument('--include-new-sites', action='store_true', help='Dodaj skonfigurowane nowe pracownie z jawnym statusem oczekiwania na pierwszy skan')
    args = parser.parse_args()
    remote = GitHubStore(args.repository, os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", ""), args.namespace)
    store = StateStore(args.root / "state")
    try:
        with store.lock():
            record = remote.pull(store)
            if not record:
                raise ValueError("Brak zatwierdzonego raportu i stanu")
            day = record["day"]
            asset_id = record.get("report_files", {}).get("zip", record["report_assets"][-1])
            asset = remote.request("GET", f"{remote.prefix}/releases/assets/{asset_id}").json()
            remote.download(asset, args.root / "source.zip", asset.get("digest", "").removeprefix("sha256:") or None)
            output = args.root / "raporty"
            restore_report(args.root / "source.zip", output, day, record["run_id"])
            data = json.loads((output / day / "zmiany.json").read_text())
            selections = json.loads((output / day / "wybrane-projekty.json").read_text())
            archived_domains = list(json.loads((output / day / "pokrycie.json").read_text()))
            sites = load_sites(Path("config/sites.json"))
            configured = {site.domain for site in sites}
            domains = [domain for domain in archived_domains if domain in configured]
            additions = sorted(configured - set(archived_domains)) if args.include_new_sites else []
            if additions and args.namespace != 'monitor':
                raise ValueError('Nowe domeny można dopisać w tym trybie tylko do pełnego monitoringu')
            domains += additions
            if not domains:
                raise ValueError("Brak skonfigurowanych domen w raporcie; nie opublikowano pustego zakresu")
            active = set(domains)
            selections = {domain: selection for domain, selection in selections.items() if domain in active}
            results = []
            for raw in data["results"]:
                if raw["domain"] not in active:
                    continue
                raw["changes"] = [Change(**change) for change in raw["changes"]]
                results.append(Result(**raw))
            for site in sites:
                if site.domain in additions:
                    for page, url in [('glowna',site.home_url),('projekt',site.project_url or site.home_url)]:
                        results.append(Result(site.domain,page,'podstawowy','unavailable',url,
                                              error='Nowa pracownia — pierwszy skan jeszcze niewykonany.'))
            metadata = data["metadata"]
            if additions:
                metadata['new_domains'] = additions
            metadata["domains"] = len(domains)
            for key in ("reused_domains", "repair_domains"):
                if key in metadata:
                    metadata[key] = [domain for domain in metadata[key] if domain in active]
            removed = sorted(set(archived_domains) - active)
            if removed:
                metadata["removed_domains"] = sorted(set(metadata.get("removed_domains", [])) | set(removed))
                # Remove only regenerated files; prior published editions and
                # stored captures remain available in their original archives.
                for domain in removed:
                    shutil.rmtree(safe_path(output, day + "/" + slug(domain)), ignore_errors=True)
            metadata["source_price_corrections"] = metadata.get("source_price_corrections", []) + repair_archived_quotes(results, output, day)
            metadata["retained_same_day_reads"] = metadata.get("retained_same_day_reads", []) + recover_from_snapshots(results, store, output, day, [site for site in sites if site.domain in active])
            metadata.setdefault("source_scan_run_id", metadata["run_id"])
            metadata["report_rendered_at"] = now_iso()
            metadata["run_id"] = now_iso().replace(":", "").replace("+", "-") + "-format-" + uuid.uuid4().hex[:8]
            enrich_visual_results(results, output, store)
            enrich_communication(results, output, store.read())
            results.sort(key=lambda r: (r.domain, r.page, r.scenario))
            write_outputs(output, day, results, metadata, selections, domains)
            verify_outputs(output, day)
            archive = args.root / "report.zip"
            bundle_report(output, day, archive)
            view = json.loads((output / day / "oferty.json").read_text())
            print(json.dumps({"counts": view["counts"], "failed_attempts": sum(bool(r.error) for r in results), "restored_reads": metadata["retained_same_day_reads"]}, ensure_ascii=False), flush=True)
            if args.publish:
                print(json.dumps(remote.publish(store, output, day, archive, metadata["run_id"]), ensure_ascii=False), flush=True)
                print(remote.update_index(), flush=True)
    finally:
        remote.close()


if __name__ == "__main__":
    main()
