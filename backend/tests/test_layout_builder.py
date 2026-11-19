"""test_layout_builder.py - tests for turning the LLM's bands into rooms with coordinates.

Same 25 x 40 ft plot as the validator tests. y=40 is the road side.
"""
import copy

import pytest
from pydantic import ValidationError

from app.schemas import ConceptDraft
from app.services.floorplan_validator import validate_concept
from app.services.layout_builder import build_concept
from tests.test_floorplan_validator import req


def item(name, type_, width):
    """Shortcut for a room inside a band."""
    return {"name": name, "type": type_, "width": width}


def draft_2bhk():
    """A valid 2BHK + 1 car plan as three bands: 12 + 10 + 18 = 40 ft tall, every band 25 ft wide."""
    bands = [
        {"height": 12, "rooms": [item("Master Bedroom", "master_bedroom", 12), item("Bedroom 2", "bedroom", 13)]},
        {"height": 10, "rooms": [item("Master Bath", "attached_bathroom", 6), item("Common Bath", "common_bathroom", 6),
                                 item("Kitchen", "kitchen", 13)]},
        {"height": 18, "rooms": [item("Car Parking", "parking", 10), item("Living Hall", "living", 15)]},
    ]
    ground = {"name": "Ground Floor", "bands": bands}
    return {"concept_name": "Bands", "bhk_type": "2BHK", "layout_summary": "x", "space_utilization": "x",
            "parking_impact": "x", "parking_type": "1_car", "floors": [ground], "advantages": ["x"]}


def build(draft, request=None):
    """Build a concept from a draft dict."""
    return build_concept(ConceptDraft.model_validate(draft), request or req())


def has_error(errors, text):
    """True if any error message contains the text."""
    return any(text in e for e in errors)


def room(concept, name):
    """Find a room of the first floor by name."""
    return next(r for r in concept.floors[0].rooms if r.name == name)


# ---------- placing bands ----------
def test_bands_become_coordinates():
    concept, errors = build(draft_2bhk())
    assert errors == []
    kitchen = room(concept, "Kitchen")
    assert (kitchen.x, kitchen.y, kitchen.width, kitchen.height) == (12, 12, 13, 10)
    assert (room(concept, "Living Hall").x, room(concept, "Living Hall").y) == (10, 22)


def test_parking_item_becomes_parking_object():
    concept, _ = build(draft_2bhk())
    p = concept.parking
    assert (p.type, p.x, p.y, p.width, p.height) == ("1_car", 0, 22, 10, 18)
    assert "Car Parking" not in [r.name for r in concept.floors[0].rooms]  # parking is not a room


def test_converted_plan_passes_the_validator():
    concept, _ = build(draft_2bhk())
    assert validate_concept(concept, req()) == []


# ---------- repairing arithmetic slips ----------
def test_widths_that_are_too_small_are_grown():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"][1]["width"] = 11  # 12 + 11 = 23, not 25
    concept, errors = build(draft)
    assert errors == []
    assert room(concept, "Master Bedroom").width + room(concept, "Bedroom 2").width == 25
    assert validate_concept(concept, req()) == []


def test_widths_that_are_too_big_are_shrunk_but_not_below_minimums():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][1]["rooms"][2]["width"] = 20  # 6 + 6 + 20 = 32
    concept, errors = build(draft)
    assert errors == []
    assert room(concept, "Kitchen").width == 13  # the kitchen had the most spare width, so it gave it up
    assert room(concept, "Master Bath").width == 6


def test_narrow_bedroom_is_widened_from_the_roomiest_neighbour():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"] = [item("Master Bedroom", "master_bedroom", 17), item("Bedroom 2", "bedroom", 8)]
    concept, errors = build(draft)
    assert errors == []
    assert (room(concept, "Bedroom 2").width, room(concept, "Master Bedroom").width) == (10, 15)


def test_heights_that_are_too_big_are_shrunk():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][2]["height"] = 36  # 12 + 10 + 36 = 58
    concept, errors = build(draft)
    assert errors == []
    assert sum(h for h in {r.y: r.height for r in concept.floors[0].rooms}.values()) == 40  # the bands now fill the plot
    assert concept.parking.height >= 18  # and the car still has its 18 ft
    assert validate_concept(concept, req()) == []


def test_band_shorter_than_its_rooms_need_is_raised():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][2]["height"] = 10  # the car needs 18 ft, so this band grows to 18
    concept, errors = build(draft)
    assert errors == [] and concept.parking.height == 18


def test_band_that_cannot_fit_is_rejected_with_a_clear_message():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"] = [item("Master Bedroom", "master_bedroom", 12), item("Bedroom 2", "bedroom", 10),
                                               item("Bedroom 3", "bedroom", 10)]
    concept, errors = build(draft)
    assert concept is None and has_error(errors, "band 1: these rooms need at least 31 ft of width")


def test_bands_too_tall_for_the_plot_are_rejected_with_a_clear_message():
    concept, errors = build(draft_2bhk(), req(plot_length_ft=30))  # the bands need at least 11 + 8 + 18 = 37 ft
    assert concept is None and has_error(errors, "need at least 37 ft of height")


# ---------- parking ----------
def test_parking_type_without_a_parking_item_is_rejected():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][2]["rooms"][0]["type"] = "utility"
    assert has_error(build(draft)[1], "no Ground Floor band item has type 'parking'")


def test_parking_item_on_first_floor_is_rejected():
    draft = draft_2bhk()
    upper = copy.deepcopy(draft["floors"][0])
    upper["name"] = "First Floor"
    draft["floors"].append(upper)
    assert has_error(build(draft, req(floors="G+1"))[1], "Ground Floor only")


def test_short_plan_is_allowed_when_a_feasibility_note_is_given():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["height"] = 8  # the plan no longer fills the plot, which is allowed here
    draft["feasibility_note"] = "Choose G+1"
    concept, errors = build(draft)
    assert errors == [] and room(concept, "Master Bedroom").height >= 11  # but rooms never go below their minimum


# ---------- tolerant room types ----------
def test_common_wrong_room_types_are_mapped():
    draft = draft_2bhk()
    rooms = draft["floors"][0]["bands"][1]["rooms"]
    rooms[0]["type"], rooms[1]["type"] = "Bathroom", "bathroom"  # the names tell attached from common
    draft["floors"][0]["bands"][2]["rooms"][1]["type"] = "Living Room"
    concept, errors = build(draft)
    assert errors == []
    assert room(concept, "Master Bath").type == "attached_bathroom"
    assert room(concept, "Common Bath").type == "common_bathroom"
    assert room(concept, "Living Hall").type == "living"


def test_unknown_room_type_is_still_rejected():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"][0]["type"] = "swimming_pool"
    with pytest.raises(ValidationError) as info:
        ConceptDraft.model_validate(draft)
    assert info.value.errors()[0]["input"] == "swimming_pool"


# ---------- text ----------
def test_room_sizes_are_removed_from_text():
    draft = draft_2bhk()
    draft["layout_summary"] = "The Master Bedroom (12' x 12') sits beside a 13x12 bedroom and a 13 ft x 10 ft kitchen."
    concept, _ = build(draft)
    assert "12'" not in concept.layout_summary and "13x12" not in concept.layout_summary
    assert "Master Bedroom" in concept.layout_summary and "kitchen" in concept.layout_summary


def test_band_that_is_one_foot_too_narrow_is_made_taller():
    # Master 12 + Bedroom 10 + a 4 ft bath = 26 ft of minimum width in an 11 ft band: one foot too wide for the plot.
    # In a 12 ft band the master needs only 11 ft, so the builder raises the band instead of giving up.
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0] = {"height": 11, "rooms": [item("Master Bedroom", "master_bedroom", 11),
                                                              item("Bedroom 2", "bedroom", 10), item("Extra Bath", "common_bathroom", 4)]}
    concept, errors = build(draft)
    assert errors == []
    assert room(concept, "Master Bedroom").height >= 12 and room(concept, "Master Bedroom").width >= 11


def test_too_many_tall_bands_give_a_message_that_lists_each_band():
    draft = draft_2bhk()
    draft["floors"][0]["bands"].append({"height": 5, "rooms": [item("Study", "master_bedroom", 25)]})  # a 4th band
    concept, errors = build(draft)
    assert concept is None and has_error(errors, "Use fewer bands")


def test_other_is_treated_as_a_utility_room():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"][1]["type"] = "other"
    concept, errors = build(draft)
    assert errors == [] and room(concept, "Bedroom 2").type == "utility"


def test_rooms_with_the_same_name_are_numbered():
    draft = draft_2bhk()
    draft["floors"][0]["bands"][0]["rooms"][1]["name"] = "Master Bedroom"
    concept, _ = build(draft)
    names = [r.name for r in concept.floors[0].rooms]
    assert len(set(names)) == len(names) and "Master Bedroom 2" in names


def test_doors_and_windows_written_by_the_llm_are_ignored():
    draft = draft_2bhk()
    draft["floors"][0]["doors"] = [{"room": "Kitchen", "wall": "E", "offset": 1, "width": 3, "kind": "main"}]  # outside wall
    concept, errors = build(draft)
    assert errors == [] and not any(d.room == "Kitchen" and d.wall == "E" for d in concept.floors[0].doors)
