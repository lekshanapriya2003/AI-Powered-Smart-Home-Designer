# Limitations, assumptions and known issues

## Free-tier limits (checked while building, they change often)

| Service | Limit that matters here | What the app does |
|---|---|---|
| Gemini free tier | Per-minute and per-day request limits shown in your AI Studio project. On a short per-minute limit (up to 45 s) the app waits once and retries Gemini before using Groq; on a longer limit it switches straight away. Model names are retired regularly. Free-tier content may be used by Google to improve its products. | Falls back to Groq on any error. The model name is set in `.env` (default `gemini-2.5-flash`). |
| Groq free tier | Per-minute request and token limits that depend on the model. See console.groq.com/settings/limits. | One concept per request. The default is `openai/gpt-oss-120b`, a reasoning model whose thinking also counts toward the token limit. A full run on Groq alone can still hit the limit and fail. |
| Cloudflare Workers AI | 10,000 neurons per day (reset 00:00 UTC). A 4-step FLUX schnell image is roughly 40 to 60 neurons, so about 200 images a day. | Falls back to Pollinations after an error. |
| Pollinations (keyless) | About 1 request per 15 seconds. May add a watermark. The keyless endpoint could change or stop. | The app waits 15 seconds between its calls. A set of 4 images can take around a minute. |

The Cloudflare figures come from published per-step pricing. Check your dashboard for real usage.

## Assumptions

- **Coordinates and road.** The road and gate are always on the bottom edge of the plot. Plans are not rotated.
- **Costs.** Rates per sq ft are assumptions: Traditional ₹1,800 to 2,300, Modern ₹2,200 to 2,800, Luxury ₹3,200 to 4,500. Built-up area is the sum of all room areas. Walls, parking, finishing upgrades, land, permits and taxes are not counted. "Fits budget" means the budget covers the low end of the range.
- **Plot size.** If size and width x length disagree by more than 10%, the app warns and uses width x length.
- **Area fill.** Ground floor rooms plus parking should cover at least 70% of the plot, and an upper floor at least 35%. These are rules of thumb.
- **Bathrooms.** The first bathroom is always the master's attached bathroom. The rest are common bathrooms.
- **Two-wheeler parking.** Assumes up to two vehicles, so at least 6 x 7 ft.
- **Feasibility.** The early check uses minimum room areas with 15% extra for walls and passages. It is an estimate, not a proof.
- **Plot fixed per project.** Plot size and dimensions cannot be edited in a new version. Start a new project instead.

## Known issues and trade-offs

**Plan quality**
- The validator proves rooms fit, do not overlap and meet the minimum sizes. It does **not** prove the layout is good design. Adjacency rules (kitchen beside the living area, common bathroom reachable from it) are in the prompt but not checked in code. Windows are not checked to be on outer walls.
- A `feasibility_note` relaxes two checks: the area-fill check and the requirement that the parking type equals the requested one. Bedroom count, minimum sizes and overlaps always stay strict.
- Doors and windows are placed by code from the geometry. Each room opens into a neighbour that is already reachable from the living hall, preferring the living hall, then the stairs, kitchen and bedrooms. If a bedroom does not touch the living hall, it can still be reached through the kitchen or another bedroom (a walk-through room). Bathrooms are never walked through. The planner has no idea of furniture, privacy or ventilation, and it does not draw a corridor.
- Variety between concepts is enforced only by the kitchen's zone (back, middle or front third) and side, and the parking side.
- Because rooms sit in rows, every room in a band has the same depth. L-shaped or staggered layouts are not possible.
- The builder may adjust room sizes by a foot or two to make the arithmetic work. So the text fields never quote sizes (any like "12x12" are removed), and the size table and drawing show the real numbers.
- If the LLM keeps failing validation, the user gets a 502 and has to try again.
- Strict rules cost retries: a plan is rejected if the attached bathroom does not touch the master bedroom, or if a room cannot reach any other room. Setting `LLM_MAX_RETRIES=4` in `.env` is recommended.
- Plans are concept drawings. They are not structural, vastu or building-code checked and must not be used for construction.

**Images**
- Images show style and colours, not the exact floor plan. The image model can also ignore details (for example it may draw an extra storey or a scooter instead of the car). Four separate generations can still differ in small details.
- Pollinations quality and availability are less predictable than Cloudflare.

**Performance**
- A full generation makes 4 LLM calls, or up to 10 with retries, one after another. With reasoning models expect 1 to 3 minutes. The request blocks with no live progress.

**Versions**
- A version's change list compares it with the version it was modified from. Versions saved before `parent_request_id` existed would have no parent.
- Versions cannot be deleted or renamed.

**Platform**
- No user accounts. Anyone who can reach the backend can read every project.
- The image lock lives in one process. Running several uvicorn workers would remove that protection.
- There is no migration tool. `init_db.py` creates tables and adds the one column added later.
- Which LLM answered is returned to the browser at generation time but is not stored.

## Testing coverage

- 61 unit tests: 23 for the floor plan validator, 5 for the image prompts, 21 for the layout builder and 12 for the door and window planner. A randomized stress test (not part of the suite) fed 1,500 sloppy layouts through the builder and found no overlapping or out-of-bounds rooms. They need no database or keys.
- The LLM calls, the image calls and the endpoints were checked with mocked providers. There are no automated frontend tests, and the floor plan SVG was checked by rendering sample plans and looking at them.
- Real Gemini, Groq, Cloudflare and Pollinations responses are only exercised when you run the app with real keys.
