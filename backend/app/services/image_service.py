"""image_service.py - makes images with Cloudflare Workers AI (FLUX) and falls back to Pollinations.ai.

Images are saved to disk. The database only stores the file path, so the demo still works
after a free quota runs out.
"""
import base64
import logging
import time
from urllib.parse import quote

import httpx

from app.config import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, IMAGE_DIR, IMAGE_TIMEOUT_SECONDS

log = logging.getLogger("image_service")

CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CF_STEPS = 4  # schnell is built for about 4 steps (max 8); more steps only burn free neurons
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"
POLLINATIONS_GAP_SECONDS = 15  # the anonymous tier allows about one request per 15 seconds
_last_pollinations_call = 0.0


class ImageError(Exception):
    """No provider could produce an image."""


def generate_with_cloudflare(prompt: str) -> bytes:
    """Call Workers AI over REST. The image comes back as a base64 string."""
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN):
        raise ImageError("Cloudflare credentials are not set")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CF_MODEL}"
    try:
        resp = httpx.post(url, headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
                          json={"prompt": prompt[:2048], "steps": CF_STEPS}, timeout=IMAGE_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ImageError(f"Cloudflare request failed ({exc.__class__.__name__})") from exc
    if resp.status_code == 429:
        raise ImageError("Cloudflare rate limit reached")
    if resp.status_code >= 400:
        # Past the 10,000 free neurons/day, Cloudflare answers with an error here.
        raise ImageError(f"Cloudflare error {resp.status_code}: {resp.text[:150]}")
    body = resp.json()
    # The REST API wraps the answer in {"result": {...}}, the Workers binding does not.
    payload = body.get("result", body) if isinstance(body, dict) else None
    image_b64 = payload.get("image") if isinstance(payload, dict) else None
    if not image_b64:
        raise ImageError("Cloudflare returned no image")
    return base64.b64decode(image_b64)


def generate_with_pollinations(prompt: str) -> bytes:
    """Call the keyless Pollinations endpoint, waiting if needed to respect its rate limit."""
    global _last_pollinations_call
    wait = POLLINATIONS_GAP_SECONDS - (time.time() - _last_pollinations_call)
    if wait > 0:
        time.sleep(wait)
    _last_pollinations_call = time.time()
    params = {"width": 1024, "height": 768, "model": "flux", "nologo": "true"}
    try:
        resp = httpx.get(POLLINATIONS_URL + quote(prompt, safe=""), params=params,
                         timeout=IMAGE_TIMEOUT_SECONDS, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ImageError(f"Pollinations request failed ({exc.__class__.__name__})") from exc
    if resp.status_code >= 400:
        raise ImageError(f"Pollinations error {resp.status_code}")
    if not resp.headers.get("content-type", "").startswith("image/"):
        raise ImageError("Pollinations did not return an image")
    return resp.content


def generate_image(prompt: str) -> tuple[bytes, str]:
    """Try Cloudflare first, then Pollinations. Returns (image bytes, provider name)."""
    problems = []
    for name, call in (("cloudflare", generate_with_cloudflare), ("pollinations", generate_with_pollinations)):
        try:
            return call(prompt), name
        except ImageError as exc:
            log.warning("%s failed, trying next provider: %s", name, exc)
            problems.append(str(exc))
    raise ImageError("All image providers failed: " + " | ".join(problems))


def save_image(design_id: int, image_type: str, data: bytes) -> str:
    """Write the image under IMAGE_DIR and return its path relative to IMAGE_DIR (this goes in the DB)."""
    extension = "png" if data.startswith(b"\x89PNG") else "jpg"
    folder = IMAGE_DIR / f"design_{design_id}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{image_type}.{extension}").write_bytes(data)
    except OSError as exc:
        raise ImageError(f"Could not save the image to disk: {exc.strerror}") from exc
    return f"design_{design_id}/{image_type}.{extension}"
