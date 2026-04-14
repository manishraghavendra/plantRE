from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlantType(Base):
    __tablename__ = "plant_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    plants: Mapped[list["Plant"]] = relationship(back_populates="plant_type")


class GrowingMedium(Base):
    __tablename__ = "growing_medium"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class EnvironmentCondition(Base):
    __tablename__ = "environment_condition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity_scale: Mapped[int | None] = mapped_column(Integer)
    is_speculative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SurvivalFactor(Base):
    __tablename__ = "survival_factor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class EnvironmentConditionSurvivalFactor(Base):
    __tablename__ = "environment_condition_survival_factor"

    environment_condition_id: Mapped[int] = mapped_column(
        ForeignKey("environment_condition.id", ondelete="CASCADE"), primary_key=True
    )
    survival_factor_id: Mapped[int] = mapped_column(
        ForeignKey("survival_factor.id", ondelete="CASCADE"), primary_key=True
    )
    relevance: Mapped[str | None] = mapped_column(String)


class Plant(Base):
    __tablename__ = "plant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scientific_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    common_names: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    plant_type_id: Mapped[int] = mapped_column(ForeignKey("plant_type.id"), nullable=False)
    life_cycle: Mapped[str] = mapped_column(String, nullable=False)
    native_regions: Mapped[str | None] = mapped_column(Text)
    edible_parts: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    toxicity_notes: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("(datetime('now'))")
    )

    plant_type: Mapped["PlantType"] = relationship(back_populates="plants")
    growing_profiles: Mapped[list["GrowingProfile"]] = relationship(back_populates="plant")


class GrowingProfile(Base):
    __tablename__ = "growing_profile"
    __table_args__ = (
        UniqueConstraint("plant_id", "environment_condition_id", "medium_id", name="uq_profile_plant_env_medium"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plant.id", ondelete="CASCADE"), nullable=False)
    environment_condition_id: Mapped[int] = mapped_column(
        ForeignKey("environment_condition.id", ondelete="CASCADE"), nullable=False
    )
    medium_id: Mapped[int] = mapped_column(ForeignKey("growing_medium.id", ondelete="RESTRICT"), nullable=False)
    hardiness_zone_min: Mapped[int | None] = mapped_column(Integer)
    hardiness_zone_max: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String, nullable=False)
    last_reviewed_at: Mapped[str | None] = mapped_column(String)
    climate_context: Mapped[str | None] = mapped_column(Text)

    plant: Mapped["Plant"] = relationship(back_populates="growing_profiles")
    steps: Mapped[list["GrowingStep"]] = relationship(
        back_populates="growing_profile", order_by="GrowingStep.step_order"
    )
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="growing_profile")


class GrowingStep(Base):
    __tablename__ = "growing_step"
    __table_args__ = (UniqueConstraint("growing_profile_id", "step_order", name="uq_step_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    growing_profile_id: Mapped[int] = mapped_column(ForeignKey("growing_profile.id", ondelete="CASCADE"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    equipment: Mapped[str | None] = mapped_column(Text)

    growing_profile: Mapped["GrowingProfile"] = relationship(back_populates="steps")


class Requirement(Base):
    __tablename__ = "requirement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    growing_profile_id: Mapped[int] = mapped_column(ForeignKey("growing_profile.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    value_min: Mapped[float | None] = mapped_column(Float)
    value_max: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)

    growing_profile: Mapped["GrowingProfile"] = relationship(back_populates="requirements")


class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)


class Hazard(Base):
    __tablename__ = "hazard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    mitigation_summary: Mapped[str | None] = mapped_column(Text)
    # food_safety: consumption / contamination; growing_issue: cultivation (pests, disease, culture errors)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="food_safety", server_default=text("'food_safety'"))


class Source(Base):
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str | None] = mapped_column(String)
    publisher: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String, nullable=False)


class Citation(Base):
    __tablename__ = "citation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    page: Mapped[str | None] = mapped_column(String)
