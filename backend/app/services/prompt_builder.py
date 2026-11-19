"""prompt_builder.py - turns form values into LLM prompts and does the early feasibility check."""
import json

from app.prompts.design_prompt import IMAGE_STYLE_WORDS, STYLE_RATES
from app.schemas import Concept, DesignRequestIn

# Smallest comfortable areas (sq ft) from the minimum room sizes.
MASTER, BEDROOM, LIVING, KITCHEN, ATTACHED_BATH, COMMON_BATH = 132, 100, 154, 80, 40, 28
CIRCULATION = 1.15  # extra 15% for passages and walls
PARKING_AREA = {"No parking": 0, "Two-wheeler only": 42, "1 car": 180, "2 cars": 360}


def _required_area(bhk: str, bathrooms: int, parking: str) -> float:
    """Smallest total area (rooms + circulation + parking) a design needs."""
    bedrooms = 2 if bhk == "2BHK" else 3
    rooms = MASTER + (bedrooms - 1) * BEDROOM + LIVING + KITCHEN + ATTACHED_BATH + (bathrooms - 1) * COMMON_BATH
    return rooms * CIRCULATION + PARKING_AREA[parking]


def feasibility_hint(req: DesignRequestIn) -> str:
    """Return an empty string if the request fits, otherwise a sentence with the changes that would fix it."""
    floors = 1 if req.floors == "Ground Floor" else 2
    available = req.plot_width_ft * req.plot_length_ft * floors
    if _required_area(req.bhk_type, req.bathrooms, req.parking) <= available:
        return ""

    fixes = []
    if floors == 1 and _required_area(req.bhk_type, req.bathrooms, req.parking) <= available * 2:
        fixes.append("choose G+1")
    if req.parking == "2 cars" and _required_area(req.bhk_type, req.bathrooms, "1 car") <= available:
        fixes.append("reduce parking to 1 car")
    if req.bhk_type == "3BHK" and _required_area("2BHK", req.bathrooms, req.parking) <= available:
        fixes.append("choose 2BHK")
    if not fixes:
        fixes.append("use a larger plot or reduce parking, bathrooms or bedrooms")
    return (f"{req.bhk_type} with {req.bathrooms} bathrooms and '{req.parking}' on {req.floors} does not fit "
            f"a {req.plot_width_ft:g}x{req.plot_length_ft:g} ft plot without going below minimum room sizes. "
            f"To fix: {', or '.join(fixes)}.")


def plot_size_warning(req: DesignRequestIn) -> list[str]:
    """Warn (not block) when the plot size does not match width x length (more than 10% apart)."""
    area = req.plot_width_ft * req.plot_length_ft
    if abs(req.plot_size_sqft - area) / area > 0.10:
        return [f"Plot size {req.plot_size_sqft:g} sq ft does not match {req.plot_width_ft:g} x {req.plot_length_ft:g} ft "
                f"= {area:g} sq ft. The design uses the width x length."]
    return []


def build_user_prompt(req: DesignRequestIn, layout_hint: str, previous_errors: list[str] | None = None) -> str:
    """The per-concept prompt: requirements, layout strategy, and (on retry) what went wrong."""
    rate_min, rate_max = STYLE_RATES[req.style]
    lines = [
        "Design ONE house concept for this client.",
        f"- Plot: {req.plot_size_sqft:g} sq ft, {req.plot_width_ft:g} ft wide (x) by {req.plot_length_ft:g} ft long (y)",
        f"- Bedrooms: {req.bhk_type}",
        f"- Bathrooms (total): {req.bathrooms}",
        f"- Floors: {req.floors}",
        f"- Budget: INR {req.budget_inr:,}",
        f"- Style: {req.style} (construction rate about INR {rate_min}-{rate_max} per sq ft)",
        f"- Parking: {req.parking}",
        f"- Layout strategy for this concept: {layout_hint}",
        f"- Ground Floor arithmetic: the room widths in every band add up to exactly {req.plot_width_ft:g}, "
        f"and the band heights add up to exactly {req.plot_length_ft:g}.",
    ]
    hint = feasibility_hint(req)
    if hint:
        lines.append(f"FEASIBILITY WARNING: {hint} Put this advice in feasibility_note.")
    if previous_errors:
        lines.append("Your previous answer was rejected. Fix ALL of these problems and return the full JSON again:")
        lines += [f"  * {e}" for e in previous_errors[:12]]
    return "\n".join(lines)


def build_recommend_prompt(req: DesignRequestIn, concepts: list[Concept]) -> str:
    """Compact summary of all concepts so the recommendation call stays small."""
    summary = [{
        "index": i,
        "name": c.concept_name,
        "layout": c.layout_summary,
        "estimated_cost_inr": [c.budget_note.cost_min_inr, c.budget_note.cost_max_inr],
        "fits_budget": c.budget_note.fits_budget,
        "parking_impact": c.parking_impact,
        "advantages": c.advantages,
    } for i, c in enumerate(concepts)]
    return f"Requirements: {req.model_dump_json()}\nConcepts: {json.dumps(summary)}"


# What each image shows. Order matters: the gallery shows them in this order.
IMAGE_TYPES = ["exterior", "living_room", "bedroom", "kitchen"]
PARKING_IN_IMAGE = {
    "Two-wheeler only": "a small covered two-wheeler parking area at the front with a scooter parked",
    "1 car": "a covered car porch at the front with a sedan car parked inside",
    "2 cars": "a wide covered car porch at the front with two cars parked",
}


def build_image_prompts(req: DesignRequestIn, concept: Concept) -> dict[str, str]:
    """Build the 4 image prompts from the design JSON. All share the same style and colour words."""
    storeys = ("double-storey (ground plus one floor)" if req.floors == "G+1"
               else "single-storey bungalow with only a ground floor and no upper storey,")
    palette = concept.color_palette or "warm white and natural wood"
    identity = f"Style: {IMAGE_STYLE_WORDS[req.style]}. Colour palette: {palette}."
    tail = "Realistic, natural lighting, high detail, no text, no watermark."

    exterior = f"High-quality 3D architectural render of the front exterior of a {storeys} {req.style.lower()} Indian family house"
    if req.parking in PARKING_IN_IMAGE:  # parking is only mentioned when it was requested
        exterior += f", with {PARKING_IN_IMAGE[req.parking]}"
    interiors = {
        "living_room": "spacious living hall with a sofa set, TV unit, coffee table and large window",
        "bedroom": "master bedroom with a double bed, wardrobe, bedside tables and soft lighting",
        "kitchen": "modular kitchen with counters, cabinets, hob, chimney and a small dining area",
    }
    prompts = {"exterior": f"{exterior}. {identity} {tail}"}
    for kind, description in interiors.items():
        prompts[kind] = f"Photorealistic interior photograph of the {description} in a {req.style.lower()} Indian home. {identity} {tail}"
    return prompts
