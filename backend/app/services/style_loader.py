import json
import logging
from pathlib import Path
from functools import lru_cache

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"

_logger = logging.getLogger(__name__)
_REQUIRED_FIELDS = ("id", "name", "bpm_range", "default_scale", "progression_templates")


@lru_cache(maxsize=None)
def load_style(style_id: str) -> dict:
    path = STYLES_DIR / f"{style_id}.json"
    if not path.exists():
        raise ValueError(f"Style not found: {style_id}")
    with open(path) as f:
        data = json.load(f)
    missing = [field for field in _REQUIRED_FIELDS if field not in data]
    if missing:
        _logger.warning("Style %r is missing required fields: %s", style_id, missing)
    return data


def list_styles() -> list[dict]:
    styles = []
    for path in sorted(STYLES_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        styles.append({"id": data["id"], "name": data["name"], "bpm_range": data.get("bpm_range", [40, 240]), "default_scale": data.get("default_scale", "minor")})
    return styles
