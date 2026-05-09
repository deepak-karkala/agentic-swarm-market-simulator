"""Pydantic request/response models with prompt injection sanitizer."""

import logging
import re

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    (r"\n{2,}Human:", " "),
    (r"</s>", ""),
    (r"<\|im_start\|>", ""),
    (r"<\|im_end\|>", ""),
    (r"\[INST\]", ""),
    (r"\[/INST\]", ""),
]


def sanitize_scenario_text(text: str) -> str:
    """Strip common LLM prompt injection markers from user input."""
    clean = text
    for pattern, replacement in _INJECTION_PATTERNS:
        if re.search(pattern, clean):
            logger.warning("Prompt injection pattern detected in scenario text")
            clean = re.sub(pattern, replacement, clean)
    return clean


class SimulateRequest(BaseModel):
    scenario_text: str = Field(max_length=2000)
    geography: str = Field(default="US")
    vertical: str = Field(default="auto")
    horizon_days: int = Field(default=30, ge=1, le=365)
    agent_count: int = Field(default=100, ge=10, le=200)

    @field_validator("scenario_text", mode="after")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return sanitize_scenario_text(v)


class SimulateResponse(BaseModel):
    sim_id: str
    status: str


class ReportResponse(BaseModel):
    sim_id: str
    status: str
    current_stage: str | None = None
