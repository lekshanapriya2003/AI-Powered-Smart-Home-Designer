"""config.py - loads settings from the .env file.

Everything secret or machine-specific lives in .env so no key is ever hardcoded.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _required(name: str) -> str:
    """Return an env variable or stop early with a clear message."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Copy backend/.env.example to backend/.env and fill it in."
        )
    return value


DATABASE_URL = _required("DATABASE_URL")

# Optional for now: the LLM and image keys are only needed from Phase 2 / 4 onwards.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")

# Model names change often, so they live in .env instead of the code.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))  # extra tries per concept after a rejected plan

IMAGE_TIMEOUT_SECONDS = float(os.getenv("IMAGE_TIMEOUT_SECONDS", "120"))
IMAGE_DIR = BACKEND_DIR / os.getenv("IMAGE_DIR", "generated_images")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
