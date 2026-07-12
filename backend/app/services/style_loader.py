# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import json
import logging
from pathlib import Path
from functools import lru_cache

from app.core.config import CUSTOM_STYLES_DIR

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"

_logger = logging.getLogger(__name__)
_REQUIRED_FIELDS = ("id", "name", "bpm_range", "default_scale", "progression_templates")


@lru_cache(maxsize=None)
def load_style(style_id: str) -> dict:
    custom_path = CUSTOM_STYLES_DIR / f"{style_id}.json"
    builtin_path = STYLES_DIR / f"{style_id}.json"
    path = custom_path if custom_path.exists() else builtin_path
    if not path.exists():
        raise ValueError(f"Style not found: {style_id}")
    with open(path) as f:
        data = json.load(f)
    missing = [field for field in _REQUIRED_FIELDS if field not in data]
    if missing:
        _logger.warning("Style %r is missing required fields: %s", style_id, missing)
    return data


def list_styles() -> list[dict]:
    from app.services.priors import prior_exists, groove_exists

    def _has_prior(data: dict) -> bool:
        sid = data.get("id", "")
        return (prior_exists(data.get("prior") or sid)
                or groove_exists(data.get("groove") or sid))

    def _instruments(data: dict) -> dict[str, str]:
        from app.core.instruments import instrumentation_for
        return {part: inst["display_name"] for part, inst in instrumentation_for(data).items()}

    styles = []
    seen: set[str] = set()
    # Custom styles override built-ins with the same id
    for path in sorted(CUSTOM_STYLES_DIR.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            seen.add(data["id"])
            styles.append({"id": data["id"], "name": data["name"], "bpm_range": data.get("bpm_range", [40, 240]), "default_scale": data.get("default_scale", "minor"), "custom": True, "has_prior": _has_prior(data), "instruments": _instruments(data)})
        except Exception as exc:
            _logger.warning("Skipping malformed custom style %s: %s", path, exc)
    for path in sorted(STYLES_DIR.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            if data["id"] in seen:
                continue
            styles.append({"id": data["id"], "name": data["name"], "bpm_range": data.get("bpm_range", [40, 240]), "default_scale": data.get("default_scale", "minor"), "has_prior": _has_prior(data), "instruments": _instruments(data)})
        except Exception as exc:
            _logger.warning("Skipping malformed style %s: %s", path, exc)
    return sorted(styles, key=lambda s: s["name"])


def save_custom_style(style_data: dict) -> dict:
    style_id = style_data["id"]
    path = CUSTOM_STYLES_DIR / f"{style_id}.json"
    path.write_text(json.dumps(style_data, indent=2))
    load_style.cache_clear()
    return style_data


def get_style_detail(style_id: str) -> dict:
    return load_style(style_id)
