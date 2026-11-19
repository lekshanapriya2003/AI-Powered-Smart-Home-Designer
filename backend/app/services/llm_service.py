"""llm_service.py - talks to Gemini (primary) and Groq (fallback) and produces validated design concepts.

Flow per concept: ask the LLM -> parse JSON -> Pydantic -> floorplan validator.
If anything fails, the error list goes back to the LLM (max 2 retries).
"""
import json
import logging
import time

import httpx
from pydantic import ValidationError

from app.config import (GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL, LLM_MAX_RETRIES,
                        LLM_TIMEOUT_SECONDS)
from app.prompts.design_prompt import LAYOUT_STRATEGIES, RECOMMEND_PROMPT, STYLE_RATES, SYSTEM_PROMPT
from app.schemas import Concept, ConceptDraft, DesignRequestIn
from app.services.floorplan_validator import layout_signature, validate_concept
from app.services.layout_builder import build_concept
from app.services.prompt_builder import build_recommend_prompt, build_user_prompt, feasibility_hint

log = logging.getLogger("llm_service")
MAX_RETRIES = LLM_MAX_RETRIES  # retries after the first attempt (default 2, so 3 tries per concept)
MAX_OUTPUT_TOKENS = 8192  # a full plan plus text is long, and reasoning models also spend tokens thinking
MAX_RATE_LIMIT_WAIT = 45  # seconds: wait this long for a short rate limit, otherwise switch provider
DISCLAIMER = "Approximate estimate only, not a quotation. Real costs depend on location, materials and contractor."


class LLMError(Exception):
    """An LLM call failed (rate limit, bad key, network...). retry_after is set when the provider says how long to wait."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class DesignGenerationError(Exception):
    """The LLM answered, but never produced a plan that passed validation."""


def _retry_seconds(resp: httpx.Response) -> float | None:
    """Read how long the provider wants us to wait: the Retry-After header, or Gemini's retryDelay like "27s"."""
    try:
        if resp.headers.get("retry-after"):
            return float(resp.headers["retry-after"])
        for detail in resp.json()["error"]["details"]:
            if "retryDelay" in detail:
                return float(detail["retryDelay"].rstrip("s"))
    except (ValueError, KeyError, TypeError):
        pass
    return None


def _post(url: str, headers: dict, body: dict, provider: str) -> dict:
    """POST JSON and turn network or HTTP problems into a short LLMError (the API key is never logged)."""
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=LLM_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise LLMError(f"{provider} request failed ({exc.__class__.__name__})") from exc
    if resp.status_code == 429:
        raise LLMError(f"{provider} rate limit reached", retry_after=_retry_seconds(resp))
    if resp.status_code >= 400:
        raise LLMError(f"{provider} error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def call_gemini(system_prompt: str, user_prompt: str) -> str:
    """Call Gemini's generateContent REST endpoint in JSON mode and return the text."""
    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    if "2.5" in GEMINI_MODEL:
        # A small thinking budget helps with room sizes. Other model versions use a different setting.
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 1024}
    data = _post(url, {"x-goog-api-key": GEMINI_API_KEY}, body, "Gemini")
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("Gemini returned no answer (the response may have been blocked)")
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def call_groq(system_prompt: str, user_prompt: str) -> str:
    """Call Groq's OpenAI-compatible chat endpoint in JSON mode and return the text."""
    if not GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not set")
    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.4,  # low temperature keeps the JSON tidy
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    if "gpt-oss" in GROQ_MODEL:
        body["reasoning_effort"] = "medium"  # only the gpt-oss models accept this setting
    data = _post("https://api.groq.com/openai/v1/chat/completions",
                 {"Authorization": f"Bearer {GROQ_API_KEY}"}, body, "Groq")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("Groq returned no answer")


def ask_llm(system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """Try Gemini first, then Groq. A short rate limit is waited out once before switching provider."""
    problems = []
    for name, call in (("gemini", call_gemini), ("groq", call_groq)):
        for attempt in range(2):
            try:
                return call(system_prompt, user_prompt), name
            except LLMError as exc:
                short_wait = exc.retry_after is not None and exc.retry_after <= MAX_RATE_LIMIT_WAIT
                if attempt == 0 and short_wait:
                    log.warning("%s rate limited, waiting %.0f s and retrying once", name, exc.retry_after)
                    time.sleep(exc.retry_after + 1)
                    continue
                log.warning("%s failed, trying next provider: %s", name, exc)
                problems.append(str(exc))
                break
    raise LLMError("All LLM providers failed: " + " | ".join(problems))


def parse_json_reply(text: str) -> dict:
    """Parse the LLM text as JSON, using everything between the first { and the last } (drops fences or chatter)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def _pydantic_errors(exc: ValidationError) -> list[str]:
    """Shorten Pydantic errors into 'path: message' lines the LLM can act on."""
    lines = []
    for e in exc.errors()[:8]:
        shown = f" (you wrote {e['input']!r})" if isinstance(e.get("input"), (str, int, float)) else ""
        lines.append(f"JSON field {'.'.join(str(p) for p in e['loc'])}: {e['msg']}{shown}")
    return lines


def _fix_budget_note(concept: Concept, req: DesignRequestIn) -> None:
    """Compute the cost numbers in code, because LLMs are unreliable at arithmetic."""
    rate_min, rate_max = STYLE_RATES[req.style]
    area = sum(r.width * r.height for f in concept.floors for r in f.rooms)  # parking is open, not counted
    note = concept.budget_note
    note.built_up_sqft = round(area)
    note.rate_min_per_sqft, note.rate_max_per_sqft = rate_min, rate_max
    note.cost_min_inr, note.cost_max_inr = round(area * rate_min), round(area * rate_max)
    note.fits_budget = req.budget_inr >= note.cost_min_inr
    note.disclaimer = DISCLAIMER


def generate_concept(req: DesignRequestIn, layout_hint: str, used_layouts: list) -> tuple[Concept, str]:
    """Get one valid concept from the LLM, retrying with the validation errors in the prompt."""
    errors: list[str] = []
    for attempt in range(MAX_RETRIES + 1):
        text, provider = ask_llm(SYSTEM_PROMPT, build_user_prompt(req, layout_hint, errors))
        try:
            draft = ConceptDraft.model_validate(parse_json_reply(text))
        except json.JSONDecodeError:
            errors = ["The reply was not valid JSON. Return only the JSON object."]
        except ValidationError as exc:
            errors = _pydantic_errors(exc)
        else:
            concept, errors = build_concept(draft, req)  # places the bands, so rooms cannot overlap
            if concept:
                errors = validate_concept(concept, req)
            if concept and not errors and layout_signature(concept, req) in used_layouts:
                errors = ["Layout is too similar to an earlier concept. Move the kitchen to a different zone or side, and/or the parking to the other side."]
            if concept and not errors:
                if not concept.feasibility_note:
                    concept.feasibility_note = feasibility_hint(req) or None
                _fix_budget_note(concept, req)
                return concept, provider
        log.info("Concept attempt %d (%s) rejected: %s", attempt + 1, provider, errors)
    raise DesignGenerationError("The AI could not produce a valid floor plan after retries. Last problems: " + "; ".join(errors[:5]))


def _fallback_pick(concepts: list[Concept]) -> tuple[int, str]:
    """Used if the recommendation call fails: first concept that fits the budget, else the cheapest."""
    fitting = [i for i, c in enumerate(concepts) if c.budget_note.fits_budget]
    pool = fitting or range(len(concepts))
    best = min(pool, key=lambda i: concepts[i].budget_note.cost_min_inr)
    why = "fits your budget" if fitting else "has the lowest estimated cost, though none clearly fit the budget"
    return best, f"Chosen automatically because it {why}."


def choose_recommendation(req: DesignRequestIn, concepts: list[Concept]) -> tuple[int, str]:
    """Ask the LLM which concept suits the requirements best, with a rule-based fallback."""
    try:
        text, _ = ask_llm(RECOMMEND_PROMPT, build_recommend_prompt(req, concepts))
        data = parse_json_reply(text)
        index = int(data["recommended_index"])
        if 0 <= index < len(concepts):
            return index, str(data["reason"])
    except (LLMError, ValueError, KeyError, TypeError) as exc:
        log.warning("Recommendation call failed, using fallback: %s", exc)
    return _fallback_pick(concepts)


def generate_all_concepts(req: DesignRequestIn) -> tuple[list[Concept], list[str]]:
    """Generate 3 concepts one by one (small calls suit Groq's token limit), then pick the best."""
    concepts, providers, layouts = [], [], []
    for hint in LAYOUT_STRATEGIES:
        concept, provider = generate_concept(req, hint, layouts)
        layouts.append(layout_signature(concept, req))
        concepts.append(concept)
        providers.append(provider)
    index, reason = choose_recommendation(req, concepts)
    concepts[index].recommended = True
    concepts[index].recommendation_reason = reason
    return concepts, providers
