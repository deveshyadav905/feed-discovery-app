# main.py
import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from feeddiscovery.discovery_async import AsyncFeedDiscovery

app = FastAPI(
    title="Feed & Sitemap Discovery",
    version="1.0.0"
)
templates = Jinja2Templates(directory="templates")

# Mount static folder for CSS/JS if needed
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# -------------------------------
# Homepage (Single Page)
# -------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "results": None})


@app.post("/discover")
async def discover(domain: str = Form(...)):
    results = await AsyncFeedDiscovery(domain).discover()
    return {"results": results}
