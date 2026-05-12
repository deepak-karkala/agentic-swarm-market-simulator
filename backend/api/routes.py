"""API routes: POST /simulate, SSE status, report endpoints."""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.schemas import ReportResponse, SimulateRequest, SimulateResponse
from backend.pipeline.task_manager import task_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/simulate", response_model=SimulateResponse)
async def simulate(request: SimulateRequest, background_tasks: BackgroundTasks):
    if not task_manager.acquire():
        current = task_manager.current_sim_id or "unknown"
        raise HTTPException(
            status_code=409,
            detail={"error": "simulation_in_progress", "sim_id": current},
        )

    sim_id = task_manager.init_sim()

    # Build an LLMClient from env vars and kick off the pipeline
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "no-key")
    from backend.llm.client import LLMClient
    llm = LLMClient(api_key=api_key)

    from backend.pipeline.orchestrator import run_pipeline_background
    background_tasks.add_task(run_pipeline_background, sim_id, request, llm)

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
                if event["event"] in ("simulation_complete", "simulation_error"):
                    break
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
    report = task_manager.get_report(sim_id)
    if report:
        task_manager.clear_sim(sim_id)  # reclaim memory after retrieval
        return JSONResponse(content={"sim_id": sim_id, "status": "complete", "sections": report})
    return JSONResponse(
        content=ReportResponse(sim_id=sim_id, status="in_progress", current_stage="unknown").model_dump(),
        status_code=202,
    )


@router.get("/report/{sim_id}")
async def public_report(sim_id: str):
    if not task_manager.has_sim(sim_id):
        raise HTTPException(status_code=404, detail="Report not found")
    report = task_manager.get_report(sim_id)
    if report:
        task_manager.clear_sim(sim_id)  # reclaim memory after retrieval
        return JSONResponse(content={"sim_id": sim_id, "status": "complete", "sections": report})
    return JSONResponse(
        content=ReportResponse(sim_id=sim_id, status="in_progress", current_stage="unknown").model_dump(),
        status_code=202,
    )
