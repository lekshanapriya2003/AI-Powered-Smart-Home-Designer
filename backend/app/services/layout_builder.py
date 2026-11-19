"""layout_builder.py - turns the LLM's band layout into rooms with x/y coordinates.

LLMs are weak at coordinate arithmetic (rooms outside the plot, overlaps, widths that do not
add up). So the LLM only chooses rows ("bands") and widths, and this code places them. Rooms
in a band sit side by side and bands stack top to bottom, so rooms can never overlap. Small
arithmetic slips are repaired here instead of costing a retry, and doors and windows are placed from
the geometry (see opening_planner.py). The LLM decides, the code guarantees.
"""
import re

from app.schemas import Concept, ConceptDraft, DesignRequestIn, Floor, FloorDraft, Parking, Room
from app.services.floorplan_validator import MIN_SIZES, PARKING_MIN
from app.services.opening_planner import plan_openings

TOLERANCE = 0.1     # ft of slack for rounding
NO_MINIMUM = 3.0    # staircase, utility and similar rooms: just keep them from collapsing


def _sum_text(values: list[float]) -> str:
    """Show an addition the way the LLM should check it, e.g. "12 + 10 + 36 = 58"."""
    return " + ".join(f"{v:g}" for v in values) + f" = {sum(values):g}"


def _min_pairs(item_type: str, parking_type: str | None) -> list[tuple[float, float]]:
    """The allowed (short, long) minimum sizes of a room or parking area (empty if it has no minimum)."""
    if item_type == "parking":
        return PARKING_MIN.get(parking_type or "", [])
    return [MIN_SIZES[item_type]] if item_type in MIN_SIZES else []


def _minimum(item_type: str, parking_type: str | None, other_side: float) -> float:
    """Smallest value for one side of a room so it still meets its minimum size, given the other side.

    Minimums are (short, long) pairs and a room may be turned either way round.
    """
    options = _min_pairs(item_type, parking_type)
    if not options:
        return NO_MINIMUM
    return min(short if other_side >= long else long for short, long in options)


def _required_height(items, parking_type: str | None, plot_w: float) -> float | None:
    """Smallest band height at which the rooms' minimum widths fit inside the plot width.

    A room needs less width when its band is taller (a master bedroom needs 12 ft in an 11 ft band
    but 11 ft in a 12 ft band), so a band that is "1 ft too narrow" is fixed by making it taller.
    Returns None if the rooms cannot fit side by side at any height.
    """
    pairs = [_min_pairs(i.type, parking_type) for i in items]
    floor_h = max([NO_MINIMUM] + [min(short for short, _ in p) for p in pairs if p])
    heights = sorted({floor_h} | {v for p in pairs for pair in p for v in pair if v >= floor_h})
    for h in heights:  # the width a room needs only changes at these heights
        if sum(_minimum(i.type, parking_type, h) for i in items) <= plot_w + TOLERANCE:
            return h
    return None


def _fit_total(sizes: list[float], minimums: list[float], can_grow: list[bool], target: float, fill: bool):
    """Adjust sizes so they add up to target without going below any minimum. Returns None if impossible.

    Too small a total grows the biggest growable item. Too big a total shrinks the item with the
    most spare room, 1 ft at a time. With fill=False the total may stay below the target.
    """
    sizes = [max(s, m) for s, m in zip(sizes, minimums)]
    extra = sum(sizes) - target
    if extra < -TOLERANCE and fill:
        growable = [i for i, ok in enumerate(can_grow) if ok]
        if not growable:
            return None
        sizes[max(growable, key=lambda i: sizes[i])] -= extra  # extra is negative, so this adds
    while extra > TOLERANCE:
        spare = [s - m for s, m in zip(sizes, minimums)]
        i = max(range(len(sizes)), key=lambda k: spare[k])
        if spare[i] <= TOLERANCE:
            return None
        step = min(1.0, extra, spare[i])
        sizes[i] -= step
        extra -= step
    return [round(s, 2) for s in sizes]


def _unique_name(name: str, used: set) -> str:
    """Two rooms with the same name would confuse the drawing and the table, so number the second one."""
    candidate, count = name, 1
    while candidate in used:
        count += 1
        candidate = f"{name} {count}"
    used.add(candidate)
    return candidate


def _strip_sizes(text: str) -> str:
    """Remove quoted room sizes such as "12x12" or "(11' x 14')". The size table shows the real numbers."""
    size = r"\d+(?:\.\d+)?\s*(?:ft|feet|')?\s*[x×*]\s*\d+(?:\.\d+)?\s*(?:ft|feet|')?"
    text = re.sub(r"\s*\(\s*" + size + r"\s*\)", "", text)
    text = re.sub(size, "", text)
    return re.sub(r"\s{2,}", " ", text).replace(" ,", ",").replace(" .", ".").strip()


def place_floor(draft: FloorDraft, req: DesignRequestIn, is_ground: bool, relaxed: bool, parking_type: str | None):
    """Repair and place one floor's bands. Returns (Floor, parking rectangle or None, error messages)."""
    plot_w, plot_l = req.plot_width_ft, req.plot_length_ft
    fill = is_ground and not relaxed  # these floors must fill the plot exactly
    errors = []

    # 1. Band heights: each band must be tall enough for its rooms to fit the plot width, and the bands must add up to the plot.
    heights = [band.height for band in draft.bands]
    required = [_required_height(band.rooms, parking_type, plot_w) for band in draft.bands]
    for number, (band, need) in enumerate(zip(draft.bands, required), start=1):
        if need is None:
            tightest = sum(_minimum(i.type, parking_type, plot_l) for i in band.rooms)
            errors.append(f"{draft.name}, band {number}: these rooms need at least {tightest:g} ft of width but the plot is "
                          f"{plot_w:g} ft wide (you gave {_sum_text([i.width for i in band.rooms])}). Move a room to another band.")
    if None not in required:
        fitted = _fit_total(heights, required, [True] * len(heights), plot_l, fill)
        if fitted is None:
            errors.append(f"{draft.name}: the bands need at least {sum(required):g} ft of height ({_sum_text(required)} for "
                          f"bands 1 to {len(required)}) but the plot is {plot_l:g} ft long. Use fewer bands (3 usually works) "
                          f"or move rooms into a band that is already tall enough.")
        else:
            heights = fitted

    # 2. Room widths inside each band, using the final band height.
    rooms, parking, y, used_names = [], None, 0.0, set()
    for number, (band, height) in enumerate(zip(draft.bands, heights), start=1):
        widths = [i.width for i in band.rooms]
        mins = [_minimum(i.type, parking_type, height) for i in band.rooms]
        fitted = _fit_total(widths, mins, [i.type != "parking" for i in band.rooms], plot_w, fill)
        if fitted is None:
            errors.append(f"{draft.name}, band {number}: these rooms need at least {sum(mins):g} ft of width but the plot is "
                          f"{plot_w:g} ft wide (you gave {_sum_text(widths)}). Move a room to another band.")
        else:
            widths = fitted
        x = 0.0
        for item, width in zip(band.rooms, widths):
            if item.type == "parking":
                if not is_ground:
                    errors.append(f"{draft.name}: parking belongs on the Ground Floor only.")
                elif parking is not None:
                    errors.append("Only one band item may have type 'parking'.")
                else:
                    parking = (x, y, width, height)
            else:
                rooms.append(Room(name=_unique_name(item.name, used_names), type=item.type, x=x, y=y, width=width, height=height))
            x += width
        y += height

    doors, windows, opening_errors = plan_openings(rooms, draft.name, plot_l, is_ground)
    errors += opening_errors
    floor = Floor(name=draft.name, rooms=rooms, doors=doors, windows=windows)
    return floor, parking, errors


def build_concept(draft: ConceptDraft, req: DesignRequestIn) -> tuple[Concept | None, list[str]]:
    """Convert a band draft into a Concept. Returns (concept, []) or (None, error messages)."""
    relaxed = bool(draft.feasibility_note)  # an infeasible request may leave part of the plot empty
    floors, parking_rect, errors = [], None, []
    for index, floor_draft in enumerate(draft.floors):
        floor, rect, floor_errors = place_floor(floor_draft, req, index == 0, relaxed, draft.parking_type)
        floors.append(floor)
        errors += floor_errors
        if index == 0:
            parking_rect = rect

    if draft.parking_type and parking_rect is None:
        errors.append(f"parking_type is '{draft.parking_type}' but no Ground Floor band item has type 'parking'.")
    if parking_rect and not draft.parking_type:
        errors.append("A band item has type 'parking' but parking_type is null.")
    if errors:
        return None, errors

    parking = None
    if parking_rect:
        x, y, w, h = parking_rect
        parking = Parking(type=draft.parking_type, x=x, y=y, width=w, height=h)
    fields = draft.model_dump(exclude={"floors", "parking_type"})
    for key in ("layout_summary", "space_utilization", "parking_impact"):
        fields[key] = _strip_sizes(fields[key])
    fields["advantages"] = [_strip_sizes(a) for a in fields["advantages"]]
    fields["budget_note"]["note"] = _strip_sizes(fields["budget_note"]["note"])
    return Concept(**fields, floors=floors, parking=parking), []
