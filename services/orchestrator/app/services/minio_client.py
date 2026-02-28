"""MinIO client for file storage."""
from minio import Minio
from datetime import datetime
import os
import io
from app.utils.logger import logger


class MinIOClient:
    """Client for MinIO object storage."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        """Initialize MinIO client."""
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.raw_bucket = "raw-documents"
        self.images_bucket = "extracted-images"

        # Ensure buckets exist
        self._ensure_buckets()

    def _ensure_buckets(self):
        """Ensure required buckets exist."""
        for bucket in [self.raw_bucket, self.images_bucket]:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
                logger.info(f"Created bucket: {bucket}")

    def upload_file(self, file_path: str, file_data: bytes) -> str:
        """Upload file to MinIO raw-documents bucket.

        Args:
            file_path: Original file path or filename
            file_data: File content as bytes

        Returns:
            Object path in format: bucket/YYYY-MM-DD/filename
        """
        # Generate object path: YYYY-MM-DD/filename
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        filename = os.path.basename(file_path)
        object_name = f"{date_prefix}/{filename}"

        # Upload to MinIO
        self.client.put_object(
            self.raw_bucket,
            object_name,
            io.BytesIO(file_data),
            length=len(file_data)
        )

        full_path = f"{self.raw_bucket}/{object_name}"
        logger.info(f"Uploaded file to MinIO: {full_path}")

        return full_path

    def get_file_url(self, object_path: str) -> str:
        """Get presigned URL for file access.

        Args:
            object_path: Full object path (bucket/date/filename)

        Returns:
            Presigned URL valid for 1 hour
        """
        # Parse bucket and object name
        parts = object_path.split("/", 1)
        bucket = parts[0]
        object_name = parts[1] if len(parts) > 1 else ""

        # Generate presigned URL (valid for 1 hour)
        url = self.client.presigned_get_object(bucket, object_name, expires=3600)
        return url
