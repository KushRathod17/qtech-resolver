"""
Storage for user-uploaded files (ticket attachments, avatars).

Local disk is fine for local development and for the test suite, but it's the
wrong choice for a free-tier host: the filesystem there is ephemeral, so
anything written to it vanishes on the next deploy or restart (Render's free
web services don't support a persistent disk at all). Set the S3_* settings
below to point at any S3-compatible bucket -- Backblaze B2 is what
DEPLOYING.md walks through, since its free tier needs no credit card at all
(Cloudflare R2, AWS S3, and others all work too, if you have a preference) --
and uploads go there instead; leave them unset and everything falls back to
local disk under uploads/, exactly like before Slice/Phase 4.

The choice is made once, at import time, from config -- not per-request -- so
a single deploy is consistently on one backend or the other.
"""
from pathlib import Path

from .config import settings

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploads"


class LocalDiskStorage:
    """The original behaviour: files live under backend/uploads/<key>."""

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._resolve(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink(missing_ok=True)

    def _resolve(self, key: str) -> Path:
        # `key` is built from server-generated names (see tickets.py /
        # users.py), never straight from a client filename, but resolve +
        # verify anyway -- belt and braces against any future caller mistake.
        candidate = (UPLOAD_ROOT / key).resolve()
        if UPLOAD_ROOT.resolve() not in candidate.parents:
            raise ValueError(f"refusing to touch a path outside uploads/: {key!r}")
        return candidate


class S3Storage:
    """Any S3-compatible bucket: Cloudflare R2, AWS S3, Backblaze B2, MinIO."""

    def __init__(self):
        import boto3
        from botocore.client import Config as BotoConfig

        self._bucket = settings.S3_BUCKET_NAME
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name=settings.S3_REGION or "auto",
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        # S3-compatible DELETE is idempotent -- no error if the key is
        # already gone, so callers don't need to check existence first.
        self._client.delete_object(Bucket=self._bucket, Key=key)


def _build_storage():
    if settings.S3_BUCKET_NAME and settings.S3_ENDPOINT_URL:
        return S3Storage()
    return LocalDiskStorage()


storage = _build_storage()
