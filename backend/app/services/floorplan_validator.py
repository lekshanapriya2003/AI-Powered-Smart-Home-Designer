"""floorplan_validator.py - checks an LLM floor plan against the user's requirements.

LLMs often draw overlapping rooms or forget a bedroom, so every plan is checked here.
Each check returns plain-English errors that are fed back to the LLM on retry.
"""
from app.schemas import Concept, DesignRequestIn, Floor

EDGE = 0.1           # ft of slack for rounding when checking bounds and overlaps
SIZE_TOLERANCE = 0.5  # ft of slack on minimum sizes (the brief says "approximate")
GROUND_FILL_MIN = 0.70  # rooms + parking should cover at least 70% of the plot
UPPER_FILL_MIN = 0.35   # upper floors are allowed to be smaller
ROAD_EDGE_TOLERANCE = 2.0  # parking must touch the road (bottom) edge within this

# (short side, long side) minimums in feet, from the brief
MIN_SIZES = {
    "master_bedroom": (11, 12), "bedroom": (10, 10), "living": (11, 14),
    "kitchen": (8, 10), "attached_bathroom": (5, 8), "common_bathroom": (4, 7),
}
# Allowed (width, height) minimums per parking type. Rotated versions are accepted too.
PARKING_MIN = {"two_wheeler": [(6, 7), (3, 14)], "1_car": [(10, 18)], "2_cars": [(20, 18), (10, 36)]}
PARKING_CODE = {"Two-wheeler only": "two_wheeler", "1 car": "1_car", "2 cars": "2_cars"}
BEDROOM_TYPES = ("master_bedroom", "bedroom")
BATHROOM_TYPES = ("attached_bathroom", "common_bathroom")


def _fits(w: float, h: float, min_a: float, min_b: float) -> bool:
    """True if a w x h rectangle can hold min_a x min_b in either orientation."""
    t = SIZE_TOLERANCE
    return (w >= min_a - t and h >= min_b - t) or (w >= min_b - t and h >= min_a - t)


def _overlap(a: tuple, b: tuple) -> bool:
    """True if two (name, x, y, w, h) rectangles share real area (touching walls is fine)."""
    ox = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    oy = min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2])
    return ox > EDGE and oy > EDGE


def _count(concept: Concept, types: tuple) -> int:
    """Count rooms of the given types across all floors."""
    return sum(1 for f in concept.floors for r in f.rooms if r.type in types)


def _size_hint(room, lo: float, hi: float) -> str:
    """Say which dimension to change. A room is its width x its band height, so the height is fixed by the band."""
    if room.height >= hi:
        return f"Make its width at least {lo:g} ft."
    if room.height >= lo:
        return f"Make its width at least {hi:g} ft."
    return f"Raise its band height to at least {lo:g} ft and its width to at least {hi:g} ft."


def check_floors(concept: Concept, req: DesignRequestIn) -> list[str]:
    """Floor count and names must match the requested number of floors."""
    expected = ["Ground Floor"] if req.floors == "Ground Floor" else ["Ground Floor", "First Floor"]
    actual = [f.name for f in concept.floors]
    errors = []
    if actual != expected:
        errors.append(f"'floors' must contain exactly these plans in order: {expected}, got {actual}.")
    if concept.bhk_type != req.bhk_type:
        errors.append(f"bhk_type must be {req.bhk_type}, got {concept.bhk_type}.")
    return errors


def check_floor_geometry(floor: Floor, parking, req: DesignRequestIn) -> list[str]:
    """Rooms (and parking on the ground floor) must be inside the plot, not overlap, and meet minimum sizes."""
    errors = []
    rects = [(r.name, r.x, r.y, r.width, r.height) for r in floor.rooms]
    if parking:
        rects.append(("Parking", parking.x, parking.y, parking.width, parking.height))

    names = [r.name for r in floor.rooms]
    if len(set(names)) != len(names):
        errors.append(f"{floor.name}: room names must be unique.")
    for name, x, y, w, h in rects:
        if x < -EDGE or y < -EDGE or x + w > req.plot_width_ft + EDGE or y + h > req.plot_length_ft + EDGE:
            errors.append(f"{floor.name}: '{name}' ({x},{y},{w}x{h}) is outside the {req.plot_width_ft:g}x{req.plot_length_ft:g} ft plot.")
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if _overlap(a, b):
                errors.append(f"{floor.name}: '{a[0]}' overlaps '{b[0]}'.")
    for r in floor.rooms:
        if r.type in MIN_SIZES and not _fits(r.width, r.height, *MIN_SIZES[r.type]):
            lo, hi = MIN_SIZES[r.type]
            errors.append(f"{floor.name}: '{r.name}' is {r.width:g}x{r.height:g} ft, below the minimum {lo}x{hi} ft. "
                          f"{_size_hint(r, lo, hi)}")
    return errors


def check_room_counts(concept: Concept, req: DesignRequestIn) -> list[str]:
    """Bedrooms must equal the BHK, bathrooms must match the form, and key rooms must exist."""
    errors = []
    wanted_beds = 2 if req.bhk_type == "2BHK" else 3
    beds = _count(concept, BEDROOM_TYPES)
    masters = _count(concept, ("master_bedroom",))
    if beds != wanted_beds:
        errors.append(f"{req.bhk_type} needs exactly {wanted_beds} bedrooms, the plan has {beds}.")
    if masters != 1:
        errors.append(f"There must be exactly 1 master_bedroom, the plan has {masters}.")
    baths = _count(concept, BATHROOM_TYPES)
    if baths != req.bathrooms:
        errors.append(f"The form asks for {req.bathrooms} bathrooms, the plan has {baths}.")
    if _count(concept, ("attached_bathroom",)) != 1:
        errors.append("There must be exactly 1 attached_bathroom (for the master bedroom); the rest are common_bathroom.")

    ground_types = {r.type for r in concept.floors[0].rooms}
    for needed in ("living", "kitchen"):
        if needed not in ground_types:
            errors.append(f"Ground Floor is missing a '{needed}' room.")
    if len(concept.floors) == 1 and "staircase" in ground_types:
        errors.append("A Ground Floor only plan must not have a staircase. Remove it.")
    if len(concept.floors) == 2:
        for f in concept.floors:
            if "staircase" not in {r.type for r in f.rooms}:
                errors.append(f"{f.name} needs a staircase room at the same position on both floors.")
    return errors


def check_parking(concept: Concept, req: DesignRequestIn) -> list[str]:
    """Parking must exist only when requested, meet the minimum size and touch the road edge."""
    requested = PARKING_CODE.get(req.parking)
    p = concept.parking
    if requested is None:
        return ["Parking was not requested, so 'parking' must be null."] if p else []
    if p is None:
        return [f"Parking '{req.parking}' was requested but 'parking' is null."]

    errors = []
    # With a feasibility_note the LLM may legitimately offer a smaller parking type.
    if p.type != requested and not concept.feasibility_note:
        errors.append(f"parking.type must be '{requested}', got '{p.type}'.")
    if not any(_fits(p.width, p.height, *opt) for opt in PARKING_MIN[p.type]):
        errors.append(f"Parking is {p.width:g}x{p.height:g} ft but '{p.type}' needs at least one of {PARKING_MIN[p.type]}.")
    if abs(req.plot_length_ft - (p.y + p.height)) > ROAD_EDGE_TOLERANCE:
        errors.append("Parking must touch the road (bottom) edge: y + height should equal the plot length.")
    return errors


def check_openings(concept: Concept) -> list[str]:
    """Doors and windows must sit on a real room wall; the ground floor needs a main door."""
    errors = []
    for i, floor in enumerate(concept.floors):
        rooms = {r.name: r for r in floor.rooms}
        for label, items in (("door", floor.doors), ("window", floor.windows)):
            for o in items:
                room = rooms.get(o.room)
                if room is None:
                    errors.append(f"{floor.name}: a {label} refers to unknown room '{o.room}'.")
                    continue
                wall_len = room.width if o.wall in ("N", "S") else room.height
                if o.offset + o.width > wall_len + EDGE:
                    errors.append(f"{floor.name}: {label} on {o.room} wall {o.wall} runs past the wall ({wall_len:g} ft long).")
        if i == 0 and not any(d.kind == "main" for d in floor.doors):
            errors.append("Ground Floor needs one door with kind 'main'.")
    return errors


def check_area(concept: Concept, req: DesignRequestIn) -> list[str]:
    """Total used area should be close to the plot area (skipped for infeasible requests)."""
    if concept.feasibility_note:
        return []
    plot_area = req.plot_width_ft * req.plot_length_ft
    errors = []
    for i, floor in enumerate(concept.floors):
        used = sum(r.width * r.height for r in floor.rooms)
        if i == 0 and concept.parking:
            used += concept.parking.width * concept.parking.height
        minimum = GROUND_FILL_MIN if i == 0 else UPPER_FILL_MIN
        if used < minimum * plot_area:
            errors.append(f"{floor.name} uses only {used:.0f} sq ft of {plot_area:.0f}; fill at least {minimum:.0%} of the plot.")
    return errors


def validate_concept(concept: Concept, req: DesignRequestIn) -> list[str]:
    """Run every check and return all error messages (empty list means the plan is valid)."""
    errors = check_floors(concept, req)
    if len(concept.floors) != (1 if req.floors == "Ground Floor" else 2):
        return errors  # the other checks assume the right number of floors
    for i, floor in enumerate(concept.floors):
        errors += check_floor_geometry(floor, concept.parking if i == 0 else None, req)
    errors += check_room_counts(concept, req)
    errors += check_parking(concept, req)
    errors += check_openings(concept)
    errors += check_area(concept, req)
    return errors


def layout_signature(concept: Concept, req: DesignRequestIn) -> tuple:
    """Kitchen zone (back/middle/front third), kitchen side (left/right) and parking side.

    Used to make sure the 3 concepts really differ, not just in their names.
    """
    kitchen = next((r for r in concept.floors[0].rooms if r.type == "kitchen"), None)
    zone = side = None
    if kitchen:
        centre_y = kitchen.y + kitchen.height / 2
        zone = 0 if centre_y < req.plot_length_ft / 3 else (1 if centre_y < 2 * req.plot_length_ft / 3 else 2)
        side = kitchen.x + kitchen.width / 2 < req.plot_width_ft / 2
    p = concept.parking
    parking_side = None if p is None else (p.x + p.width / 2 < req.plot_width_ft / 2)
    return (zone, side, parking_side)
