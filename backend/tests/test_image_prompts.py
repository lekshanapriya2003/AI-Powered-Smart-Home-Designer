"""test_image_prompts.py - checks the 4 image prompts: same style words everywhere, parking only if requested."""
from app.schemas import Concept
from app.services.prompt_builder import IMAGE_TYPES, build_image_prompts
from tests.test_floorplan_validator import plan_2bhk, req


def prompts_for(**changes):
    """Build the 4 prompts for the sample plan with request overrides."""
    concept = Concept.model_validate({**plan_2bhk(), "color_palette": "white walls, walnut wood, black trims"})
    return build_image_prompts(req(**changes), concept)


def test_four_prompts_in_gallery_order():
    assert list(prompts_for()) == IMAGE_TYPES


def test_all_prompts_share_style_and_palette():
    for prompt in prompts_for(style="Luxury").values():
        assert "luxury Indian villa" in prompt
        assert "white walls, walnut wood, black trims" in prompt


def test_exterior_mentions_parking_only_when_requested():
    assert "car porch" in prompts_for(parking="1 car")["exterior"]
    assert "two cars" in prompts_for(parking="2 cars")["exterior"]
    assert "parking" not in prompts_for(parking="No parking")["exterior"].lower()
    assert "car" not in prompts_for(parking="No parking")["exterior"].lower().replace("carved", "")


def test_interior_prompts_never_mention_parking():
    for kind, prompt in prompts_for(parking="2 cars").items():
        if kind != "exterior":
            assert "parking" not in prompt.lower()


def test_floors_appear_in_exterior_prompt():
    assert "double-storey" in prompts_for(floors="G+1")["exterior"]
    assert "single-storey" in prompts_for(floors="Ground Floor")["exterior"]
