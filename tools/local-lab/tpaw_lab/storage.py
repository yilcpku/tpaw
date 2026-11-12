"""Private local store, with Git exclusion checked before every write."""
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


def private_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError("Data root must be a directory")
    # Do not trust a directory name like .private: verify owning Git metadata.
    for ancestor in (root, *root.parents):
        if not (ancestor / ".git").exists():
            continue
        rel = root.relative_to(ancestor).as_posix()
        tracked = subprocess.run(["git", "-C", str(ancestor), "ls-files", "-z", "--", rel], capture_output=True, check=True)
        if tracked.stdout:
            raise ValueError("Private root contains tracked files")
        ignored = subprocess.run(["git", "-C", str(ancestor), "check-ignore", "--no-index", "-q", "--", rel + "/"], capture_output=True)
        if ignored.returncode != 0:
            raise ValueError("Private root is not excluded from Git")
        break
    root.mkdir(parents=True, exist_ok=True)
    return root


class Store:
    def __init__(self, root: Path):
        self.root = private_root(root)

    def _path(self, category: str, identifier: str) -> Path:
        if category not in ("scenarios", "results", "data", "baselines") or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identifier):
            raise ValueError("Invalid local record identifier")
        path = (self.root / category / (identifier + ".json")).resolve()
        if not path.is_relative_to(self.root) or path.is_symlink():
            raise ValueError("Local path escapes data root")
        return path

    def put(self, category: str, record: dict, identifier: str | None = None) -> str:
        private_root(self.root)
        key = identifier or uuid.uuid4().hex
        path = self._path(category, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        canonical = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if category in ("data", "results", "baselines") and path.exists():
            existing = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False, allow_nan=False, sort_keys=True)
            if existing == canonical:
                return key
            raise ValueError("Frozen data/results already exist; use a new versioned identifier")
        temp = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, allow_nan=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return key

    def get(self, category: str, identifier: str) -> dict:
        return json.loads(self._path(category, identifier).read_text(encoding="utf-8"))

    def list(self, category: str) -> list[dict]:
        result = []
        for path in sorted((self.root / category).glob("*.json")):
            record = self.get(category, path.stem)
            result.append({"id": path.stem, "name": record.get("name", path.stem),
                           "updated": path.stat().st_mtime})
        return result
