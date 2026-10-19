"""Verify a downloaded daily archive and summarize coverage without extracting files."""
import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter


def audit(path):
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if re.fullmatch(r"raporty/\d{4}-\d{2}-\d{2}/manifest\.json", name)]
        if len(candidates) != 1:
            raise ValueError("Oczekiwano jednego dziennego manifestu")
        prefix = candidates[0].rsplit("/", 1)[0]
        manifest = json.loads(archive.read(candidates[0]))
        for name, record in manifest["files"].items():
            with archive.open("raporty/" + name) as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if checksum != record["sha256"]:
                raise ValueError("Niepoprawna suma kontrolna: " + name)
        coverage = json.loads(archive.read(prefix + "/pokrycie.json"))
        results = json.loads(archive.read(prefix + "/zmiany.json"))
        selections = json.loads(archive.read(prefix + "/wybrane-projekty.json"))
        if len(coverage) != results["metadata"]["domains"]:
            raise ValueError("Liczba domen w metrykach i pokryciu jest różna")
        return {
            "metadata": results["metadata"], "verified_files": len(manifest["files"]),
            "counts": dict(Counter(row["status"] for row in coverage.values())),
            "selections": selections,
            "domains": {domain: {
                "status": row["status"],
                "home": next((s["status"] for s in row["scenarios"] if s["page"] == "glowna" and s["scenario"] == "podstawowy"), "unrun"),
                "project": next((s["status"] for s in row["scenarios"] if s["page"] == "projekt" and s["scenario"] == "podstawowy"), "unrun"),
                "errors": [s["error"] for s in row["scenarios"] if s["error"]],
                "warnings": list(dict.fromkeys(w for s in row["scenarios"] for w in s["warnings"])),
            } for domain, row in coverage.items()},
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), ensure_ascii=False, indent=2))
