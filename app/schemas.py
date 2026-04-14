from pydantic import BaseModel, Field, model_validator


class GrowingProfileCreate(BaseModel):
    plant_id: int
    environment_condition_id: int
    medium_id: int
    hardiness_zone_min: int | None = None
    hardiness_zone_max: int | None = None
    summary: str | None = None
    climate_context: str | None = None
    difficulty: str = Field(pattern="^(beginner|intermediate|advanced)$")
    confidence_level: str = Field(pattern="^(peer_reviewed|field_practice|speculative)$")
    last_reviewed_at: str | None = None
    citation_source_ids: list[int] = Field(
        default_factory=list,
        description="At least one required when confidence_level is not speculative",
    )

    @model_validator(mode="after")
    def citations_for_non_speculative(self):
        if self.confidence_level != "speculative" and len(self.citation_source_ids) < 1:
            raise ValueError("Non-speculative profiles require at least one citation_source_id")
        return self
