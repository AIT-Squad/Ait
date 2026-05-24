"""YAML I/O helpers bridging pydantic models and on-disk YAML files."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from .io_utils import atomic_write_text

T = TypeVar("T", bound=BaseModel)


def _json_safe(value: Any) -> Any:
    """Convert pydantic-dumped values into YAML-safe scalars."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def load_yaml(path: Path) -> dict:
    """Load a YAML file as a dict (returns {} for empty file)."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def load_model(path: Path, model: type[T]) -> T:
    """Load a YAML file and validate against a pydantic model."""
    data = load_yaml(path)
    return model.model_validate(data)


def dump_model(model: BaseModel) -> str:
    """Dump a pydantic model to a YAML string (stable order, block style)."""
    raw = model.model_dump(by_alias=True, exclude_none=False)
    safe = _json_safe(raw)
    return yaml.safe_dump(
        safe,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


def save_model(path: Path, model: BaseModel) -> None:
    """Atomically write a pydantic model as YAML."""
    text = dump_model(model)
    atomic_write_text(path, text)
