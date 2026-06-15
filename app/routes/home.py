from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.utils.blog import get_recent_posts

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/")
async def home(request: Request):
    recent_posts = get_recent_posts(limit=3)
    return templates.TemplateResponse("home.html", {
        "request": request,
        "recent_posts": recent_posts,
    })
