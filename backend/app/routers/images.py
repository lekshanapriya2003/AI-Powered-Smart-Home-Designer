"""images.py - endpoints to generate and list the 4 images of a design."""
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import IMAGE_DIR
from app.database import get_db
from app.models import Design, DesignImage
from app.schemas import Concept, DesignRequestIn, ImageOut, ImageSetOut
from app.services.image_service import ImageError, generate_image, save_image
from app.services.prompt_builder import IMAGE_TYPES, build_image_prompts

router = APIRouter(prefix="/api/designs", tags=["images"])

# One lock per design: a double click (or React dev double-mount) must not burn quota twice.
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(design_id: int) -> threading.Lock:
    """Return the lock that belongs to this design."""
    with _locks_guard:
        return _locks.setdefault(design_id, threading.Lock())


def _saved_images(db: Session, design_id: int) -> list[DesignImage]:
    """Images whose file still exists on disk, in gallery order. Rows with a missing file are removed."""
    rows = db.query(DesignImage).filter(DesignImage.design_id == design_id).all()
    good = []
    for row in rows:
        if (IMAGE_DIR / row.file_path).is_file():
            good.append(row)
        else:
            db.delete(row)  # the file was deleted by hand, so generate it again next time
    db.commit()
    return sorted(good, key=lambda r: IMAGE_TYPES.index(r.image_type) if r.image_type in IMAGE_TYPES else 99)


def _to_response(design_id: int, rows: list[DesignImage], failed: list[str]) -> ImageSetOut:
    """Turn DB rows into the API response with URLs the browser can load."""
    images = [ImageOut(image_type=r.image_type, url=f"/generated/{r.file_path}", provider=r.provider) for r in rows]
    return ImageSetOut(design_id=design_id, images=images, failed=failed)


def _get_design(db: Session, design_id: int) -> Design:
    """Load a design or answer 404."""
    design = db.get(Design, design_id)
    if design is None:
        raise HTTPException(status_code=404, detail=f"No design with id {design_id}.")
    return design


@router.get("/{design_id}/images", response_model=ImageSetOut)
def list_images(design_id: int, db: Session = Depends(get_db)):
    """Return the images already generated for a design (never calls an AI provider)."""
    _get_design(db, design_id)
    return _to_response(design_id, _saved_images(db, design_id), [])


@router.post("/{design_id}/images", response_model=ImageSetOut)
def generate_images(design_id: int, db: Session = Depends(get_db)):
    """Generate whichever of the 4 images are missing, so calling it twice costs nothing extra."""
    design = _get_design(db, design_id)
    failed: list[str] = []
    with _lock_for(design_id):
        have = {r.image_type for r in _saved_images(db, design_id)}
        missing = [t for t in IMAGE_TYPES if t not in have]
        if missing:
            request = DesignRequestIn.model_validate(design.request, from_attributes=True)
            prompts = build_image_prompts(request, Concept.model_validate(design.concept_json))
            failed, first_error = _generate_missing(db, design_id, missing, prompts)
            if len(failed) == len(missing):
                raise HTTPException(status_code=503, detail=f"Image generation failed. {first_error}")
        rows = _saved_images(db, design_id)
    return _to_response(design_id, rows, failed)


def _generate_missing(db: Session, design_id: int, missing: list[str], prompts: dict[str, str]):
    """Generate each missing image in turn. Returns (failed types, first error message)."""
    failed, first_error, in_a_row = [], "", 0
    for image_type in missing:
        if in_a_row >= 2:  # two failures in a row usually means a quota or key problem, so stop wasting time
            failed.append(image_type)
            continue
        try:
            data, provider = generate_image(prompts[image_type])
            path = save_image(design_id, image_type, data)
            db.add(DesignImage(design_id=design_id, image_type=image_type, file_path=path, provider=provider))
            db.commit()
            in_a_row = 0
        except (ImageError, SQLAlchemyError) as exc:
            db.rollback()
            failed.append(image_type)
            first_error = first_error or str(exc)
            in_a_row += 1
    return failed, first_error
