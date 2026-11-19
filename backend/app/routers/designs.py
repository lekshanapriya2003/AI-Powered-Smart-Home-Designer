"""designs.py - endpoints to generate concepts, modify requirements into a new version, and list versions."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Design, DesignRequest
from app.schemas import (Concept, DesignModifyIn, DesignOut, DesignRequestIn, DesignRequestOut, DesignSetOut,
                         VersionListOut, VersionOut)
from app.services.llm_service import DesignGenerationError, LLMError, generate_all_concepts
from app.services.prompt_builder import plot_size_warning

log = logging.getLogger("designs")
router = APIRouter(prefix="/api/designs", tags=["designs"])

# The fields a user can edit between versions, with the labels shown in the version list.
TRACKED_FIELDS = {"bhk_type": "Bedrooms", "bathrooms": "Bathrooms", "floors": "Floors",
                  "budget_inr": "Budget (INR)", "style": "Style", "parking": "Parking"}


def _to_response(row: DesignRequest, warnings: list[str], providers: list[str]) -> DesignSetOut:
    """Convert a saved request (with its designs) into the API response."""
    designs = [
        DesignOut(id=d.id, concept_name=d.concept_name, is_recommended=d.is_recommended,
                  concept=Concept.model_validate(d.concept_json))
        for d in sorted(row.designs, key=lambda d: d.id)
    ]
    return DesignSetOut(request=DesignRequestOut.model_validate(row), designs=designs,
                        warnings=warnings, llm_providers=providers)


def _create_version(db: Session, payload: DesignRequestIn, project_id: str, version: int,
                    parent_id: int | None = None) -> DesignSetOut:
    """Generate 3 concepts for the payload and save them as one version of a project."""
    warnings = plot_size_warning(payload)
    try:
        concepts, providers = generate_all_concepts(payload)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))  # AI service unavailable
    except DesignGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))  # AI answered with unusable plans

    try:
        row = DesignRequest(**payload.model_dump(), project_id=project_id, version_number=version,
                           parent_request_id=parent_id)
        row.designs = [
            Design(concept_name=c.concept_name, concept_json=c.model_dump(), is_recommended=c.recommended)
            for c in concepts
        ]
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()  # two modifies ran at once and picked the same version number
        raise HTTPException(status_code=409, detail="Another version was just created. Reload and try again.")
    except SQLAlchemyError as exc:
        db.rollback()
        log.exception("Could not save the generated designs")  # the real reason goes to the terminal
        detail = "Designs were generated but could not be saved to the database. See the backend terminal for the reason."
        if "parent_request_id" in str(exc):  # the table was created before this column existed
            detail = "The database is missing a column added in a later phase. Run: python scripts/init_db.py, then try again."
        raise HTTPException(status_code=500, detail=detail)
    return _to_response(row, warnings, providers)


@router.post("/generate", response_model=DesignSetOut, status_code=201)
def generate_designs(payload: DesignRequestIn, db: Session = Depends(get_db)):
    """Start a new project: generate 3 concepts for the form values and save them as v1."""
    return _create_version(db, payload, str(uuid.uuid4()), 1)


@router.post("/{request_id}/modify", response_model=DesignSetOut, status_code=201)
def modify_designs(request_id: int, changes: DesignModifyIn, db: Session = Depends(get_db)):
    """Copy a version, apply only the edited fields, and save the regenerated designs as the next version."""
    base = db.get(DesignRequest, request_id)
    if base is None:
        raise HTTPException(status_code=404, detail=f"No design request with id {request_id}.")

    # Keep only real edits, so sending an unchanged value does not count as a change.
    edits = {k: v for k, v in changes.model_dump(exclude_none=True).items() if getattr(base, k) != v}
    if not edits:
        raise HTTPException(status_code=422, detail="Nothing changed. Edit at least one requirement first.")
    merged = DesignRequestIn.model_validate(base, from_attributes=True).model_copy(update=edits)

    latest = db.query(func.max(DesignRequest.version_number)).filter(DesignRequest.project_id == base.project_id).scalar()
    return _create_version(db, merged, base.project_id, latest + 1, parent_id=base.id)


def _fmt(field: str, value) -> str:
    """Format a field value for the change list (budget gets thousands separators)."""
    return f"{value:,}" if field == "budget_inr" else str(value)


def _describe_changes(previous, current) -> list[str]:
    """List what differs between a version and the one it was modified from."""
    if previous is None:
        return ["Initial requirements"]
    return [f"{label}: {_fmt(f, getattr(previous, f))} → {_fmt(f, getattr(current, f))}"
            for f, label in TRACKED_FIELDS.items() if getattr(previous, f) != getattr(current, f)]


@router.get("/projects/{project_id}/versions", response_model=VersionListOut)
def list_versions(project_id: str, db: Session = Depends(get_db)):
    """List every version of a project, oldest first, with what changed in each."""
    rows = (db.query(DesignRequest).filter(DesignRequest.project_id == project_id)
            .order_by(DesignRequest.version_number).all())
    if not rows:
        raise HTTPException(status_code=404, detail="No project with that id.")
    by_id = {r.id: r for r in rows}
    versions = []
    for r in rows:
        parent = by_id.get(r.parent_request_id)  # None for v1
        versions.append(VersionOut(request_id=r.id, version_number=r.version_number, created_at=r.created_at,
                                   based_on_version=parent.version_number if parent else None,
                                   changes=_describe_changes(parent, r)))
    return VersionListOut(project_id=project_id, versions=versions)


@router.get("/{request_id}", response_model=DesignSetOut)
def get_designs(request_id: int, db: Session = Depends(get_db)):
    """Return a saved version and its concepts (this is how older versions are viewed)."""
    row = db.get(DesignRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No design request with id {request_id}.")
    return _to_response(row, plot_size_warning(DesignRequestIn.model_validate(row, from_attributes=True)), [])
