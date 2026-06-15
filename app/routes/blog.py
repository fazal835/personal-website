from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates

from app.utils.blog import get_all_posts, get_post_by_slug

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/blog")


@router.get("/")
async def blog_index(request: Request):
    posts = get_all_posts()
    return templates.TemplateResponse("blog/index.html", {
        "request": request,
        "posts": posts,
    })


@router.get("/{slug}")
async def blog_post(request: Request, slug: str):
    post = get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse("blog/post.html", {
        "request": request,
        "post": post,
    })
