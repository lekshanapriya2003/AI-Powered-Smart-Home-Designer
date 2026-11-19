"""test_opening_planner.py - doors and windows must come from the room geometry, never from the LLM."""
from app.schemas import ConceptDraft
from app.services.floorplan_validator import validate_concept
from app.services.layout_builder import build_concept
from app.services.opening_planner import _outside_pieces, _shared_wall, plan_openings
from tests.test_floorplan_validator import req
from tests.test_layout_builder import draft_2bhk, item


def built(draft=None, request=None):
    """Build a concept from a band draft and return it (the draft must be valid)."""
    concept, errors = build_concept(ConceptDraft.model_validate(draft or draft_2bhk()), request or req())
    assert errors == [], errors
    return concept


def point_outside(room, door):
    """A point just outside the room, in front of the middle of the door or window."""
    mid = door.offset + door.width / 2
    if door.wall == "N": return room.x + mid, room.y - 0.3
    if door.wall == "S": return room.x + mid, room.y + room.height + 0.3
    if door.wall == "W": return room.x - 0.3, room.y + mid
    return room.x + room.width + 0.3, room.y + mid


def room_at(rooms, x, y):
    """The room that contains a point, or None."""
    return next((r for r in rooms if r.x < x < r.x + r.width and r.y < y < r.y + r.height), None)


def test_every_internal_door_opens_into_a_neighbouring_room():
    concept = built()
    rooms = {r.name: r for r in concept.floors[0].rooms}
    for door in concept.floors[0].doors:
        if door.kind != "main":
            assert room_at(rooms.values(), *point_outside(rooms[door.room], door)) is not None, door


def test_only_the_main_door_faces_outside():
    concept = built()
    rooms = {r.name: r for r in concept.floors[0].rooms}
    outside = [d for d in concept.floors[0].doors if room_at(rooms.values(), *point_outside(rooms[d.room], d)) is None]
    assert [d.kind for d in outside] == ["main"]


def test_main_door_is_on_the_road_side_of_the_living_hall():
    main = next(d for d in built().floors[0].doors if d.kind == "main")
    assert main.room == "Living Hall" and main.wall == "S"


def test_windows_only_on_outside_walls():
    concept = built()
    rooms = {r.name: r for r in concept.floors[0].rooms}
    assert concept.floors[0].windows
    for window in concept.floors[0].windows:
        assert room_at(rooms.values(), *point_outside(rooms[window.room], window)) is None, window


def test_windows_do_not_overlap_doors_of_the_same_room():
    concept = built()
    for window in concept.floors[0].windows:
        for door in concept.floors[0].doors:
            if door.room == window.room and door.wall == window.wall:
                assert window.offset + window.width <= door.offset or door.offset + door.width <= window.offset


def test_attached_bathroom_opens_into_the_master_bedroom():
    concept = built()
    door = next(d for d in concept.floors[0].doors if d.room == "Master Bath")
    rooms = {r.name: r for r in concept.floors[0].rooms}
    assert room_at(rooms.values(), *point_outside(rooms["Master Bath"], door)).name == "Master Bedroom"


def test_every_room_can_be_reached_from_the_living_hall():
    concept = built()
    rooms = {r.name: r for r in concept.floors[0].rooms}
    links = {r: set() for r in rooms}
    for d in concept.floors[0].doors:
        if d.kind != "main":
            other = room_at(rooms.values(), *point_outside(rooms[d.room], d)).name
            links[d.room].add(other); links[other].add(d.room)
    seen, todo = {"Living Hall"}, ["Living Hall"]
    while todo:
        for nxt in links[todo.pop()] - seen:
            seen.add(nxt); todo.append(nxt)
    assert seen == set(rooms)


def test_attached_bathroom_that_does_not_touch_the_master_bedroom_is_rejected():
    draft = draft_2bhk()
    bands = draft["floors"][0]["bands"]
    # the attached bath moves to x 14..25 under Bedroom 2, away from the master bedroom (x 0..12)
    bands[1]["rooms"] = [item("Common Bath", "common_bathroom", 6), item("Kitchen", "kitchen", 8), item("Master Bath", "attached_bathroom", 11)]
    concept, errors = build_concept(ConceptDraft.model_validate(draft), req())
    assert concept is None and any("must share a wall" in e and "master bedroom" in e for e in errors)


def test_first_floor_rooms_connect_through_the_stairs():
    ground = {"name": "Ground Floor", "bands": [
        {"height": 12, "rooms": [item("Master Bedroom", "master_bedroom", 12), item("Staircase", "staircase", 5), item("Utility", "utility", 8)]},
        {"height": 10, "rooms": [item("Master Bath", "attached_bathroom", 6), item("Common Bath", "common_bathroom", 6), item("Kitchen", "kitchen", 13)]},
        {"height": 18, "rooms": [item("Car Parking", "parking", 10), item("Living Hall", "living", 15)]}]}
    first = {"name": "First Floor", "bands": [
        {"height": 14, "rooms": [item("Bedroom 2", "bedroom", 12), item("Staircase", "staircase", 5)]},
        {"height": 14, "rooms": [item("Bedroom 3", "bedroom", 12)]}]}
    draft = {**draft_2bhk(), "bhk_type": "3BHK", "floors": [ground, first]}
    concept = built(draft, req(bhk_type="3BHK", floors="G+1"))
    upper = concept.floors[1]
    assert {d.room for d in upper.doors} >= {"Bedroom 2", "Bedroom 3"}
    assert all(d.kind != "main" for d in upper.doors)  # the entrance is only on the ground floor
    assert validate_concept(concept, req(bhk_type="3BHK", floors="G+1")) == []


def test_shared_wall_and_outside_pieces():
    concept = built()
    rooms = {r.name: r for r in concept.floors[0].rooms}
    wall = _shared_wall(rooms["Kitchen"], rooms["Living Hall"], 2.5)
    assert wall[0] == "S" and wall[1] == "N" and (wall[2], wall[3]) == (12, 25)
    assert _outside_pieces(rooms["Master Bedroom"], list(rooms.values()))["N"] == [(0, 12)]  # the whole north wall faces out


def test_a_plan_without_a_living_hall_or_stairs_reports_it():
    concept = built()
    rooms = [r for r in concept.floors[0].rooms if r.type != "living"]
    _, _, errors = plan_openings(rooms, "Ground Floor", 40, True)
    assert any("no living hall or staircase" in e for e in errors)


def test_converted_plan_with_planned_openings_passes_the_validator():
    assert validate_concept(built(), req()) == []
