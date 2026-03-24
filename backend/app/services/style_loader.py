import json
from pathlib import Path
from functools import lru_cache

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"


@lru_cache(maxsize=None)
def load_style(style_id: str) -> dict:
    path = STYLES_DIR / f"{style_id}.json"
    if not path.exists():
        raise ValueError(f"Style not found: {style_id}")
    with open(path) as f:
        return json.load(f)


def list_styles() -> list[dict]:
    styles = []
    for path in sorted(STYLES_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        styles.append({"id": data["id"], "name": data["name"]})
    return styles
