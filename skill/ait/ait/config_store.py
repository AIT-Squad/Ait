"""Layered project configuration store (v2.71).

Project config lives in two layers under ``<root>/.meta/``:

- ``config.yaml`` (shared) — tracked by the docs repo. Machine-independent,
  project-level settings only (``initialized``, ``auto_snapshot_on_merge``).
- ``config.local.yaml`` (machine-local) — excluded by the docs repo's
  ``.gitignore``. Holds machine-specific fields whose values vary per
  environment (``skill_dir``, ``cli_path``, ``wrapper_path``,
  ``acceptance_command``).

Reads merge both layers with the local layer winning. Writes route each field
to its owning layer via the explicit :data:`MACHINE_FIELDS` table.

Failure semantics are the point of this module: a *missing* layer is a normal
empty config, but a layer that exists and is *corrupt* raises
``CONFIG_UNREADABLE`` instead of degrading to ``{}``. Silent degradation would
let a gate that depends on config (artifact acceptance) mistake "cannot read"
for "not configured" and let the merge through — gates must fail closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import yaml

from .io_utils import atomic_write_text

SHARED_CONFIG_NAME = "config.yaml"
LOCAL_CONFIG_NAME = "config.local.yaml"

#: Explicit ownership table — machine-specific fields live in the local layer.
#: Membership is checked against this frozenset only; ownership is never
#: guessed from name patterns. New machine fields must be registered here.
MACHINE_FIELDS: frozenset[str] = frozenset(
    {"skill_dir", "cli_path", "wrapper_path", "acceptance_command"}
)


class ConfigError(RuntimeError):
    """Raised when a config layer exists but cannot be read as a mapping."""

    def __init__(self, message: str, *, code: str = "CONFIG_UNREADABLE") -> None:
        super().__init__(message)
        self.code = code


def _layer_path(meta_dir: Path, name: str) -> Path:
    return Path(meta_dir) / name


def _load_layer(path: Path) -> dict:
    """Read a single layer.

    Missing file → ``{}`` (normal: uninitialised project, or single-layer
    project). Empty file → ``{}`` (an empty config is legal). Present but
    unparseable, or parsing to a non-mapping → ``ConfigError``.

    Uses ``yaml.safe_load`` only: config files travel with the repo, so an
    unsafe loader would be an arbitrary-object-construction entry point.
    """
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — any parse failure is unreadable
        raise ConfigError(
            f"config layer {path.name} exists but is not valid YAML: {exc}"
        ) from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(
            f"config layer {path.name} must contain a mapping, "
            f"got {type(loaded).__name__}"
        )
    return loaded


def read_layer(meta_dir: Path, *, local: bool) -> dict:
    """Return a single layer's raw view (callers that must distinguish origin)."""
    name = LOCAL_CONFIG_NAME if local else SHARED_CONFIG_NAME
    return _load_layer(_layer_path(meta_dir, name))


def read_config(meta_dir: Path) -> dict:
    """Return the merged config view; the local layer wins on key collisions.

    Propagates ``ConfigError`` — never degrades a corrupt layer to ``{}``.
    """
    merged = read_layer(meta_dir, local=False)
    merged.update(read_layer(meta_dir, local=True))
    return merged


def _dump(data: Mapping) -> str:
    return yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False)


def write_config_fields(
    meta_dir: Path,
    fields: Mapping | None = None,
    *,
    delete: Iterable[str] = (),
) -> None:
    """Route ``fields`` to their owning layer and persist atomically.

    ``delete`` removes keys from *both* layers — "unset" should also clear a
    stale copy left in the shared layer by a pre-v2.71 project.

    A layer with nothing to change is not touched at all (no empty file
    created, no mtime refresh). Each target layer is read before writing, so a
    corrupt layer raises ``CONFIG_UNREADABLE`` *before* any write — we never
    overwrite a layer we could not read, which would silently drop settings.
    """
    fields = dict(fields or {})
    delete_keys = list(delete)

    partitions = (
        (LOCAL_CONFIG_NAME, {k: v for k, v in fields.items() if k in MACHINE_FIELDS}),
        (SHARED_CONFIG_NAME, {k: v for k, v in fields.items() if k not in MACHINE_FIELDS}),
    )

    for name, updates in partitions:
        if not updates and not delete_keys:
            continue
        path = _layer_path(meta_dir, name)
        data = _load_layer(path)
        changed = False
        for key in delete_keys:
            if key in data:
                del data[key]
                changed = True
        for key, value in updates.items():
            if key not in data or data[key] != value:
                data[key] = value
                changed = True
        if not changed:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, _dump(data))


def find_legacy_machine_fields(meta_dir: Path) -> dict:
    """Return machine-specific fields still present in the *shared* layer.

    This is the single source of truth for "does this project need migrating".
    """
    shared = read_layer(meta_dir, local=False)
    return {k: v for k, v in shared.items() if k in MACHINE_FIELDS}


def move_machine_fields_to_local(meta_dir: Path) -> dict:
    """Move machine-specific fields out of the shared layer into the local one.

    Order is fixed: write the destination first, then strip the source. If
    interrupted, the worst case is the field existing in both layers — which
    :func:`find_legacy_machine_fields` still reports, so re-running converges
    (idempotent). The reverse order could lose the value entirely.

    A field already present in the local layer keeps its local value (same
    precedence as :func:`read_config`); the shared copy is still removed
    because it is the stale one. Values are moved verbatim — no normalisation,
    no path rewriting.

    Returns the fields that were cleared from the shared layer.
    """
    legacy = find_legacy_machine_fields(meta_dir)
    if not legacy:
        return {}

    local_path = _layer_path(meta_dir, LOCAL_CONFIG_NAME)
    local = _load_layer(local_path)
    for key, value in legacy.items():
        if key not in local:
            local[key] = value
    local_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(local_path, _dump(local))

    shared_path = _layer_path(meta_dir, SHARED_CONFIG_NAME)
    shared = _load_layer(shared_path)
    for key in legacy:
        shared.pop(key, None)
    atomic_write_text(shared_path, _dump(shared))

    return legacy
