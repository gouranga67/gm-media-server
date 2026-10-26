from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import EffectLevel, MusicMode, TargetPlatform


class ConceptRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    focus: str = Field(default="", max_length=1200)
    audience: str = Field(default="", max_length=600)
    collection_id: UUID | None = None
    privacy_mode: Literal["hybrid", "text_only"] = "hybrid"
    reel_kind: Literal["story", "bloopers"] = "story"

    @field_validator("focus", "audience")
    @classmethod
    def normalize(cls, value: str) -> str:
        return " ".join(value.split())


class ConceptSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept_ids: list[UUID] = Field(min_length=1, max_length=2)
    effect_level: EffectLevel = EffectLevel.SOCIAL
    music_mode: MusicMode = MusicMode.NONE
    target_platform: TargetPlatform = TargetPlatform.ALL_SOCIAL

    @field_validator("concept_ids")
    @classmethod
    def unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("select each concept only once")
        return value


class ConceptBeatProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: int
    role: Literal["hook", "context", "development", "payoff", "ending"]


class ConceptVisualProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: UUID
    reason: str = Field(min_length=1, max_length=180)


class ConceptProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    angle: str = Field(min_length=1, max_length=500)
    @field_validator("title", "angle")
    @classmethod
    def nonempty_words(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("concept titles and angles cannot be blank")
        return value

    script: list[ConceptBeatProposal] = Field(min_length=1, max_length=10)
    visuals: list[ConceptVisualProposal] = Field(max_length=6)


class ConceptProposals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concepts: list[ConceptProposal] = Field(min_length=0, max_length=3)
