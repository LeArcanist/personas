from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from starlette.middleware.sessions import SessionMiddleware

from database import engine, SessionLocal
import models
from routers import users, auth, chat, api, steam
from auth_utils import hash_password

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(users.router)
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(steam.router)

app.add_middleware(SessionMiddleware, 
                   secret_key="change-this-to-a-random-secret",
                   https_only=False)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request}
    )