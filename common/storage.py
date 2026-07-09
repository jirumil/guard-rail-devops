"""
Thin storage abstraction.

Phase 1/2 (local): backed by MinIO, speaking the S3 API.
Phase 3 (Azure):   swap ObjectStorage's implementation to use the
                    azure-storage-blob SDK against Azure Blob Storage.
                    Callers in app.py / worker.py never change.
"""
import json
import os
from abc import ABC, abstractmethod

import boto3
from botocore.client import Config


class ObjectStorage(ABC):
    @abstractmethod
    def upload(self, key: str, local_path: str, content_type: str) -> str:
        """Uploads a file and returns a publicly retrievable URL."""

    @abstractmethod
    def get_url(self, key: str) -> str:
        ...


class MinioStorage(ObjectStorage):
    """S3-compatible storage. Same SDK shape Azure Blob's S3-compat
    tooling does NOT use — this class is the only thing Phase 3 touches."""

    def __init__(self):
        self.bucket = os.environ.get("STORAGE_BUCKET", "pixelvault-processed")
        self.public_base_url = os.environ.get(
            "STORAGE_PUBLIC_URL", "http://localhost:9000"
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("STORAGE_ENDPOINT", "http://minio:9000"),
            aws_access_key_id=os.environ.get("STORAGE_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.environ.get("STORAGE_SECRET_KEY", "minioadmin"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        existing = [b["Name"] for b in self.client.list_buckets().get("Buckets", [])]
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
            }],
        }
        self.client.put_bucket_policy(Bucket=self.bucket, Policy=json.dumps(policy))

    def upload(self, key: str, local_path: str, content_type: str) -> str:
        self.client.upload_file(
            local_path, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return self.get_url(key)

    def get_url(self, key: str) -> str:
        return f"{self.public_base_url}/{self.bucket}/{key}"


def get_storage() -> ObjectStorage:
    # Single seam for Phase 3: return AzureBlobStorage() here instead.
    return MinioStorage()