import asyncio
import logging
import math
import random
import time
from contextlib import suppress
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from dao import (
    latest_region_stats_map,
    price_for_region,
    recent_telemetry,
    record_telemetry,
    regions_financial_snapshot,
    update_region_financials,
)
from db import SessionLocal


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["simulation"])


class SimulationRequest(BaseModel):
    duration_hours: float = Field(24, gt=0)
    step_minutes: float = Field(60, gt=0)
    speed_multiplier: float = Field(3600, gt=0, description="Simulated seconds advanced per real second")
    base_cost_cph: float = Field(0.45, ge=0)
    price_mode: str = Field("standard", pattern="^(standard|priority|spot)$")


class SimulationManager:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._sync_lock = RLock()
        self._clients: Set[WebSocket] = set()
        self._last_heartbeat: Dict[WebSocket, float] = {}
        self._watchdogs: Dict[WebSocket, asyncio.Task] = {}
        self._latest_payload: Optional[Dict] = None
        self._current_request: Optional[SimulationRequest] = None
        self._current_iteration: int = 0
        self._messages_sent: int = 0
        self._disconnects: int = 0
        self._last_broadcast_at: Optional[datetime] = None
        self._stale_timeout = 30
        self._watchdog_interval = 5

    async def start(self, request: SimulationRequest) -> None:
        async with self._lock:
            await self._stop_locked()
            self._current_request = request
            self._current_iteration = 0
            self._messages_sent = 0
            self._disconnects = 0
            self._latest_payload = None
            self._last_broadcast_at = None
            self._task = asyncio.create_task(self._run_simulation(request))

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._current_request = None
        await self._close_all_clients("simulation stopped")

    async def register(self, websocket: WebSocket) -> None:
        self._add_connection(websocket)
        logger.info(f"Client connected: {self._client_repr(websocket)}")
        if self._latest_payload:
            with suppress(Exception):
                await websocket.send_json(self._latest_payload)
                self.update_heartbeat(websocket)
        try:
            while True:
                try:
                    message = await websocket.receive_text()
                    if message is not None:
                        self.update_heartbeat(websocket)
                except WebSocketDisconnect:
                    logger.info(f"Client disconnected: {self._client_repr(websocket)}")
                    return
                except RuntimeError:
                    logger.warning("WebSocket runtime error during receive; closing connection")
                    return
        finally:
            self._cleanup_connection(websocket, "listener exit")

    async def broadcast(self, payload: Dict) -> None:
        now = datetime.utcnow()
        with self._sync_lock:
            self._latest_payload = payload
            self._last_broadcast_at = now
            iteration = payload.get("iteration")
            if isinstance(iteration, int):
                self._current_iteration = iteration
            self._messages_sent += 1
            clients = list(self._clients)

        for client in clients:
            try:
                await client.send_json(payload)
                self.update_heartbeat(client)
            except Exception as exc:
                logger.warning(
                    "Failed to push simulation payload to %s: %s",
                    self._client_repr(client),
                    exc,
                )
                with suppress(Exception):
                    await client.close(code=1011, reason="send failure")
                self._cleanup_connection(client, "send failure")

    def update_heartbeat(self, websocket: WebSocket) -> None:
        with self._sync_lock:
            if websocket in self._clients:
                self._last_heartbeat[websocket] = time.time()

    def status(self) -> Dict[str, object]:
        snapshot_clients: List[Dict[str, object]] = []
        last_payload: Optional[Dict] = None
        request: Optional[SimulationRequest] = None
        messages_sent = 0
        disconnects = 0
        last_broadcast_at: Optional[datetime] = None
        running = False

        with self._sync_lock:
            clients = list(self._clients)
            last_payload = self._latest_payload
            request = self._current_request
            messages_sent = self._messages_sent
            disconnects = self._disconnects
            last_broadcast_at = self._last_broadcast_at
            running = self._task is not None and not self._task.done()
            now = time.time()
            for ws in clients:
                heartbeat = self._last_heartbeat.get(ws)
                snapshot_clients.append(
                    {
                        "client": self._client_repr(ws),
                        "seconds_since_heartbeat": round(now - heartbeat, 1) if heartbeat else None,
                    }
                )

        payload_meta: Optional[Dict[str, object]] = None
        last_broadcast_age = None
        if last_payload:
            payload_meta = {
                "timestamp": last_payload.get("timestamp"),
                "iteration": last_payload.get("iteration"),
                "step_hours": last_payload.get("step_hours"),
            }
        if last_broadcast_at:
            last_broadcast_age = round((datetime.utcnow() - last_broadcast_at).total_seconds(), 2)

        return {
            "running": running,
            "active_clients": len(snapshot_clients),
            "clients": snapshot_clients,
            "messages_sent": messages_sent,
            "disconnects": disconnects,
            "last_broadcast": last_broadcast_at.isoformat() if last_broadcast_at else None,
            "last_broadcast_age_seconds": last_broadcast_age,
            "current_iteration": self._current_iteration,
            "stale_timeout_seconds": self._stale_timeout,
            "request": request.model_dump() if request else None,
            "latest_payload": payload_meta,
        }

    async def _close_all_clients(self, reason: str) -> None:
        with self._sync_lock:
            clients = list(self._clients)
        for ws in clients:
            with suppress(Exception):
                await ws.close(code=1000, reason=reason)
            self._cleanup_connection(ws, reason)

    def _add_connection(self, websocket: WebSocket) -> None:
        with self._sync_lock:
            self._clients.add(websocket)
            self._last_heartbeat[websocket] = time.time()
            watchdog = asyncio.create_task(self._watchdog(websocket))
            self._watchdogs[websocket] = watchdog

    def _cleanup_connection(self, websocket: WebSocket, reason: str) -> None:
        task: Optional[asyncio.Task] = None
        removed = False
        with self._sync_lock:
            if websocket in self._clients:
                self._clients.remove(websocket)
                removed = True
            if websocket in self._last_heartbeat:
                self._last_heartbeat.pop(websocket, None)
                removed = True
            task = self._watchdogs.pop(websocket, None)
            if removed:
                self._disconnects += 1
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
        if removed:
            logger.info("Client cleanup: %s (%s)", self._client_repr(websocket), reason)

    async def _watchdog(self, websocket: WebSocket) -> None:
        try:
            while True:
                await asyncio.sleep(self._watchdog_interval)
                with self._sync_lock:
                    if websocket not in self._clients:
                        return
                    last = self._last_heartbeat.get(websocket)
                if last is None:
                    continue
                if time.time() - last > self._stale_timeout:
                    logger.warning("Closing stale connection: %s", self._client_repr(websocket))
                    with suppress(Exception):
                        await websocket.close(code=1011, reason="stale connection")
                    return
        finally:
            self._cleanup_connection(websocket, "watchdog timeout")

    def _client_repr(self, websocket: WebSocket) -> str:
        client = getattr(websocket, "client", None)
        if client and getattr(client, "host", None) is not None:
            return f"{client.host}:{client.port}"
        return "unknown"

    async def _run_simulation(self, request: SimulationRequest) -> None:
        step_hours = request.step_minutes / 60.0
        total_steps = max(1, math.ceil(request.duration_hours / step_hours))
        sleep_seconds = max(0.01, (step_hours * 3600.0) / request.speed_multiplier)

        db = SessionLocal()
        try:
            for step in range(total_steps):
                regions = regions_financial_snapshot(db)
                if not regions:
                    raise HTTPException(status_code=400, detail="No regions available for simulation.")

                stats_map = latest_region_stats_map(db)

                totals = {
                    "revenue_cents": 0,
                    "cost_cents": 0,
                    "profit_cents": 0,
                    "avg_utilization": 0.0,
                }
                regions_payload = []
                util_sum = 0.0
                max_ts: Optional[datetime] = None

                for region in regions:
                    stats = stats_map.get(region["id"], {})
                    total_gpus = max(1, int(stats.get("total_gpus", 8) or 8))

                    # Generate utilization between 35% and 95%
                    utilization = max(0.05, min(0.98, random.normalvariate(0.65, 0.18)))

                    pricing = price_for_region(db, region["code"])
                    price = pricing.get(request.price_mode, pricing["standard"])

                    revenue_cents = int(round(utilization * price * total_gpus * step_hours * 100))
                    cost_cents = int(round(total_gpus * request.base_cost_cph * step_hours * 100))
                    profit_cents = revenue_cents - cost_cents

                    current_sim_ts: datetime = region.get("simulated_time") or datetime.utcnow()
                    next_sim_ts = current_sim_ts + timedelta(hours=step_hours)

                    update_region_financials(
                        db,
                        region_id=region["id"],
                        revenue_delta=revenue_cents,
                        cost_delta=cost_cents,
                        simulated_time=next_sim_ts,
                    )
                    record_telemetry(
                        db,
                        region_id=region["id"],
                        ts=next_sim_ts,
                        utilization=utilization,
                        revenue_cents=revenue_cents,
                        cost_cents=cost_cents,
                    )

                    totals["revenue_cents"] += revenue_cents
                    totals["cost_cents"] += cost_cents
                    totals["profit_cents"] += profit_cents
                    util_sum += utilization
                    max_ts = next_sim_ts if not max_ts or next_sim_ts > max_ts else max_ts

                    regions_payload.append(
                        {
                            "code": region["code"],
                            "timestamp": next_sim_ts.isoformat(),
                            "utilization": round(utilization * 100, 2),
                            "revenue_cents": revenue_cents,
                            "cost_cents": cost_cents,
                            "profit_cents": profit_cents,
                            "total_gpus": total_gpus,
                        }
                    )

                totals["avg_utilization"] = round((util_sum / len(regions)) * 100, 2)

                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

                payload = {
                    "iteration": step + 1,
                    "timestamp": (max_ts or datetime.utcnow()).isoformat(),
                    "step_hours": step_hours,
                    "totals": totals,
                    "regions": regions_payload,
                }

                await self.broadcast(payload)
                await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            db.close()


manager = SimulationManager()


@router.post("")
async def trigger_simulation(request: SimulationRequest):
    db = SessionLocal()
    try:
        regions = regions_financial_snapshot(db)
        if not regions:
            raise HTTPException(status_code=400, detail="No regions available for simulation.")
    finally:
        db.close()

    await manager.start(request)
    return {
        "status": "started",
        "duration_hours": request.duration_hours,
        "step_minutes": request.step_minutes,
        "speed_multiplier": request.speed_multiplier,
    }


@router.post("/stop")
async def stop_simulation():
    await manager.stop()
    return {"status": "stopped"}


@router.get("/telemetry")
def recent_simulation(limit: int = 200):
    db = SessionLocal()
    try:
        rows = recent_telemetry(db, limit)
    finally:
        db.close()

    buckets: Dict[str, Dict] = {}
    ordered_keys: List[str] = []

    for row in reversed(rows):  # chronological order
        ts = row["ts"].isoformat()
        if ts not in buckets:
            buckets[ts] = {
                "timestamp": ts,
                "regions": [],
                "totals": {"revenue_cents": 0, "cost_cents": 0, "profit_cents": 0, "avg_utilization": 0.0},
            }
            ordered_keys.append(ts)

        revenue = int(row["revenue_cents"])
        cost = int(row["cost_cents"])
        utilization = float(row["gpu_utilization"])

        buckets[ts]["regions"].append(
            {
                "code": row["code"],
                "utilization": round(utilization * 100, 2),
                "revenue_cents": revenue,
                "cost_cents": cost,
                "profit_cents": revenue - cost,
            }
        )
        buckets[ts]["totals"]["revenue_cents"] += revenue
        buckets[ts]["totals"]["cost_cents"] += cost

    for ts in ordered_keys:
        bucket = buckets[ts]
        bucket["totals"]["profit_cents"] = bucket["totals"]["revenue_cents"] - bucket["totals"]["cost_cents"]
        if bucket["regions"]:
            avg_util = sum(r["utilization"] for r in bucket["regions"]) / len(bucket["regions"])
            bucket["totals"]["avg_utilization"] = round(avg_util, 2)

    points = [buckets[k] for k in ordered_keys]
    return {"points": points[-limit:]}


@router.websocket("/stream")
async def simulation_stream(websocket: WebSocket):
    await websocket.accept()
    await manager.register(websocket)
