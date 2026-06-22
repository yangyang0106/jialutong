import json
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(path)


def load_routes(path: Path) -> dict:
    return load_json(path, {})


def save_routes(path: Path, routes: dict) -> None:
    save_json(path, routes)
