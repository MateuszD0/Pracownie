"""Rebuild a committed report from verified captures, without visiting websites."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

from .compare import compare
from .github import GitHubStore
from .images import image_difference
from .model import Change, Result, Site, Snapshot, json_bytes, load_sites, local_day, now_iso, slug
from .offers import primary_offer
from .pipeline import preserve_same_day_reads
from .report import bundle_report, restore_report, verify_outputs, write_outputs
from .state import StateStore


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
        changes, _ = compare(before, snapshot)
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
            domains = list(json.loads((output / day / "pokrycie.json").read_text()))
            results = []
            for raw in data["results"]:
                raw["changes"] = [Change(**change) for change in raw["changes"]]
                results.append(Result(**raw))
            metadata = data["metadata"]
            metadata["retained_same_day_reads"] = metadata.get("retained_same_day_reads", []) + recover_from_snapshots(results, store, output, day, load_sites(Path("config/sites.json")))
            metadata.setdefault("source_scan_run_id", metadata["run_id"])
            metadata["report_rendered_at"] = now_iso()
            metadata["run_id"] = now_iso().replace(":", "").replace("+", "-") + "-format-" + uuid.uuid4().hex[:8]
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
