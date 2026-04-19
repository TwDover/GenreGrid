import re
from fastapi import APIRouter, HTTPException
from app.services.style_loader import list_styles, get_style_detail, save_custom_style
from app.models.schemas import StyleInfo

router = APIRouter()

_VALID_ID = re.compile(r'^[a-z0-9_]{1,40}$')


@router.get("/styles", response_model=list[StyleInfo])
def get_styles():
    return list_styles()


@router.get("/styles/{style_id}/detail")
def get_style_detail_route(style_id: str):
    try:
        return get_style_detail(style_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Style not found: {style_id}")


@router.post("/styles/custom")
def create_custom_style(body: dict):
    style_id = body.get("id", "")
    if not _VALID_ID.match(style_id):
        raise HTTPException(status_code=422, detail="Style id must be 1-40 lowercase alphanumeric/underscore chars")
    if not body.get("name"):
        raise HTTPException(status_code=422, detail="Style name is required")
    required = ("bpm_range", "default_scale", "progression_templates")
    for field in required:
        if field not in body:
            raise HTTPException(status_code=422, detail=f"Missing required field: {field}")
    return save_custom_style(body)
