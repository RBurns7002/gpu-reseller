from pydantic import BaseModel
from typing import List, Optional, Dict

class AgentRegisterReq(BaseModel):
    region_code: str
    agent_name: str
    meta: Dict = {}
class AgentRegisterRes(BaseModel):
    agent_id: str
    agent_api_key: str

class NodeDesc(BaseModel):
    hostname: str
    gpu_model: str
    gpus: int
    vram_gb: int
    state: str = 'ready'
    labels: Dict = {}

class HeartbeatReq(BaseModel):
    agent_id: str
    metrics: Dict
    nodes: List[NodeDesc]

class AvailabilityItem(BaseModel):
    region: str
    status: str
    total_gpus: int
    free_gpus: int
    utilization: float
    est_wait_minutes: Dict[str, int]
    prices: Dict[str, float]

class JobCreateReq(BaseModel):
    image: str
    cmd: List[str]
    gpus: int = 1
    gpu_model: str = 'DGX Spark'
    queue: str = 'standard'
    preferred_region: Optional[str] = None
    region_lock: bool = False

class JobCreateRes(BaseModel):
    job_id: str
    region: str
    queue: str
    eta_minutes: int
