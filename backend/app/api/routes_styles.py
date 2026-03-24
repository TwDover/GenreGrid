from fastapi import APIRouter
from app.services.style_loader import list_styles
from app.models.schemas import StyleInfo

router = APIRouter()


@router.get("/styles", response_model=list[StyleInfo])
def get_styles():
    return list_styles()
