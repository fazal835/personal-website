from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.routes import home, blog, projects, tools

load_dotenv()

app = FastAPI(title="The Curious Engineer")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(home.router)
app.include_router(blog.router)
app.include_router(projects.router)
app.include_router(tools.router)
