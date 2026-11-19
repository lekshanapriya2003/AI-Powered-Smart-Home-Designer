"""test_floorplan_validator.py - unit tests for the floor plan rules.

Run from the backend folder:  pytest -v
The plans below are small hand-made fixtures on a 25 x 40 ft plot (y=40 is the road side).
"""
import copy

from app.schemas import Concept, DesignRequestIn
from app.services.floorplan_validator import validate_concept


def room(name, type_, x, y, w, h):
    """Shortcut to build a room dict."""
    return {"name": name, "type": type_, "x": x, "y": y, "width": w, "height": h}


def door(room_name, wall, offset, kind="internal"):
    """Shortcut to build a 3 ft door dict."""
    return {"room": room_name, "wall": wall, "offset": offset, "width": 3, "kind": kind}


def window(room_name, wall, offset):
    """Shortcut to build a 3 ft window dict."""
    return {"room": room_name, "wall": wall, "offset": offset, "width": 3}


def make_plan(floors, parking=None, bhk="2BHK"):
    """Wrap floors into a full concept dict with the text fields the schema needs."""
    return {"concept_name": "Test", "bhk_type": bhk, "layout_summary": "x", "space_utilization": "x",
            "parking_impact": "x", "floors": floors, "parking": parking, "advantages": ["x"]}


def req(**changes):
    """A 2BHK, 2 bathroom, ground floor, 1 car request on a 25x40 plot, with overrides."""
    values = dict(plot_size_sqft=1000, plot_width_ft=25, plot_length_ft=40, bhk_type="2BHK", bathrooms=2,
                  floors="Ground Floor", budget_inr=3000000, style="Modern", parking="1 car")
    values.update(changes)
    return DesignRequestIn(**values)


def plan_2bhk():
    """Valid 2BHK + 1 car parking plan, ground floor only. Rooms tile the 25x40 plot exactly."""
    ground = {"name": "Ground Floor", "rooms": [
        room("Master Bedroom", "master_bedroom", 0, 0, 12, 13),
        room("Bedroom 2", "bedroom", 12, 0, 13, 12),
        room("Master Bath", "attached_bathroom", 0, 13, 6, 9),
        room("Common Bath", "common_bathroom", 6, 13, 6, 9),
        room("Kitchen", "kitchen", 12, 12, 13, 10),
        room("Living Hall", "living", 10, 22, 15, 18),
    ], "doors": [door("Living Hall", "S", 6, "main"), door("Master Bedroom", "S", 7), door("Bedroom 2", "S", 5),
                 door("Master Bath", "N", 1), door("Common Bath", "S", 1), door("Kitchen", "S", 5)],
        "windows": [window("Master Bedroom", "N", 4), window("Bedroom 2", "N", 4), window("Kitchen", "E", 3)]}
    return make_plan([ground], {"type": "1_car", "x": 0, "y": 22, "width": 10, "height": 18})


def plan_3bhk():
    """Valid 3BHK, no parking, ground floor on a 30x40 plot."""
    ground = {"name": "Ground Floor", "rooms": [
        room("Master Bedroom", "master_bedroom", 0, 0, 15, 12),
        room("Bedroom 2", "bedroom", 15, 0, 15, 12),
        room("Master Bath", "attached_bathroom", 0, 12, 6, 10),
        room("Common Bath", "common_bathroom", 6, 12, 5, 10),
        room("Bedroom 3", "bedroom", 11, 12, 10, 10),
        room("Kitchen", "kitchen", 21, 12, 9, 10),
        room("Living Hall", "living", 0, 22, 30, 18),
    ], "doors": [door("Living Hall", "S", 12, "main"), door("Master Bedroom", "S", 2), door("Bedroom 2", "S", 5),
                 door("Master Bath", "S", 1), door("Common Bath", "S", 1), door("Bedroom 3", "S", 3),
                 door("Kitchen", "S", 3)],
        "windows": [window("Master Bedroom", "N", 4), window("Bedroom 2", "N", 4), window("Kitchen", "E", 3)]}
    return make_plan([ground], None, "3BHK")


def req_3bhk(**changes):
    """3BHK request matching plan_3bhk."""
    return req(plot_size_sqft=1200, plot_width_ft=30, bhk_type="3BHK", parking="No parking", **changes)


def plan_g_plus_1():
    """Valid 3BHK G+1 plan with 1 car parking on the 25x40 plot."""
    ground = {"name": "Ground Floor", "rooms": [
        room("Master Bedroom", "master_bedroom", 0, 0, 12, 13),
        room("Staircase", "staircase", 12, 0, 5, 12),
        room("Utility", "utility", 17, 0, 8, 12),
        room("Master Bath", "attached_bathroom", 0, 13, 6, 9),
        room("Common Bath", "common_bathroom", 6, 13, 6, 9),
        room("Kitchen", "kitchen", 12, 12, 13, 10),
        room("Living Hall", "living", 10, 22, 15, 18),
    ], "doors": [door("Living Hall", "S", 6, "main"), door("Master Bedroom", "S", 7), door("Master Bath", "N", 1),
                 door("Common Bath", "S", 1), door("Kitchen", "S", 5), door("Utility", "S", 2)],
        "windows": [window("Master Bedroom", "N", 4), window("Kitchen", "E", 3)]}
    first = {"name": "First Floor", "rooms": [
        room("Bedroom 2", "bedroom", 0, 0, 12, 14),
        room("Bedroom 3", "bedroom", 0, 14, 12, 14),
        room("Staircase", "staircase", 12, 0, 5, 12),
    ], "doors": [door("Bedroom 2", "E", 5), door("Bedroom 3", "E", 5)],
        "windows": [window("Bedroom 2", "N", 4), window("Bedroom 3", "S", 4)]}
    return make_plan([ground, first], {"type": "1_car", "x": 0, "y": 22, "width": 10, "height": 18}, "3BHK")


def errors_for(plan, request):
    """Validate a plan dict against a request and return the error list."""
    return validate_concept(Concept.model_validate(plan), request)


def bedroom_count(plan):
    """Count bedroom rooms across all floors of a plan dict."""
    return sum(1 for f in plan["floors"] for r in f["rooms"] if r["type"] in ("master_bedroom", "bedroom"))


def has_error(errors, text):
    """True if any error message contains the text."""
    return any(text in e for e in errors)


# ---------- valid plans ----------
def test_valid_2bhk_plan_with_parking_passes():
    assert errors_for(plan_2bhk(), req()) == []


def test_valid_3bhk_plan_without_parking_passes():
    assert errors_for(plan_3bhk(), req_3bhk()) == []


def test_valid_g_plus_1_plan_passes():
    assert errors_for(plan_g_plus_1(), req(bhk_type="3BHK", floors="G+1")) == []


# ---------- BHK rules ----------
def test_2bhk_has_exactly_two_bedrooms():
    plan = plan_2bhk()
    assert bedroom_count(plan) == 2
    assert errors_for(plan, req()) == []


def test_3bhk_has_exactly_three_bedrooms():
    plan = plan_3bhk()
    assert bedroom_count(plan) == 3
    assert errors_for(plan, req_3bhk()) == []


def test_three_bedrooms_rejected_for_2bhk_request():
    plan = plan_3bhk()
    errors = errors_for(plan, req(plot_size_sqft=1200, plot_width_ft=30, parking="No parking"))
    assert has_error(errors, "needs exactly 2 bedrooms")


def test_two_bedrooms_rejected_for_3bhk_request():
    errors = errors_for(plan_2bhk(), req(bhk_type="3BHK"))
    assert has_error(errors, "needs exactly 3 bedrooms")


def test_bathroom_count_must_match_form():
    errors = errors_for(plan_2bhk(), req(bathrooms=3))
    assert has_error(errors, "asks for 3 bathrooms")


# ---------- room sizes and overlaps ----------
def test_too_small_room_rejected():
    plan = plan_2bhk()
    plan["floors"][0]["rooms"][0].update(width=9, height=9)  # master bedroom shrunk below 11x12
    assert has_error(errors_for(plan, req()), "below the minimum")


def test_overlapping_rooms_rejected():
    plan = plan_2bhk()
    plan["floors"][0]["rooms"][1]["x"] = 10  # Bedroom 2 now sits on top of the master bedroom
    assert has_error(errors_for(plan, req()), "overlaps")


def test_room_outside_plot_rejected():
    plan = plan_2bhk()
    plan["floors"][0]["rooms"][1]["width"] = 20  # sticks out past the 25 ft width
    assert has_error(errors_for(plan, req()), "outside")


# ---------- parking ----------
def test_parking_present_when_requested():
    plan = plan_2bhk()
    assert plan["parking"] is not None
    assert errors_for(plan, req()) == []


def test_missing_parking_rejected_when_requested():
    plan = plan_2bhk()
    plan["parking"] = None
    assert has_error(errors_for(plan, req()), "was requested but")


def test_parking_absent_when_not_requested():
    assert errors_for(plan_3bhk(), req_3bhk()) == []


def test_parking_rejected_when_not_requested():
    plan = plan_2bhk()  # has parking, but the user chose no parking
    assert has_error(errors_for(plan, req(parking="No parking")), "was not requested")


def test_parking_too_small_rejected():
    plan = plan_2bhk()
    plan["parking"].update(width=8, height=15)
    assert has_error(errors_for(plan, req()), "needs at least")


def test_parking_overlapping_room_rejected():
    plan = plan_2bhk()
    plan["parking"].update(x=5)  # slides under the living hall (starts at x=10)
    assert has_error(errors_for(plan, req()), "overlaps")


def test_smaller_parking_allowed_only_with_feasibility_note():
    plan = plan_2bhk()  # holds a 1 car bay, but the user asked for 2 cars
    request = req(parking="2 cars")
    assert has_error(errors_for(plan, request), "parking.type must be")
    plan["feasibility_note"] = "Reduce parking to 1 car"
    assert not has_error(errors_for(plan, request), "parking.type must be")


# ---------- floors ----------
def test_g_plus_1_needs_both_floor_plans():
    plan = plan_g_plus_1()
    plan["floors"] = plan["floors"][:1]
    assert has_error(errors_for(plan, req(bhk_type="3BHK", floors="G+1")), "'floors' must contain")


def test_ground_floor_request_rejects_two_plans():
    errors = errors_for(plan_g_plus_1(), req(bhk_type="3BHK", floors="Ground Floor"))
    assert has_error(errors, "'floors' must contain")


def test_door_must_fit_on_its_wall():
    plan = copy.deepcopy(plan_2bhk())
    plan["floors"][0]["doors"][0]["offset"] = 14  # living hall wall is only 15 ft long
    assert has_error(errors_for(plan, req()), "runs past the wall")


def test_small_room_error_says_which_dimension_to_change():
    plan = plan_2bhk()
    plan["floors"][0]["rooms"][0].update(width=9, height=12)  # master bedroom is 9 wide, needs 11x12
    assert has_error(errors_for(plan, req()), "Make its width at least 11 ft")


def test_ground_floor_only_plan_cannot_have_a_staircase():
    plan = plan_2bhk()
    plan["floors"][0]["rooms"][1] = room("Staircase", "staircase", 12, 0, 13, 12)  # replaces Bedroom 2
    assert has_error(errors_for(plan, req()), "must not have a staircase")
