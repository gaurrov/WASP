import time
from functools import lru_cache

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import ClientError, EndpointConnectionError

from app.config import get_settings


@lru_cache
def get_s3() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket(retries: int = 30, delay: float = 1.0) -> None:
    """Create the documents bucket, waiting for the storage service to come up."""
    s3, bucket = get_s3(), get_settings().s3_bucket
    for attempt in range(retries):
        try:
            s3.head_bucket(Bucket=bucket)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
                s3.create_bucket(Bucket=bucket)
                return
            if attempt == retries - 1:
                raise
        except EndpointConnectionError:
            if attempt == retries - 1:
                raise
        time.sleep(delay)
