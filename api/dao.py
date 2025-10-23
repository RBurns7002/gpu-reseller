from sqlalchemy import text
from sqlalchemy.orm import Session

def region_exists(db: Session, code: str) -> bool:
    row = db.execute(text("SELECT 1 FROM region WHERE code=:c"), {"c":code}).first()
    return bool(row)

def agent_create(db: Session, region_code:str, agent_id:str, key_hash:str, meta:dict):
    db.execute(text("""
        INSERT INTO agent(id, region_id, name, api_key_hash, meta)
        SELECT :id, r.id, :name, :hash, :meta::jsonb FROM region r WHERE r.code=:code
    """), {"id":agent_id, "name":f"{region_code}-agent", "hash":key_hash, "meta":meta, "code":region_code})

def agent_get(db: Session, agent_id:str):
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
    return [dict(r) for r in rows]


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
