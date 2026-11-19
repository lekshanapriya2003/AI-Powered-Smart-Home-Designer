"""models.py - the three tables: design_requests, designs, design_images.

A "project" is a chain of versions. Every version is one row in design_requests
and shares a project_id, so v1, v2, v3 can be listed together.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DesignRequest(Base):
    """The form values the user submitted, plus which version this is."""

    __tablename__ = "design_requests"
    __table_args__ = (UniqueConstraint("project_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)  # groups all versions
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    # Which version this one was modified from (None for v1), so change lists compare the right pair.
    parent_request_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("design_requests.id", ondelete="SET NULL"), nullable=True)

    plot_size_sqft: Mapped[float] = mapped_column(Float)
    plot_width_ft: Mapped[float] = mapped_column(Float)
    plot_length_ft: Mapped[float] = mapped_column(Float)
    bhk_type: Mapped[str] = mapped_column(String(10))        # "2BHK" or "3BHK"
    bathrooms: Mapped[int] = mapped_column(Integer)
    floors: Mapped[str] = mapped_column(String(20))          # "Ground Floor" or "G+1"
    budget_inr: Mapped[int] = mapped_column(Integer)
    style: Mapped[str] = mapped_column(String(20))           # Modern / Traditional / Luxury
    parking: Mapped[str] = mapped_column(String(30))         # No parking / Two-wheeler only / 1 car / 2 cars

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    designs: Mapped[list["Design"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class Design(Base):
    """One design concept (the full LLM JSON) generated for a request."""

    __tablename__ = "designs"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("design_requests.id", ondelete="CASCADE"), index=True)
    concept_name: Mapped[str] = mapped_column(String(100))
    concept_json: Mapped[dict] = mapped_column(JSON)  # rooms, doors, windows, parking, budget_note...
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped["DesignRequest"] = relationship(back_populates="designs")
    images: Mapped[list["DesignImage"]] = relationship(
        back_populates="design", cascade="all, delete-orphan"
    )


class DesignImage(Base):
    """A generated image. Only the file path is stored, the file lives on disk."""

    __tablename__ = "design_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id", ondelete="CASCADE"), index=True)
    image_type: Mapped[str] = mapped_column(String(20))   # exterior / living_room / bedroom / kitchen
    file_path: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(30))     # cloudflare or pollinations
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    design: Mapped["Design"] = relationship(back_populates="images")
