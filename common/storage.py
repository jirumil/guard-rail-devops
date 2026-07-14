"""
Thin storage abstraction.

Phase 1/2 (local): backed by MinIO, speaking the S3 API.
Phase 3 (Azure):   backed by Azure Blob Storage via the azure-storage-blob
                    SDK. Callers in app.py / worker.py never change —
                    they only ever call get_storage() and use whatever
                    ObjectStorage implementation comes back.

Provider selection is driven entirely by the STORAGE_PROVIDER env var:
    STORAGE_PROVIDER=azure  (or unset) -> AzureBlobStorage  [default]
    STORAGE_PROVIDER=minio             -> MinioStorage      [local dev]

ARCHITECTURE NOTE (blob-routing refactor): the API now uploads a file to
this storage layer at ingest time and enqueues a storage KEY, not a
filesystem path. The worker downloads that key to its own private
scratch space before scanning. Neither side ever assumes the other's
local disk is reachable — that assumption was the root cause of the
"file not found" bug this refactor eliminates. download() exists
specifically to support that: the worker's only way to get the file's
bytes is through this interface, the same as upload always has been.
"""
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone


class ObjectStorage(ABC):
    @abstractmethod
    def upload(self, key: str, local_path: str, content_type: str) -> str:
        """Uploads a file and returns a retrievable URL."""

    @abstractmethod
    def download(self, key: str, local_path: str) -> None:
        """Downloads a stored object to a local path. This is how the
        worker gets file bytes onto its own disk — never by assuming
        another container's filesystem is reachable."""

    @abstractmethod
    def get_url(self, key: str) -> str:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Removes a file — used to enforce immediate post-scan deletion."""


# ---------------------------------------------------------------------------
# MinIO (Phase 1/2 — local dev)
# ---------------------------------------------------------------------------
class MinioStorage(ObjectStorage):
    def __init__(self):
        import boto3
        from botocore.client import Config

        self.bucket = os.environ.get("STORAGE_BUCKET", "guardrail-quarantine")
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
        # Intentionally NOT public-read — this is a quarantine sandbox,
        # not a CDN. Access is internal-only.

    def upload(self, key: str, local_path: str, content_type: str) -> str:
        self.client.upload_file(
            local_path, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return self.get_url(key)

    def download(self, key: str, local_path: str) -> None:
        self.client.download_file(self.bucket, key, local_path)

    def get_url(self, key: str) -> str:
        return f"{self.public_base_url}/{self.bucket}/{key}"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


# ---------------------------------------------------------------------------
# Azure Blob Storage (Phase 3 — cloud target)
# ---------------------------------------------------------------------------
class AzureBlobStorage(ObjectStorage):
    """
    Talks to Azure Blob Storage directly via account name + account key.
    Anonymous blob access is disabled on the storage account by design,
    so every retrievable URL returned by this class is a short-lived SAS
    URL — there is no "plain" public URL here.
    """

    def __init__(self):
        from azure.storage.blob import BlobServiceClient

        self.account_name = os.environ["AZURE_STORAGE_ACCOUNT_NAME"]
        self.account_key = os.environ["AZURE_STORAGE_ACCOUNT_KEY"]
        self.container_name = os.environ.get("STORAGE_BUCKET", "guardrail-quarantine")
        self.sas_ttl_minutes = int(os.environ.get("STORAGE_SAS_TTL_MINUTES", "15"))

        account_url = f"https://{self.account_name}.blob.core.windows.net"
        self.service_client = BlobServiceClient(
            account_url=account_url, credential=self.account_key
        )
        self._ensure_container()

    def _ensure_container(self):
        from azure.core.exceptions import ResourceExistsError

        container_client = self.service_client.get_container_client(self.container_name)
        try:
            container_client.create_container()
        except ResourceExistsError:
            pass

    def upload(self, key: str, local_path: str, content_type: str) -> str:
        from azure.storage.blob import ContentSettings

        blob_client = self.service_client.get_blob_client(
            container=self.container_name, blob=key
        )
        with open(local_path, "rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        return self.get_url(key)

    def download(self, key: str, local_path: str) -> None:
        blob_client = self.service_client.get_blob_client(
            container=self.container_name, blob=key
        )
        with open(local_path, "wb") as f:
            download_stream = blob_client.download_blob()
            f.write(download_stream.readall())

    def get_url(self, key: str) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=key,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=self.sas_ttl_minutes),
        )
        base_url = (
            f"https://{self.account_name}.blob.core.windows.net/"
            f"{self.container_name}/{key}"
        )
        return f"{base_url}?{sas_token}"

    def delete(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        blob_client = self.service_client.get_blob_client(
            container=self.container_name, blob=key
        )
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
def get_storage() -> ObjectStorage:
    provider = os.environ.get("STORAGE_PROVIDER", "azure").strip().lower()
    if provider == "minio":
        return MinioStorage()
    return AzureBlobStorage()
