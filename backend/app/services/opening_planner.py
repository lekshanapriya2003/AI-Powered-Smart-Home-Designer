"""opening_planner.py - places doors and windows from the room geometry.

LLMs cannot see the plan, so they put doors on outside walls and windows on inside walls.
Here the code does it: every door sits on a wall two rooms really share, and every window sits
on a piece of wall that faces outside. The LLM only chooses the rooms.
"""
from app.schemas import Opening, Room

MIN_WALL = 2.5    # ft of shared wall needed to fit a door
TOUCH = 0.05      # rooms closer than this (ft) count as touching
DOOR_MAIN, DOOR_ROOM, DOOR_BATH = 3.5, 3.0, 2.5
HUBS = ("living", "dining", "passage")
BATHROOMS = ("attached_bathroom", "common_bathroom")
WINDOW_ROOMS = ("living", "dining", "kitchen", "master_bedroom", "bedroom", "attached_bathroom", "common_bathroom")
TWO_WINDOWS = ("living", "master_bedroom", "bedroom")  # bigger rooms get a window on two walls when they can


def _shared_wall(a: Room, b: Room, minimum: float):
    """The wall two rooms share: (wall of a, wall of b, start, end), or None.

    start and end are plot positions along the wall (x for N/S walls, y for E/W walls).
    """
    ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.width, a.y + a.height
    bx1, by1, bx2, by2 = b.x, b.y, b.x + b.width, b.y + b.height
    for wall_a, wall_b, touching, lo, hi in (
        ("E", "W", abs(ax2 - bx1) < TOUCH, max(ay1, by1), min(ay2, by2)),
        ("W", "E", abs(ax1 - bx2) < TOUCH, max(ay1, by1), min(ay2, by2)),
        ("S", "N", abs(ay2 - by1) < TOUCH, max(ax1, bx1), min(ax2, bx2)),
        ("N", "S", abs(ay1 - by2) < TOUCH, max(ax1, bx1), min(ax2, bx2)),
    ):
        if touching and hi - lo >= minimum - TOUCH:
            return wall_a, wall_b, lo, hi
    return None


def _wall_start(room: Room, wall: str) -> float:
    """Plot position where a room's wall starts (left end of N/S walls, top end of E/W walls)."""
    return room.x if wall in ("N", "S") else room.y


def _outside_pieces(room: Room, rooms: list[Room]) -> dict[str, list[tuple[float, float]]]:
    """For each wall, the pieces no other room touches. Those pieces face the outside."""
    result = {}
    for wall in "NESW":
        start = _wall_start(room, wall)
        end = start + (room.width if wall in ("N", "S") else room.height)
        covered = []
        for other in rooms:
            shared = _shared_wall(room, other, TOUCH) if other is not room else None
            if shared and shared[0] == wall:
                covered.append((shared[2], shared[3]))
        free, cursor = [], start
        for lo, hi in sorted(covered):
            if lo - cursor > TOUCH:
                free.append((cursor, lo))
            cursor = max(cursor, hi)
        if end - cursor > TOUCH:
            free.append((cursor, end))
        result[wall] = free
    return result


def _subtract(pieces, cuts, margin):
    """Remove the cut intervals (plus a margin) from the pieces."""
    for c_lo, c_hi in cuts:
        remaining = []
        for a, b in pieces:
            if c_hi + margin <= a or c_lo - margin >= b:
                remaining.append((a, b))
                continue
            if c_lo - margin > a:
                remaining.append((a, c_lo - margin))
            if c_hi + margin < b:
                remaining.append((c_hi + margin, b))
        pieces = remaining
    return pieces


def _opening(room: Room, wall: str, lo: float, hi: float, preferred: float, kind: str = "internal") -> Opening:
    """An opening centred on the stretch [lo, hi] of the room's wall, narrower if the stretch is short."""
    width = min(preferred, hi - lo - 0.3)
    offset = (lo + hi) / 2 - width / 2 - _wall_start(room, wall)
    return Opening(room=room.name, wall=wall, offset=round(offset, 2), width=round(width, 2), kind=kind)


def _parent_rank(child: Room, parent: Room, hubs: set) -> int:
    """How good a room is to open into the child (lower is better): hubs first, bedrooms last."""
    if parent.type in hubs:
        return 0
    rank = {"staircase": 1, "kitchen": 2, "utility": 2}.get(parent.type, 3)
    if child.type in BATHROOMS and parent.type == "kitchen":
        rank += 2  # a bathroom should not open off the kitchen
    return rank


def _connect_rooms(rooms: list[Room], floor_name: str, errors: list[str]) -> list[Opening]:
    """Give every room one door, to a room that is already reachable from the living hall (or the stairs)."""
    start = [r for r in rooms if r.type == "living"] or [r for r in rooms if r.type == "staircase"]
    if not start:
        errors.append(f"{floor_name}: there is no living hall or staircase to connect the rooms to.")
        return []
    hubs = set(HUBS) | (set() if any(r.type == "living" for r in rooms) else {"staircase"})
    connected, doors = list(start), []
    phases = ([r for r in rooms if r not in start and r.type not in BATHROOMS],  # rooms first, bathrooms after
              [r for r in rooms if r.type in BATHROOMS])
    leftovers = []
    for pending in phases:
        pending = list(pending)
        while pending:
            options = []
            for child in pending:
                for parent in connected:
                    if parent.type in BATHROOMS or (child.type == "attached_bathroom" and parent.type != "master_bedroom"):
                        continue
                    wall = _shared_wall(child, parent, MIN_WALL)
                    if wall:
                        options.append((_parent_rank(child, parent, hubs), -(wall[3] - wall[2]), rooms.index(child), child, wall))
            if not options:
                break
            _, _, _, child, (wall_name, _, lo, hi) = min(options, key=lambda o: o[:3])
            doors.append(_opening(child, wall_name, lo, hi, DOOR_BATH if child.type in BATHROOMS else DOOR_ROOM))
            connected.append(child)
            pending.remove(child)
        leftovers += pending

    for room in leftovers:
        if room.type == "attached_bathroom":
            errors.append(f"The attached bathroom '{room.name}' must share a wall (at least {MIN_WALL:g} ft) with the master bedroom. "
                          f"Put it right next to the master bedroom.")
        elif room.type not in ("staircase", "utility"):
            errors.append(f"{floor_name}: '{room.name}' does not share a wall (at least {MIN_WALL:g} ft) with any room it can open "
                          f"into, so it cannot have a door. Place it next to the living hall or another room.")
    return doors


def _main_door(rooms: list[Room], plot_length: float, floor_name: str, errors: list[str]) -> Opening | None:
    """The entrance: on the living hall's road-side wall, or on its longest outside wall if it is not on the road."""
    living = [r for r in rooms if r.type == "living"]
    if not living:
        return None  # the validator reports the missing living hall
    room = max(living, key=lambda r: r.width * r.height)
    if abs(room.y + room.height - plot_length) < 0.5:
        return _opening(room, "S", room.x, room.x + room.width, DOOR_MAIN, "main")
    pieces = [(hi - lo, wall, lo, hi) for wall, items in _outside_pieces(room, rooms).items() for lo, hi in items]
    if not pieces:
        errors.append(f"{floor_name}: the living hall has no outside wall for the main entrance.")
        return None
    _, wall, lo, hi = max(pieces)
    return _opening(room, wall, lo, hi, DOOR_MAIN, "main")


def _windows(rooms: list[Room], doors: list[Opening]) -> list[Opening]:
    """One window per room on its longest outside wall piece (two for bigger rooms), kept clear of doors."""
    windows = []
    for room in rooms:
        if room.type not in WINDOW_ROOMS:
            continue
        pieces = []
        for wall, items in _outside_pieces(room, rooms).items():
            start = _wall_start(room, wall)
            cuts = [(start + d.offset, start + d.offset + d.width) for d in doors if d.room == room.name and d.wall == wall]
            pieces += [(hi - lo, wall, lo, hi) for lo, hi in _subtract(items, cuts, 0.4) if hi - lo >= 2.0]
        used = set()
        for length, wall, lo, hi in sorted(pieces, reverse=True):
            if len(used) >= (2 if room.type in TWO_WINDOWS else 1):
                break
            if wall not in used:
                used.add(wall)
                windows.append(_opening(room, wall, lo, hi, 2.0 if room.type in BATHROOMS else 4.0))
    return windows


def plan_openings(rooms: list[Room], floor_name: str, plot_length: float, is_ground: bool):
    """Returns (doors, windows, error messages) for one floor."""
    errors: list[str] = []
    doors = _connect_rooms(rooms, floor_name, errors)
    if is_ground:
        main = _main_door(rooms, plot_length, floor_name, errors)
        if main:
            doors.append(main)
    return doors, _windows(rooms, doors), errors
