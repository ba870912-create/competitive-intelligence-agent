from pydantic import BaseModel, Field
from datetime import date as date_type
from typing import Literal, Optional

class RawClaim(BaseModel):
    """A single unverified fact pulled by the Research Agent."""
    competitor: str
    claim_type: Literal["pricing", "announcement", "hiring"]
    text: str
    source_url: str
    source_name: str
    observed_on: date_type = Field(default_factory=date_type.today)

class VerifiedClaim(RawClaim):
    """A claim that survived cross-source verification."""
    confidence: Literal["confirmed", "unconfirmed"]
    corroborating_sources: list[str] = []
    sentiment: str | None = None

class GraphEdge(BaseModel):
    subject: str
    relation: str
    object: str
    date: Optional[date_type] = None
    source_url: str

class BriefSection(BaseModel):
    heading: str
    content: str
    citations: list[str]

class WeeklyBrief(BaseModel):
    week_of: date_type
    sections: list[BriefSection]
    whats_new: list[str] = []