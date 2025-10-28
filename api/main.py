# api/main.py
from fastapi import FastAPI, HTTPException, Depends, Query
import os
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import random
from contextlib import suppress
from typing import List, Dict, Optional

import docker
from docker.errors import DockerException, NotFound

from dao import region_upsert_metrics, latest_regions
from db import get_db, SessionLocal
from storage import presign_put, presign_put_public, list_objects, ensure_bucket, USER_BUCKET, JOBS_BUCKET
from routes.telemetry import router as telemetry_router
from routes.files import router as files_router
from simulation import router as simulation_router, manager

app = FastAPI()
APP_START = datetime.utcnow()
CONTAINER_TARGETS = [
    name.strip()
    for name in os.getenv(
        "HEALTH_CONTAINER_NAMES",
        "gpu-reseller-db-1,gpu-reseller-minio-1,gpu-reseller-api-1,gpu-reseller-web-1,gpu-reseller-agent-1",
    ).split(",")
    if name.strip()
]

allow_origins = os.getenv("ALLOW_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health_check():
    now = datetime.utcnow()
    uptime = (now - APP_START).total_seconds()
    simulation_state = manager.status()
    container_snapshot = _gather_container_snapshot()
    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "uptime_seconds": int(uptime),
        "simulation": simulation_state,
        "containers": container_snapshot["containers"],
        "containers_error": container_snapshot.get("error"),
    }


def _gather_container_snapshot() -> Dict[str, object]:
    summary: List[Dict[str, object]] = []
    if not CONTAINER_TARGETS:
        return {"containers": summary}

    client: Optional[docker.DockerClient] = None
    try:
        client = docker.from_env()
    except DockerException as exc:
        return {"containers": summary, "error": str(exc)}

    error: Optional[str] = None
    try:
        for target in CONTAINER_TARGETS:
            try:
                container = client.containers.get(target)
                state = container.attrs.get("State", {})
                health_state = (state.get("Health") or {}).get("Status")
                summary.append(
                    {
                        "name": target,
                        "status": state.get("Status") or container.status,
                        "restart_count": container.attrs.get("RestartCount", 0),
                        "health": health_state,
                        "started_at": state.get("StartedAt"),
                    }
                )
            except NotFound:
                summary.append(
                    {
                        "name": target,
                        "status": "missing",
                        "restart_count": None,
                        "health": None,
                        "started_at": None,
                    }
                )
            except DockerException as exc:
                summary.append(
                    {
                        "name": target,
                        "status": "error",
                        "restart_count": None,
                        "health": None,
                        "error": str(exc),
                    }
                )
    except DockerException as exc:
        error = str(exc)
    finally:
        with suppress(Exception):
            if client is not None:
                client.close()

    result: Dict[str, object] = {"containers": summary}
    if error:
        result["error"] = error
    return result

@app.get("/regions/latest")
def regions_latest(db: Session = Depends(get_db)):
    try:
        data = latest_regions(db)
        return {"regions": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

# Background demo ticker (unchanged)
async def _tick_regions():
    codes = ["ashburn", "dallas", "us-east", "us-west", "eu-central"]
    while True:
        if manager.is_running():
            await asyncio.sleep(2)
            continue
        for code in codes:
            total = random.choice([4, 8, 16])
            free = random.randint(0, total)
            util = int(100 * (1 - (free / max(total, 1))))
            if util >= 90:
                status = "congested"
            elif util >= 70:
                status = "busy"
            elif util <= 25:
                status = "idle"
            else:
                status = "healthy"
            try:
                with SessionLocal() as db:
                    region_upsert_metrics(
                        db,
                        code=code,
                        total_gpus=total,
                        free_gpus=free,
                        util=util,
                        status=status,
                    )
            except Exception:
                pass
        await asyncio.sleep(10)

@app.on_event("startup")
async def on_startup():
    ensure_bucket(USER_BUCKET)
    ensure_bucket(JOBS_BUCKET)
    asyncio.create_task(_tick_regions())

# ---- Storage API ----
@app.post("/storage/presign-upload")
def storage_presign_upload(
    bucket: str = Query("user-data"),
    key: str = Query(..., description="object key"),
    public: bool = Query(True, description="Return browser-friendly URL")
):
    try:
        url = presign_put(bucket, key)
        browser = presign_put_public(bucket, key) if public else url
        return {"url": url, "browser_url": browser, "bucket": bucket, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Presign error: {e}")

@app.get("/storage/list")
def storage_list(bucket: str = Query("gpu-jobs"), prefix: str = Query("")):
    try:
        return {"bucket": bucket, "items": list_objects(bucket, prefix)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List error: {e}")

# Routers
app.include_router(telemetry_router)
app.include_router(files_router)
app.include_router(simulation_router)
