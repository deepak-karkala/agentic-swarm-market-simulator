"""API routes: POST /simulate, SSE status, report endpoints."""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.schemas import ReportResponse, SimulateRequest, SimulateResponse
from backend.pipeline.task_manager import task_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/simulate", response_model=SimulateResponse)
async def simulate(request: SimulateRequest):
    if not task_manager.acquire():
        raise HTTPException(
            status_code=409,
            detail={"error": "simulation_in_progress", "sim_id": "current"},
        )

    sim_id = task_manager.init_sim()
    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage0", "message": "Gathering market intelligence..."})

    # Background pipeline will be wired in Task 6.1.
    # The lock is released when the pipeline completes or errors.

    return SimulateResponse(sim_id=sim_id, status="queued")


@router.get("/simulate/{sim_id}/status")
async def simulate_status(sim_id: str, request: Request):
    if not task_manager.has_sim(sim_id):
        raise HTTPException(status_code=404, detail="Simulation not found")

    queue = task_manager.get_queue(sim_id)

    async def event_stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/simulate/{sim_id}/report")
async def simulate_report(sim_id: str):
    if not task_manager.has_sim(sim_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return JSONResponse(
        content=ReportResponse(sim_id=sim_id, status="in_progress", current_stage="stage0").model_dump(),
        status_code=202,
    )


@router.get("/report/{sim_id}")
async def public_report(sim_id: str):
    if not task_manager.has_sim(sim_id):
        raise HTTPException(status_code=404, detail="Report not found")
    return JSONResponse(
        content=ReportResponse(sim_id=sim_id, status="in_progress", current_stage="stage0").model_dump(),
        status_code=202,
    )
