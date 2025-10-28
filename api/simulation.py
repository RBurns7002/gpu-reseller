import asyncio
import logging
import math
import random
import time
from contextlib import suppress
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, List, Optional

from sqlalchemy import text

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from dao import (
    get_region_capacities,
    get_simulation_state,
    latest_region_stats_map,
    price_for_region,
    recent_telemetry,
    record_telemetry,
    regions_financial_snapshot,
    reset_simulation_data,
    update_region_financials,
    update_simulation_state,
    upsert_region_capacity,
    ensure_region_exists,
)
from db import SessionLocal


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["simulation"])

BASE_REGION_CAPACITY = 16
HQ_BASE_CAPACITY = 0
HQ_REGION_CODE = "hq"
HQ_REGION_NAME = "HQ Expansion"


class SimulationRequest(BaseModel):
    step_minutes: float = Field(30, gt=0)
    speed_multiplier: float = Field(3600, gt=0, description="Simulated seconds advanced per real second")
    price_mode: str = Field("standard", pattern="^(standard|priority|spot)$")
    spend_ratio: float = Field(0.25, ge=0, le=1)
    expansion_cost_per_gpu_cents: int = Field(40000, gt=0)
    electricity_cost_per_kwh: float = Field(
        0.065,
        ge=0,
        description="Electricity price in USD per kilowatt hour",
    )
    gpu_wattage_w: float = Field(
        240.0,
        ge=0,
        description="Peak power draw per GPU (watts)",
    )
    continuous: bool = True
    duration_hours: Optional[float] = Field(None, gt=0)


class SimulationManager:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._sync_lock = RLock()
        self._clients: set[WebSocket] = set()
        self._last_heartbeat: Dict[WebSocket, float] = {}
        self._watchdogs: Dict[WebSocket, asyncio.Task] = {}
        self._latest_payload: Optional[Dict] = None
        self._current_request: Optional[SimulationRequest] = None
        self._current_iteration: int = 0
        self._messages_sent: int = 0
        self._disconnects: int = 0
        self._last_broadcast_at: Optional[datetime] = None
        self._finance_snapshot: Dict[str, object] = {}
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
            self._finance_snapshot = {}
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
        logger.info("Client connected: %s", self._client_repr(websocket))
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
                    logger.info("Client disconnected: %s", self._client_repr(websocket))
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
            self._finance_snapshot = payload.get("finance", {})
            self._messages_sent += 1
            clients = list(self._clients)

        for client in clients:
            try:
                await client.send_json(payload)
                self.update_heartbeat(client)
            except Exception as exc:
                logger.warning("Failed to push simulation payload to %s: %s", self._client_repr(client), exc)
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
        messages_sent = 0
        disconnects = 0
        last_broadcast_at: Optional[datetime] = None
        running = False
        configuration: Optional[Dict[str, object]] = None
        finance_snapshot: Dict[str, object] = {}

        with self._sync_lock:
            clients = list(self._clients)
            last_payload = self._latest_payload
            messages_sent = self._messages_sent
            disconnects = self._disconnects
            last_broadcast_at = self._last_broadcast_at
            running = self._task is not None and not self._task.done()
            configuration = self._current_request.model_dump() if self._current_request else None
            finance_snapshot = dict(self._finance_snapshot) if self._finance_snapshot else {}
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
            "configuration": configuration,
            "active_clients": len(snapshot_clients),
            "clients": snapshot_clients,
            "messages_sent": messages_sent,
            "disconnects": disconnects,
            "last_broadcast": last_broadcast_at.isoformat() if last_broadcast_at else None,
            "last_broadcast_age_seconds": last_broadcast_age,
            "current_iteration": self._current_iteration,
            "stale_timeout_seconds": self._stale_timeout,
            "latest_payload": payload_meta,
            "finance": finance_snapshot,
        }

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

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
        sleep_seconds = max(0.01, (step_hours * 3600.0) / request.speed_multiplier)
        max_steps = None
        if not request.continuous and request.duration_hours:
            max_steps = max(1, math.ceil(request.duration_hours / step_hours))

        db = SessionLocal()
        try:
            state = get_simulation_state(db)
            energy_cost_per_gpu_hour = (request.gpu_wattage_w / 1000.0) * request.electricity_cost_per_kwh
            hq_region_id = ensure_region_exists(db, HQ_REGION_CODE, HQ_REGION_NAME)
            step_index = 0
            while True:
                regions = regions_financial_snapshot(db)
                if not regions:
                    raise HTTPException(status_code=400, detail="No regions available for simulation.")

                stats_map = latest_region_stats_map(db)
                capacities = get_region_capacities(db)

                if hq_region_id not in capacities:
                    capacities[hq_region_id] = HQ_BASE_CAPACITY
                    upsert_region_capacity(db, hq_region_id, HQ_BASE_CAPACITY)

                totals = {
                    "revenue_cents": 0,
                    "cost_cents": 0,
                    "profit_cents": 0,
                    "avg_utilization": 0.0,
                }
                regions_payload: List[Dict[str, object]] = []
                iteration_data: List[Dict[str, object]] = []
                util_sum = 0.0
                max_ts: Optional[datetime] = None

                for region in regions:
                    region_id = region["id"]
                    if region_id not in capacities:
                        default_capacity = HQ_BASE_CAPACITY if region_id == hq_region_id else BASE_REGION_CAPACITY
                        capacities[region_id] = default_capacity
                        upsert_region_capacity(db, region_id, default_capacity)
                    capacity = max(capacities.get(region_id, BASE_REGION_CAPACITY if region_id != hq_region_id else HQ_BASE_CAPACITY), 0)

                    utilization = max(0.05, min(0.98, random.normalvariate(0.65, 0.18)))
                    used_gpus = int(round(utilization * capacity))
                    free_gpus = max(capacity - used_gpus, 0)

                    pricing = price_for_region(db, region["code"])
                    price = pricing.get(request.price_mode, pricing["standard"])

                    revenue_cents = int(round(utilization * price * capacity * step_hours * 100))
                    cost_cents = int(round(used_gpus * step_hours * energy_cost_per_gpu_hour * 100))
                    profit_cents = revenue_cents - cost_cents

                    current_sim_ts: datetime = region.get("simulated_time") or datetime.utcnow()
                    next_sim_ts = current_sim_ts + timedelta(hours=step_hours)

                    util_percent = int(round(utilization * 100))
                    if util_percent >= 90:
                        status = "congested"
                    elif util_percent >= 70:
                        status = "busy"
                    elif util_percent <= 25:
                        status = "idle"
                    else:
                        status = "healthy"

                    update_region_financials(
                        db,
                        region_id=region_id,
                        revenue_delta=revenue_cents,
                        cost_delta=cost_cents,
                        simulated_time=next_sim_ts,
                        status=status,
                    )

                    db.execute(
                        text(
                            """
                        INSERT INTO region_stats(region_id, ts, total_gpus, free_gpus, utilization, avg_queue_sec)
                        VALUES (:rid, :ts, :total, :free, :util, 0)
                        ON CONFLICT (region_id, ts) DO UPDATE
                        SET total_gpus = EXCLUDED.total_gpus,
                            free_gpus = EXCLUDED.free_gpus,
                            utilization = EXCLUDED.utilization
                        """
                        ),
                        {
                            "rid": region_id,
                            "ts": next_sim_ts,
                            "total": capacity,
                            "free": free_gpus,
                            "util": util_percent,
                        },
                    )

                    iteration_data.append(
                        {
                            "region_id": region_id,
                            "code": region["code"],
                            "timestamp": next_sim_ts,
                            "utilization": utilization,
                            "revenue_cents": revenue_cents,
                            "cost_cents": cost_cents,
                            "profit_cents": profit_cents,
                            "capacity_gpus": capacity,
                            "free_gpus": free_gpus,
                        }
                    )

                    totals["revenue_cents"] += revenue_cents
                    totals["cost_cents"] += cost_cents
                    totals["profit_cents"] += profit_cents
                    util_sum += utilization
                    max_ts = next_sim_ts if not max_ts or next_sim_ts > max_ts else max_ts

                totals["avg_utilization"] = round((util_sum / len(regions)) * 100, 2)

                profit_total = totals["profit_cents"]
                gpu_cost = request.expansion_cost_per_gpu_cents
                available_capital = max(state["capital_cents"] + max(profit_total, 0), 0)
                spend_budget = int(available_capital * request.spend_ratio)
                affordable_gpus = available_capital // gpu_cost if gpu_cost > 0 else 0
                planned_gpus = spend_budget // gpu_cost if gpu_cost > 0 else 0
                new_gpus = int(min(planned_gpus, affordable_gpus)) if gpu_cost > 0 else 0
                spent_capex = new_gpus * gpu_cost

                capital = state["capital_cents"] + profit_total - spent_capex
                total_revenue = state["total_revenue_cents"] + totals["revenue_cents"]
                total_cost = state["total_cost_cents"] + totals["cost_cents"]
                total_spent = state["total_spent_cents"] + spent_capex

                update_simulation_state(
                    db,
                    capital_cents=capital,
                    total_revenue_cents=total_revenue,
                    total_cost_cents=total_cost,
                    total_spent_cents=total_spent,
                )
                state.update(
                    {
                        "capital_cents": capital,
                        "total_revenue_cents": total_revenue,
                        "total_cost_cents": total_cost,
                        "total_spent_cents": total_spent,
                    }
                )

                if new_gpus > 0:
                    capacities[hq_region_id] = capacities.get(hq_region_id, HQ_BASE_CAPACITY) + new_gpus
                    upsert_region_capacity(db, hq_region_id, capacities[hq_region_id])

                    hq_entry = next(
                        (item for item in iteration_data if item["region_id"] == hq_region_id or item["code"].lower() == HQ_REGION_CODE),
                        None,
                    )
                    if hq_entry is None:
                        # Create telemetry stub for HQ so growth is visible next payload
                        hq_region = next((r for r in regions if r["id"] == hq_region_id), None)
                        if hq_region:
                            hq_entry = {
                                "region_id": hq_region_id,
                                "code": hq_region["code"],
                                "timestamp": datetime.utcnow(),
                                "utilization": 0.0,
                                "revenue_cents": 0,
                                "cost_cents": 0,
                                "profit_cents": 0,
                                "capacity_gpus": capacities[hq_region_id],
                                "free_gpus": capacities[hq_region_id],
                            }
                            iteration_data.append(hq_entry)
                    if hq_entry:
                        hq_entry["capacity_gpus"] = capacities[hq_region_id]
                        used_after = int(round(hq_entry["utilization"] * hq_entry["capacity_gpus"]))
                        hq_entry["free_gpus"] = max(hq_entry["capacity_gpus"] - used_after, 0)

                    total_spent = state["total_spent_cents"]  # already updated

                for data in iteration_data:
                    record_telemetry(
                        db,
                        region_id=data["region_id"],
                        ts=data["timestamp"],
                        utilization=data["utilization"],
                        revenue_cents=data["revenue_cents"],
                        cost_cents=data["cost_cents"],
                        capital_cents=capital,
                        total_spent_cents=total_spent,
                        electricity_cost_per_kwh=request.electricity_cost_per_kwh,
                        gpu_wattage_w=request.gpu_wattage_w,
                    )

                    regions_payload.append(
                        {
                            "code": data["code"],
                            "timestamp": data["timestamp"].isoformat(),
                            "utilization": round(data["utilization"] * 100, 2),
                            "revenue_cents": data["revenue_cents"],
                            "cost_cents": data["cost_cents"],
                            "profit_cents": data["profit_cents"],
                            "capacity_gpus": data["capacity_gpus"],
                            "free_gpus": data["free_gpus"],
                        }
                    )

                finance_payload = {
                    "capital_cents": capital,
                    "total_revenue_cents": total_revenue,
                    "total_cost_cents": total_cost,
                    "total_spent_cents": total_spent,
                    "profit_cents": profit_total,
                    "spend_ratio": request.spend_ratio,
                    "expansion_cost_per_gpu_cents": gpu_cost,
                    "new_gpu_purchased": new_gpus,
                    "electricity_cost_per_kwh": request.electricity_cost_per_kwh,
                    "gpu_wattage_w": request.gpu_wattage_w,
                    "energy_cost_per_gpu_hour": energy_cost_per_gpu_hour,
                }

                payload = {
                    "iteration": step_index + 1,
                    "timestamp": (max_ts or datetime.utcnow()).isoformat(),
                    "step_hours": step_hours,
                    "totals": totals,
                    "regions": regions_payload,
                    "finance": finance_payload,
                }

                db.commit()

                await self.broadcast(payload)
                step_index += 1
                if max_steps and step_index >= max_steps:
                    break
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
        "continuous": request.continuous,
        "duration_hours": request.duration_hours,
        "step_minutes": request.step_minutes,
        "spend_ratio": request.spend_ratio,
        "expansion_cost_per_gpu_cents": request.expansion_cost_per_gpu_cents,
    }


@router.post("/stop")
async def stop_simulation():
    await manager.stop()
    return {"status": "stopped"}


@router.post("/reset")
async def reset_simulation():
    await manager.stop()
    db = SessionLocal()
    try:
        reset_simulation_data(db)
    finally:
        db.close()
    return {"status": "reset"}


@router.get("/telemetry")
def recent_simulation(limit: int = 200):
    db = SessionLocal()
    try:
        rows = recent_telemetry(db, limit)
    finally:
        db.close()

    buckets: Dict[str, Dict] = {}
    ordered_keys: List[str] = []

    for row in reversed(rows):
        ts_key = row["ts"].isoformat()
        if ts_key not in buckets:
            buckets[ts_key] = {
                "timestamp": ts_key,
                "regions": [],
                "totals": {
                    "revenue_cents": 0,
                    "cost_cents": 0,
                    "profit_cents": 0,
                    "avg_utilization": 0.0,
                },
                "finance": {
                    "capital_cents": row.get("capital_cents", 0),
                    "total_spent_cents": row.get("total_spent_cents", 0),
                    "electricity_cost_per_kwh": row.get("electricity_cost_per_kwh"),
                    "gpu_wattage_w": row.get("gpu_wattage_w"),
                },
            }
            ordered_keys.append(ts_key)

        revenue = int(row["revenue_cents"])
        cost = int(row["cost_cents"])
        utilization = float(row["gpu_utilization"])

        buckets[ts_key]["regions"].append(
            {
                "code": row["code"],
                "utilization": round(utilization * 100, 2),
                "revenue_cents": revenue,
                "cost_cents": cost,
                "profit_cents": revenue - cost,
            }
        )
        totals = buckets[ts_key]["totals"]
        totals["revenue_cents"] += revenue
        totals["cost_cents"] += cost

    for ts_key in ordered_keys:
        bucket = buckets[ts_key]
        totals = bucket["totals"]
        totals["profit_cents"] = totals["revenue_cents"] - totals["cost_cents"]
        if bucket["regions"]:
            avg_util = sum(r["utilization"] for r in bucket["regions"]) / len(bucket["regions"])
            totals["avg_utilization"] = round(avg_util, 2)
        finance = bucket.get("finance", {})
        finance["profit_cents"] = totals["profit_cents"]
        if finance.get("electricity_cost_per_kwh") is not None and finance.get("gpu_wattage_w") is not None:
            try:
                energy_cost = (float(finance["gpu_wattage_w"]) / 1000.0) * float(finance["electricity_cost_per_kwh"])
                finance["energy_cost_per_gpu_hour"] = energy_cost
            except (TypeError, ValueError):
                pass
        bucket["finance"] = finance

    points = [buckets[k] for k in ordered_keys]
    return {"points": points[-limit:]}


@router.websocket("/stream")
async def simulation_stream(websocket: WebSocket):
    await websocket.accept()
    await manager.register(websocket)
