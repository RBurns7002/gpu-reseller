from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, Optional


def _rows_to_dicts(rows):
    return [dict(r) for r in rows]

def region_exists(db: Session, code: str) -> bool:
    row = db.execute(text("SELECT 1 FROM region WHERE code=:c"), {"c":code}).first()
    return bool(row)

def agent_create(db: Session, region_code: str, agent_id: str, key_hash: str, meta: dict):
    db.execute(text("""
        INSERT INTO agent(id, region_id, name, api_key_hash, meta)
        SELECT :id, r.id, :name, :hash, :meta::jsonb FROM region r WHERE r.code=:code
    """), {"id":agent_id, "name":f"{region_code}-agent", "hash":key_hash, "meta":meta, "code":region_code})

def agent_get(db: Session, agent_id: str):
    row = db.execute(text("""
        SELECT a.api_key_hash, r.code as region
        FROM agent a JOIN region r ON r.id=a.region_id
        WHERE a.id=:id
    """), {"id":agent_id}).mappings().first()
    return dict(row) if row else None

def region_upsert_metrics(
    db: Session,
    code: str,
    total_gpus: int,
    free_gpus: int,
    util: float,
    status: str = "healthy",
):
    db.execute(
        text(
            """
      INSERT INTO region_stats(region_id,total_gpus,free_gpus,utilization,avg_queue_sec)
      SELECT id,:t,:f,:u,0 FROM region WHERE code=:c
    """
        ),
        {"t": total_gpus, "f": free_gpus, "u": util, "c": code},
    )
    db.execute(
        text(
            """
      UPDATE region
      SET status = :status
      WHERE code = :code
    """
        ),
        {"status": status, "code": code},
    )
    db.commit()

def latest_regions(db: Session):
    rows = db.execute(text("""
        SELECT r.code,
               r.status,
               COALESCE(s.total_gpus, 0) AS total_gpus,
               COALESCE(s.free_gpus, 0)  AS free_gpus,
               COALESCE(s.utilization, 0) AS utilization
        FROM region r
        LEFT JOIN LATERAL (
          SELECT total_gpus, free_gpus, utilization
          FROM region_stats rs
          WHERE rs.region_id = r.id
          ORDER BY ts DESC
          LIMIT 1
        ) s ON TRUE
        ORDER BY r.code ASC
    """)).mappings().all()
    return _rows_to_dicts(rows)


def price_for_region(db: Session, code:str) -> dict:
    row = db.execute(text("""
      SELECT pb.standard_cph_cents, pb.priority_cph_cents, pb.spot_cph_cents
      FROM pricebook pb JOIN region r ON r.id=pb.region_id
      WHERE r.code=:c ORDER BY effective_at DESC LIMIT 1
    """), {"c":code}).mappings().first()
    return ({"standard":1.00,"priority":1.40,"spot":0.75} if not row else
            {"standard":row['standard_cph_cents']/100.0,
             "priority":row['priority_cph_cents']/100.0,
             "spot":row['spot_cph_cents']/100.0})


def regions_financial_snapshot(db: Session):
    rows = db.execute(
        text(
            """
        SELECT id, code, revenue_cents, cost_cents, simulated_time
        FROM region
        ORDER BY code ASC
        """
        )
    ).mappings().all()
    return _rows_to_dicts(rows)


def latest_region_stats_map(db: Session):
    rows = db.execute(
        text(
            """
        SELECT DISTINCT ON (region_id)
               region_id,
               total_gpus,
               free_gpus,
               utilization
        FROM region_stats
        ORDER BY region_id, ts DESC
        """
        )
    ).mappings().all()
    return {row["region_id"]: dict(row) for row in rows}


def update_region_financials(
    db: Session,
    region_id: str,
    revenue_delta: int,
    cost_delta: int,
    simulated_time,
    status: Optional[str] = None,
):
    if status is None:
        params = {"rev": revenue_delta, "cost": cost_delta, "sim_time": simulated_time, "rid": region_id}
        db.execute(
            text(
                """
            UPDATE region
            SET revenue_cents = revenue_cents + :rev,
                cost_cents = cost_cents + :cost,
                simulated_time = :sim_time
            WHERE id = :rid
            """
            ),
            params,
        )
    else:
        params = {
            "rev": revenue_delta,
            "cost": cost_delta,
            "sim_time": simulated_time,
            "rid": region_id,
            "status": status,
        }
        db.execute(
            text(
                """
            UPDATE region
            SET revenue_cents = revenue_cents + :rev,
                cost_cents = cost_cents + :cost,
                simulated_time = :sim_time,
                status = :status
            WHERE id = :rid
            """
            ),
            params,
        )


def record_telemetry(
    db: Session,
    region_id: str,
    ts,
    utilization: float,
    revenue_cents: int,
    cost_cents: int,
    capital_cents: int,
    total_spent_cents: int,
    electricity_cost_per_kwh: float,
    gpu_wattage_w: float,
):
    db.execute(
        text(
            """
        INSERT INTO telemetry(
            region_id,
            ts,
            gpu_utilization,
            revenue_cents,
            cost_cents,
            capital_cents,
            total_spent_cents,
            electricity_cost_per_kwh,
            gpu_wattage_w
        )
        VALUES (:rid, :ts, :util, :rev, :cost, :capital, :spent, :kwh_cost, :wattage)
        """
        ),
        {
            "rid": region_id,
            "ts": ts,
            "util": utilization,
            "rev": revenue_cents,
            "cost": cost_cents,
            "capital": capital_cents,
            "spent": total_spent_cents,
            "kwh_cost": electricity_cost_per_kwh,
            "wattage": gpu_wattage_w,
        },
    )


def recent_telemetry(db: Session, limit: int = 200):
    rows = db.execute(
        text(
            """
        SELECT t.region_id,
               r.code,
               t.ts,
               t.gpu_utilization,
               t.revenue_cents,
               t.cost_cents,
               t.capital_cents,
               t.total_spent_cents,
               t.electricity_cost_per_kwh,
               t.gpu_wattage_w
        FROM telemetry t
        JOIN region r ON r.id = t.region_id
        ORDER BY t.ts DESC
        LIMIT :limit
        """
        ),
        {"limit": limit},
    ).mappings().all()
    return _rows_to_dicts(rows)


def ensure_region_exists(db: Session, code: str, name: str) -> str:
    row = db.execute(text("SELECT id FROM region WHERE code=:code"), {"code": code}).mappings().first()
    if row:
        return row["id"]

    inserted = db.execute(
        text(
            """
        INSERT INTO region(code, name, status, spot_multiplier)
        VALUES (:code, :name, 'healthy', 1.0)
        ON CONFLICT (code) DO NOTHING
        RETURNING id
        """
        ),
        {"code": code, "name": name},
    ).mappings().first()
    db.commit()

    if inserted:
        return inserted["id"]

    row = db.execute(text("SELECT id FROM region WHERE code=:code"), {"code": code}).mappings().first()
    if not row:
        raise RuntimeError(f"Unable to ensure region '{code}' exists")
    return row["id"]


def get_simulation_state(db: Session) -> Dict:
    row = db.execute(
        text(
            """
        SELECT id,
               capital_cents,
               total_revenue_cents,
               total_cost_cents,
               total_spent_cents,
               last_reset
        FROM simulation_state
        WHERE id = 1
        """
        )
    ).mappings().first()
    if row:
        return dict(row)
    db.execute(text("INSERT INTO simulation_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
    db.commit()
    return get_simulation_state(db)


def update_simulation_state(
    db: Session,
    capital_cents: int,
    total_revenue_cents: int,
    total_cost_cents: int,
    total_spent_cents: int,
):
    db.execute(
        text(
            """
        UPDATE simulation_state
        SET capital_cents = :capital,
            total_revenue_cents = :revenue,
            total_cost_cents = :cost,
            total_spent_cents = :spent
        WHERE id = 1
        """
        ),
        {
            "capital": capital_cents,
            "revenue": total_revenue_cents,
            "cost": total_cost_cents,
            "spent": total_spent_cents,
        },
    )


def get_region_capacities(db: Session) -> Dict[str, int]:
    rows = db.execute(
        text(
            """
        SELECT region_id, capacity_gpus
        FROM simulation_region
        """
        )
    ).mappings().all()
    return {row["region_id"]: row["capacity_gpus"] for row in rows}


def upsert_region_capacity(db: Session, region_id: str, capacity_gpus: int):
    db.execute(
        text(
            """
        INSERT INTO simulation_region(region_id, capacity_gpus)
        VALUES (:rid, :capacity)
        ON CONFLICT (region_id)
        DO UPDATE SET capacity_gpus = EXCLUDED.capacity_gpus
        """
        ),
        {"rid": region_id, "capacity": capacity_gpus},
    )


def reset_simulation_data(db: Session):
    db.execute(text("TRUNCATE telemetry"))
    db.execute(text("TRUNCATE region_stats"))
    db.execute(
        text(
            """
        UPDATE region
        SET revenue_cents = 0,
            cost_cents = 0,
            simulated_time = now()
        """
        )
    )
    db.execute(text("DELETE FROM simulation_region"))
    db.execute(
        text(
            """
        UPDATE simulation_state
        SET capital_cents = 0,
            total_revenue_cents = 0,
            total_cost_cents = 0,
            total_spent_cents = 0,
            last_reset = now()
        WHERE id = 1
        """
        )
    )
    db.commit()
