# api/routes/files.py
from fastapi import APIRouter, HTTPException, Query
from storage import ensure_bucket, list_objects, presign_put, USER_BUCKET

router = APIRouter(prefix="/files", tags=["files"])

@router.get("/list")
def list_files(bucket: str = Query(USER_BUCKET), prefix: str = Query("")):
    """List all files in a bucket/prefix."""
    try:
        ensure_bucket(bucket)
        items = list_objects(bucket, prefix)
        return {"bucket": bucket, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List error: {e}")

@router.post("/upload-url")
def get_upload_url(bucket: str = Query(USER_BUCKET), key: str = Query(...)):
    """Return presigned URL for uploading a file."""
    try:
        ensure_bucket(bucket)
        url = presign_put(bucket, key)
        return {"url": url, "bucket": bucket, "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Presign error: {e}")
