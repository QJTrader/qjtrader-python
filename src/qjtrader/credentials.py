"""Least-surprise loading for local QJ machine credential files."""
from __future__ import annotations

import os
from pathlib import Path

from .errors import QJError

ALLOWED_KEYS = {
    "QJ_CLIENT_ID", "QJ_CLIENT_SECRET", "QJ_TOKEN_URL", "QJ_DATA_HOST",
    "QJ_DATA_PORT", "QJ_ORDERS_HOST", "QJ_ORDERS_PORT", "QJ_DATA_REST_PORT",
    "QJ_ORDERS_REST_PORT", "QJ_CA_FILE",
}


def load_credentials_file(file: str | os.PathLike[str]) -> dict[str, str]:
    """Read a dotenv-shaped QJ credential file without changing ``os.environ``.

    Only ``QJ_*`` keys used by the SDK are accepted. Shell interpolation and
    command substitution are deliberately unsupported.
    """
    path = Path(file).expanduser()
    if not path.is_file():
        raise QJError(f"credential file not found: {path}")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise QJError(f"credential file is readable by another user; run chmod 600 {path}")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or key not in ALLOWED_KEYS:
            raise QJError(f"unsupported credential-file entry on line {number}: {key or line}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    missing = [key for key in ("QJ_CLIENT_ID", "QJ_CLIENT_SECRET") if not values.get(key)]
    if missing:
        raise QJError(f"credential file is missing {', '.join(missing)}")
    return values
