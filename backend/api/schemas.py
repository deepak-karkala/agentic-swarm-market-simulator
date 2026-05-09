"""Pydantic request/response models — extended in Task 1.3."""

from pydantic import BaseModel, Field


class SimulateRequest(BaseModel):
    scenario_text: str = Field(max_length=2000)
    geography: str = Field(default="US")
    vertical: str = Field(default="auto")
    horizon_days: int = Field(default=30, ge=1, le=365)
    agent_count: int = Field(default=100, ge=10, le=200)


class SimulateResponse(BaseModel):
    sim_id: str
    status: str
