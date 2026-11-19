"""main.py - FastAPI entry point. Routers are added in later phases."""
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import FRONTEND_ORIGIN, IMAGE_DIR
from app.database import get_db
from app.routers import designs, images

# Show the app's own log lines (rejected LLM attempts, provider fallbacks) in the terminal.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="AI-Powered Smart Home Designer")
app.include_router(designs.router)
app.include_router(images.router)

# Saved images are served from disk, so the DB only needs their relative path.
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=IMAGE_DIR), name="generated")

# The React dev server runs on a different port, so the browser needs CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, FRONTEND_ORIGIN.replace("localhost", "127.0.0.1")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Confirm the API is up and the database connection works."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database not reachable: {exc.__class__.__name__}")
    return {"status": "ok", "database": "connected"}
