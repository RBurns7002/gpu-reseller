import hashlib
from fastapi import Header, HTTPException

def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()

async def require_agent(key: str = Header(None, alias='X-Agent-Key')):
    if not key:
        raise HTTPException(status_code=401, detail='missing agent key')
    return key
