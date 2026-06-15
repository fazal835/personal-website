from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/projects")

PROJECTS = [
    {
        "title": "AI Chat Experiment",
        "description": "A simple chatbot powered by Claude to answer questions about my blog posts.",
        "tags": ["AI", "Python", "Claude"],
        "status": "In Progress",
        "link": "/tools/chat",
    },
]


@router.get("/")
async def projects_index(request: Request):
    return templates.TemplateResponse("projects/index.html", {
        "request": request,
        "projects": PROJECTS,
    })
