# AI-Powered Smart Home Designer

A prototype web app for a technical assignment. The user enters land and house requirements. The app asks an LLM for **3 different house design concepts**, draws a **2D floor plan for each one in code (SVG)**, generates **AI images** (exterior and interiors), **recommends the best concept**, and lets the user **edit the requirements and regenerate** as a new version (v1, v2, v3).

Everything uses free tools. There is no Docker anywhere.

## Features

- Requirement form with validation (all fields required, positive numbers, warning when plot size does not match width x length)
- 3 concepts that really differ in layout (kitchen corner and parking side are checked, not just the names)
- Room-wise sizes, space utilization, advantages and a parking-impact note for each concept
- A recommended concept with the reason
- Budget estimate range per concept (INR) with a clear "estimate only" note
- Feasibility check: if the request cannot fit the plot, rooms are **not** shrunk below the minimums. The app returns the closest design plus a note such as "choose G+1"
- 2D floor plans drawn as SVG: rooms, names, sizes, doors with swing arcs, windows, parking, stairs, plot outline, road side and a scale bar. G+1 gets Ground Floor / First Floor tabs
- 4 AI images per design (3D exterior, living room, bedroom, kitchen). The recommended design generates automatically, the others on a button click
- Modify and regenerate: change BHK, budget, style, floors, bathrooms or parking. Old values are kept, the result is saved as a new version, and older versions stay viewable

## Architecture

```
 Browser (React + Vite, port 5173)
   RequirementForm -> App -> DesignTabs -> FloorPlanSVG / ImageGallery / ModifyPanel
        |  fetch (JSON)
        v
 FastAPI backend (port 8000)
   routers/designs.py          routers/images.py
        |                            |
        v                            v
   services/llm_service.py      services/image_service.py
     Gemini (primary)             Cloudflare FLUX (primary)
     Groq   (fallback)            Pollinations   (fallback)
        |                            |
        v                            v
   services/layout_builder       generated_images/ (files on disk)
   services/floorplan_validator
        |                            |
        +-----------+----------------+
                    v
             PostgreSQL (SQLAlchemy)
   design_requests -> designs -> design_images
```

The detailed request flow is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech choices and why

| Choice | Why |
|---|---|
| React + Vite, plain JavaScript | Fast to start, no TypeScript or UI library to explain |
| FastAPI | Pydantic validation built in, clear error codes, automatic `/docs` page for demos |
| PostgreSQL + SQLAlchemy | Requested stack. The design JSON is stored in a JSON column, so no extra tables for rooms |
| Gemini Flash, Groq fallback | Both have free tiers. Two providers means a rate limit on one does not stop the demo |
| Cloudflare FLUX, Pollinations fallback | FLUX schnell is fast and cheap on the free allowance. Pollinations needs no key |
| SVG floor plans from JSON | Image models cannot draw accurate plans. Code can, and the numbers match the text exactly |
| Images saved to disk | The demo still works after a free quota runs out |

## AI models and API integration

| Job | Primary | Fallback | How it is called |
|---|---|---|---|
| Design JSON | Gemini `gemini-2.5-flash` | Groq `openai/gpt-oss-120b` | Plain HTTP with `httpx`. Gemini `generateContent` in JSON mode with a token limit and a small thinking budget. Groq OpenAI-compatible chat. The JSON is taken from the first `{` to the last `}` of the reply |
| Images | Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell` (4 steps) | Pollinations.ai image URL | Cloudflare REST `ai/run` returns base64. Pollinations returns image bytes |

Model names change often, so they are set in `.env` (`GEMINI_MODEL`, `GROQ_MODEL`). API keys only come from `.env` and are never logged.

## How the prompts and fallbacks work

1. `prompts/design_prompt.py` holds the system prompt (coordinates, BHK rules, parking rules, JSON shape), the three layout strategies and the cost rates. It is the file to read when explaining the AI side.
2. For each concept, `prompt_builder.py` adds the form values, one layout strategy, and a feasibility warning if the request is too big for the plot.
3. `llm_service.py` calls Gemini. On any error or rate limit it calls Groq instead.
4. The reply is parsed and checked by Pydantic. `layout_builder.py` then turns the bands into rooms with coordinates, and `floorplan_validator.py` checks the result. If anything fails, the **error list goes back into the prompt** and the LLM retries (2 retries by default, so 3 tries per concept; set `LLM_MAX_RETRIES` in `.env` to change it).
5. Concepts are generated one at a time. This keeps each request small enough for Groq's free token-per-minute limit.
6. A final small LLM call picks the recommended concept. If it fails, a rule picks the first concept that fits the budget.
7. **Cost numbers are computed in code**, not by the LLM, because LLMs are unreliable at arithmetic. The LLM only writes one sentence of advice.

Images use the same pattern: Cloudflare first, then Pollinations. After two failures in a row the remaining images are skipped, so a quota problem does not make the user wait.

## Floor plan generation approach

The LLM returns strict JSON, but it does **not** write coordinates. LLMs are weak at coordinate arithmetic: in testing they produced rooms outside the plot and overlapping rooms. Instead the LLM describes each floor as horizontal **bands** from the back of the plot to the road. Each band has a height, and each room in it has a width. `layout_builder.py` places the bands top to bottom and the rooms left to right, so rooms can never overlap or leave the plot. The result is the usual JSON with `x, y, width, height` for every room, which is what gets validated and stored. In short, the LLM decides and the code guarantees correctness.

Coordinates are in feet, origin at the top-left of the plot, x to the right, y downward. **The road and gate are always on the bottom edge.** React draws that JSON as SVG, so no image AI is involved.

**BHK handling.** 2BHK means exactly 2 bedrooms, 3BHK exactly 3. The validator counts rooms by type, requires exactly one `master_bedroom` with exactly one `attached_bathroom`, and requires the bathroom total to equal the form value. A wrong count is rejected and sent back to the LLM.

**Parking handling.** If parking is requested, `parking` must exist, match the requested type, meet the minimum size (1 car 10x18 ft, 2 cars 20x18 or 10x36, two-wheeler 6x7 for two), touch the road edge, and not overlap any room. If not requested, it must be `null`. Parking is drawn as an open area with a dashed border and a light fill, not as a room. The exterior image prompt mentions parking only when it was requested.

**Minimum room sizes (ft):** master bedroom 11x12, bedroom 10x10, living 11x14, kitchen 8x10, attached bathroom 5x8, common bathroom 4x7 (0.5 ft tolerance, either orientation).

**Builder repairs and checks:** the Ground Floor bands must fill the plot exactly (upper floors only have to fit). When the LLM's numbers are slightly off, the builder fixes them instead of costing a retry: a room below its minimum is widened by taking width from the roomiest neighbour, and widths or heights that do not add up are grown or shrunk, never below a room's minimum. A room needs less width in a taller band, so a band that is a foot too narrow is made taller rather than rejected. If the rooms in a band cannot fit at all, the error says how much width they need. It also maps common wrong room types ("bathroom", "living room"), and numbers rooms that share a name.

**Doors and windows are placed by code, not by the LLM** (`opening_planner.py`). LLMs cannot see the plan, so in testing they put doors on outside walls, opened bathrooms into the wrong room and put windows on inside walls. Now every door sits on a wall two rooms really share, each room gets one door to a room that is already reachable from the living hall (or the stairs on an upper floor), the attached bathroom always opens into the master bedroom, the main door is on the living hall's road-side wall, and windows only go on wall pieces that face outside. If the attached bathroom does not touch the master bedroom, or a room cannot reach any other room, the plan is rejected with a message that says what to move. Because sizes can be adjusted, the text fields do not quote room sizes; the size table and the drawing always show the real numbers.

**Validator checks:** rooms and parking inside the plot, no overlaps, used area close to the plot area, bedroom and bathroom counts, minimum sizes, required rooms, a staircase on both floors for G+1, both floor plans present, doors and windows on real walls, and a main door on the ground floor.

**Feasibility.** `prompt_builder.py` estimates the smallest area the request needs. If it exceeds the plot, the LLM is told to keep minimum sizes and return a `feasibility_note` with what to change. Example: 3BHK + 2 cars on a 25x40 ground floor suggests "choose G+1, or reduce parking to 1 car, or choose 2BHK".

**Drawing.** Doors are a wall gap plus a quarter-circle swing arc opening into the room. Windows are two thin parallel lines in a wall gap. Stairs have tread lines. Each plan has a plot outline, a road strip, dimension text and a scale bar.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | API and database check |
| POST | `/api/designs/generate` | New project: generate 3 concepts, save as v1 |
| GET | `/api/designs/{request_id}` | One saved version with its concepts |
| POST | `/api/designs/{request_id}/modify` | Apply only the edited fields to that version, save the result as the next version |
| GET | `/api/designs/projects/{project_id}/versions` | List versions with what changed in each |
| GET | `/api/designs/{design_id}/images` | Images already saved (never calls an AI) |
| POST | `/api/designs/{design_id}/images` | Generate whichever of the 4 images are missing |
| GET | `/generated/...` | Saved image files |

Status codes: 201 created, 404 not found, 409 version conflict, 422 invalid input or nothing changed, 502 the AI never produced a valid plan, 503 all AI providers failed. Interactive docs are at `http://localhost:8000/docs`.

## Database

- `design_requests`: form values, `project_id`, `version_number`, `parent_request_id` (which version it was modified from)
- `designs`: one row per concept, with the full concept JSON and a recommended flag
- `design_images`: image type, provider and the file path on disk

## Folder structure

```
smart-home-designer/
  README.md  .gitignore
  docs/            SETUP.md  ARCHITECTURE.md  LIMITATIONS.md
  backend/
    requirements.txt  .env.example
    scripts/init_db.py
    app/
      main.py  config.py  database.py  models.py  schemas.py
      routers/designs.py  images.py
      services/llm_service.py  layout_builder.py  opening_planner.py  floorplan_validator.py  prompt_builder.py  image_service.py
      prompts/design_prompt.py
    tests/test_floorplan_validator.py  test_image_prompts.py  test_layout_builder.py  test_opening_planner.py
  frontend/
    package.json  vite.config.js  .env.example  index.html
    src/
      main.jsx  App.jsx  api/client.js  styles/app.css
      components/RequirementForm.jsx  DesignTabs.jsx  FloorPlanSVG.jsx  ImageGallery.jsx  ModifyPanel.jsx
```

## Running it

Full steps are in [docs/SETUP.md](docs/SETUP.md). In short:

```
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then fill it in
python scripts/init_db.py
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev                                           # open http://localhost:5173
```
