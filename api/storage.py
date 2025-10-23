# api/storage.py
import os
from datetime import timedelta, datetime
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.client import Config

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", "")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

USER_BUCKET = "user-data"
JOBS_BUCKET = "gpu-jobs"

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

def ensure_bucket(name: str):
    s3 = _s3()
    try:
        s3.head_bucket(Bucket=name)
    except Exception:
        s3.create_bucket(Bucket=name)

def list_objects(bucket: str, prefix: str = ""):
    s3 = _s3()
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix or "")
    contents = resp.get("Contents", [])
    return [obj["Key"] for obj in contents]

def presign_put(bucket: str, key: str, expires_seconds: int = 3600) -> str:
    s3 = _s3()
    ensure_bucket(bucket)
    return s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds,
        HttpMethod="PUT",
    )

def _browserize(url: str) -> str:
    """Replace internal host with public endpoint so the browser can reach it."""
    u = urlparse(url)
    if MINIO_PUBLIC_ENDPOINT:
        pu = urlparse(MINIO_PUBLIC_ENDPOINT)
        u = u._replace(scheme=pu.scheme or u.scheme, netloc=pu.netloc)
    elif u.hostname in {"minio", "minio.local"}:
        # Fallback for local dev
        u = u._replace(netloc="localhost:9000")
    return urlunparse(u)

def presign_put_public(bucket: str, key: str, expires_seconds: int = 3600) -> str:
    return _browserize(presign_put(bucket, key, expires_seconds))
