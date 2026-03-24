from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EXPORTS_DIR = BASE_DIR / "exports"
STYLES_DIR = BASE_DIR / "app" / "styles"

EXPORTS_DIR.mkdir(exist_ok=True)
