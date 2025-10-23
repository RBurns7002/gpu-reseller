# api/routes/telemetry.py
from fastapi import APIRouter, HTTPException
import boto3, os
from botocore.client import Config

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

def minio_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

@router.get("")
def telemetry_root():
    """Return system health snapshot: regions + MinIO buckets."""
    try:
        s3 = minio_client()
        # List all buckets
        buckets = s3.list_buckets()
        bucket_data = []
        for b in buckets.get("Buckets", []):
            name = b["Name"]
            objs = s3.list_objects_v2(Bucket=name)
            count = objs.get("KeyCount", 0)
            bucket_data.append({"bucket": name, "objects": count})
        return {"status": "ok", "storage": bucket_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
