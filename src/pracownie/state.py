from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from .model import SCHEMA, Snapshot, digest, json_bytes, local_day, safe_path


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def referenced_images(data: dict) -> set[str]:
    return {
        snapshot["image"]
        for section in ("snapshots", "anchor")
        for snapshot in data.get(section, {}).values()
        if snapshot.get("image")
    }


class StateStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "state.json"

    @contextmanager
    def lock(self):
        with (self.root / ".lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Inny skan zapisuje ten sam stan") from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self) -> dict:
        if not self.path.exists():
            return {"schema": SCHEMA, "day": "", "snapshots": {}, "anchor": {}, "selections": {}}
        data = json.loads(self.path.read_text())
        if data.get("schema") != SCHEMA:
            raise ValueError("Nieobsługiwana wersja stanu; przerwano zamiast utracić historię")
        for image in referenced_images(data):
            if not safe_path(self.root, image).is_file():
                raise ValueError(f"Brak obrazu stanu: {image}")
        return data

    def begin(self, day: str, retention: int = 180) -> dict:
        date.fromisoformat(day)
        data = copy.deepcopy(self.read())
        if data["day"] > day:
            raise ValueError("Nie można zapisać starszego dnia ponad nowszym stanem")
        if data["day"] != day:
            data["anchor"] = copy.deepcopy(data["snapshots"])
        data["day"] = day
        cutoff = (date.fromisoformat(day) - timedelta(days=retention)).isoformat()
        for section in ("snapshots", "anchor"):
            data[section] = {
                key: value for key, value in data[section].items() if local_day(datetime.fromisoformat(value["observed_at"])) > cutoff
            }
            for snapshot in data[section].values():
                # A missing section may retain an older field inside a newer snapshot.
                # Such fields must expire by their own observation date as well.
                snapshot["fields"] = {
                    key: value for key, value in snapshot["fields"].items()
                    if local_day(datetime.fromisoformat(value.get("observed_at") or snapshot["observed_at"])) > cutoff
                }
        return data

    def image(self, source: Path) -> str:
        from .images import lossless_image

        content, extension = lossless_image(source)
        relative = f"images/{hashlib.sha256(content).hexdigest()}{extension}"
        target = safe_path(self.root, relative)
        if not target.exists():
            atomic_write(target, content)
        return relative

    def commit(self, data: dict) -> None:
        for image in referenced_images(data):
            if not safe_path(self.root, image).is_file():
                raise ValueError(f"Nie można utrwalić stanu bez obrazu: {image}")
        atomic_write(self.path, json_bytes(data))

    def collect(self, data: dict) -> None:
        keep = referenced_images(data)
        for path in (self.root / "images").glob("*.*"):
            if path.suffix in {".png", ".webp"} and path.relative_to(self.root).as_posix() not in keep:
                path.unlink()

    def export(self, destination: Path, data: dict | None = None) -> None:
        data = data or self.read()
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("state.json", json_bytes(data))
            for relative in sorted(referenced_images(data)):
                archive.write(safe_path(self.root, relative), relative)

    def restore(self, archive_path: Path, expected_hash: str | None = None) -> None:
        if expected_hash and digest(archive_path) != expected_hash:
            raise ValueError("Niepoprawna suma kontrolna pobranego stanu")
        with tempfile.TemporaryDirectory(dir=self.root.parent) as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(archive_path) as archive:
                if sum(info.file_size for info in archive.infolist()) > 1_500_000_000:
                    raise ValueError("Archiwum przekracza limit rozpakowanego stanu")
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError("Powtórzone ścieżki w archiwum")
                for info in archive.infolist():
                    path = safe_path(staging, info.filename)
                    if info.is_dir():
                        path.mkdir(parents=True, exist_ok=True)
                        continue
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("Dowiązania symboliczne w archiwum są niedozwolone")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, path.open("wb") as target:
                        shutil.copyfileobj(source, target)
            data = StateStore(staging).read()
            if not (staging / "state.json").exists():
                raise ValueError("Archiwum nie zawiera stanu")
            for relative in referenced_images(data):
                source = safe_path(staging, relative)
                if source.suffix not in {".png", ".webp"} or relative != f"images/{digest(source)}{source.suffix}":
                    raise ValueError("Niepoprawna suma kontrolna obrazu")
                atomic_write(safe_path(self.root, relative), source.read_bytes())
            self.commit(data)

    @staticmethod
    def previous(data: dict, key: str) -> Snapshot | None:
        value = data["anchor"].get(key)
        return Snapshot.from_dict(value) if value else None
