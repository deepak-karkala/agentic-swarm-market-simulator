"""API route stubs — implemented in Task 1.3."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/simulate/{sim_id}/status")
async def get_sim_status(sim_id: str):
    return {"sim_id": sim_id, "status": "not_implemented"}
