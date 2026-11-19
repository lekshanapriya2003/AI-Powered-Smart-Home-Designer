"""schemas.py - Pydantic models for the API and for the design JSON returned by the LLM.

This file never touches the database or config, so the validator tests can import it directly.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


# ---------- what the user submits ----------
BhkType = Literal["2BHK", "3BHK"]
FloorsType = Literal["Ground Floor", "G+1"]
StyleType = Literal["Modern", "Traditional", "Luxury"]
ParkingType = Literal["No parking", "Two-wheeler only", "1 car", "2 cars"]


class DesignRequestIn(BaseModel):
    """The requirement form. Every field is required and numbers must be positive."""

    plot_size_sqft: float = Field(gt=0)
    plot_width_ft: float = Field(gt=0)
    plot_length_ft: float = Field(gt=0)
    bhk_type: BhkType
    bathrooms: int = Field(ge=1, le=6)
    floors: FloorsType
    budget_inr: int = Field(gt=0)
    style: StyleType
    parking: ParkingType


class DesignModifyIn(BaseModel):
    """Only the fields the user edited. Anything left out keeps its value from the version being modified."""

    model_config = ConfigDict(extra="forbid")  # plot size and dimensions cannot be changed in a version

    bhk_type: Optional[BhkType] = None
    bathrooms: Optional[int] = Field(default=None, ge=1, le=6)
    floors: Optional[FloorsType] = None
    budget_inr: Optional[int] = Field(default=None, gt=0)
    style: Optional[StyleType] = None
    parking: Optional[ParkingType] = None


class DesignRequestOut(DesignRequestIn):
    """A saved request, including which project and version it belongs to."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str
    version_number: int


# ---------- the design JSON (what the LLM must return) ----------
RoomType = Literal[
    "living", "dining", "kitchen", "master_bedroom", "bedroom",
    "attached_bathroom", "common_bathroom", "staircase", "utility", "passage",
]
Wall = Literal["N", "E", "S", "W"]


class Room(BaseModel):
    """One rectangular room. x/y is the top-left corner in feet from the plot's top-left."""

    name: str
    type: RoomType
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Opening(BaseModel):
    """A door or window on one wall of a room, measured from the wall's start (N/S: left, E/W: top)."""

    room: str
    wall: Wall
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    kind: Literal["main", "internal"] = "internal"  # only used for doors


class Floor(BaseModel):
    """The plan of one floor."""

    name: str
    rooms: list[Room]
    doors: list[Opening] = []
    windows: list[Opening] = []


class Parking(BaseModel):
    """Open or covered parking area on the ground floor (not an enclosed room)."""

    type: Literal["two_wheeler", "1_car", "2_cars"]
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class BudgetNote(BaseModel):
    """Cost estimate. The numbers are filled by the server, the LLM only writes the note."""

    built_up_sqft: float = 0
    rate_min_per_sqft: int = 0
    rate_max_per_sqft: int = 0
    cost_min_inr: int = 0
    cost_max_inr: int = 0
    fits_budget: bool = False
    note: str = ""
    disclaimer: str = ""


class Concept(BaseModel):
    """One complete house design concept."""

    concept_name: str
    bhk_type: Literal["2BHK", "3BHK"]
    layout_summary: str
    space_utilization: str
    parking_impact: str
    color_palette: str = ""  # reused later so all 4 image prompts match
    floors: list[Floor]
    parking: Optional[Parking] = None
    advantages: list[str]
    budget_note: BudgetNote = BudgetNote()
    recommended: bool = False
    recommendation_reason: Optional[str] = None
    feasibility_note: Optional[str] = None


# ---------- what the API returns ----------
class DesignOut(BaseModel):
    """A stored concept with its database id."""

    id: int
    concept_name: str
    is_recommended: bool
    concept: Concept


class DesignSetOut(BaseModel):
    """A request plus all the concepts generated for it."""

    request: DesignRequestOut
    designs: list[DesignOut]
    warnings: list[str] = []
    llm_providers: list[str] = []  # which LLM answered, handy for the demo


class ImageOut(BaseModel):
    """One generated image. `url` is a path on the backend, e.g. /generated/design_3/exterior.jpg."""

    image_type: str
    url: str
    provider: str


class ImageSetOut(BaseModel):
    """The images stored for a design, plus any image types that could not be generated."""

    design_id: int
    images: list[ImageOut]
    failed: list[str] = []


class VersionOut(BaseModel):
    """One entry in a project's version list."""

    request_id: int
    version_number: int
    created_at: datetime
    based_on_version: Optional[int] = None  # the version this one was modified from
    changes: list[str]  # what changed compared with that version


class VersionListOut(BaseModel):
    """All versions (v1, v2, v3...) of one project."""

    project_id: str
    versions: list[VersionOut]


# ---------- the band layout the LLM actually returns (converted to Concept by layout_builder) ----------
BandRoomType = Literal[
    "living", "dining", "kitchen", "master_bedroom", "bedroom",
    "attached_bathroom", "common_bathroom", "staircase", "utility", "passage", "parking",
]


# Names LLMs often use instead of our room types. Mapping them saves a whole retry.
ROOM_TYPE_ALIASES = {
    "living_room": "living", "living_hall": "living", "hall": "living", "lounge": "living", "drawing_room": "living",
    "master": "master_bedroom", "master_bed": "master_bedroom", "master_bed_room": "master_bedroom",
    "bed_room": "bedroom", "guest_bedroom": "bedroom", "kids_bedroom": "bedroom", "children_bedroom": "bedroom",
    "dining_room": "dining", "dining_area": "dining", "dining_hall": "dining",
    "stairs": "staircase", "stair": "staircase", "stairway": "staircase",
    "car_parking": "parking", "car_porch": "parking", "garage": "parking", "parking_area": "parking",
    "two_wheeler_parking": "parking", "carport": "parking",
    "store": "utility", "store_room": "utility", "storeroom": "utility", "pooja": "utility", "pooja_room": "utility",
    "laundry": "utility", "wash_area": "utility", "balcony": "utility",
    "corridor": "passage", "lobby": "passage", "hallway": "passage",
    "other": "utility", "misc": "utility", "extra": "utility", "closet": "utility", "wardrobe": "utility", "pantry": "utility",
    "attached_bath": "attached_bathroom", "attached_toilet": "attached_bathroom", "master_bath": "attached_bathroom",
    "master_bathroom": "attached_bathroom", "ensuite": "attached_bathroom", "en_suite": "attached_bathroom",
    "common_bath": "common_bathroom", "common_toilet": "common_bathroom",
}
PLAIN_BATHROOM_WORDS = {"bathroom", "bath", "toilet", "washroom", "wc", "restroom"}


class BandRoom(BaseModel):
    """A room (or the parking area) inside a band. It only has a width, the band gives the height."""

    name: str
    type: BandRoomType
    width: float = Field(gt=0)

    @field_validator("type", mode="before")
    @classmethod
    def fix_common_type_names(cls, value, info: ValidationInfo):
        """Accept near-miss room types ("Living Room", "bathroom") by mapping them to ours."""
        if not isinstance(value, str):
            return value
        key = value.strip().lower().replace(" ", "_").replace("-", "_")
        if key in PLAIN_BATHROOM_WORDS:  # attached or common? The room's name usually says
            name = str(info.data.get("name", "")).lower()
            return "attached_bathroom" if ("attached" in name or "master" in name or "ensuite" in name) else "common_bathroom"
        return ROOM_TYPE_ALIASES.get(key, key)


class Band(BaseModel):
    """A horizontal strip of the plot. Rooms sit side by side, left to right."""

    height: float = Field(gt=0)
    rooms: list[BandRoom] = Field(min_length=1)


class FloorDraft(BaseModel):
    """One floor as bands from the back of the plot (top) to the road (bottom)."""

    name: str
    bands: list[Band] = Field(min_length=1)  # doors and windows are placed by opening_planner, not by the LLM


class ConceptDraft(BaseModel):
    """What the LLM returns. It has no x/y: the server calculates them from the bands."""

    concept_name: str
    bhk_type: Literal["2BHK", "3BHK"]
    layout_summary: str
    space_utilization: str
    parking_impact: str
    color_palette: str = ""
    parking_type: Optional[Literal["two_wheeler", "1_car", "2_cars"]] = None
    floors: list[FloorDraft]
    advantages: list[str]
    budget_note: BudgetNote = BudgetNote()
    recommended: bool = False
    recommendation_reason: Optional[str] = None
    feasibility_note: Optional[str] = None
