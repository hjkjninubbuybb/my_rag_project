"""MinIO client for file storage."""

from datetime import timedelta
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.utils.logger import logger


class MinIOClient:
    """MinIO client for managing file storage.

    Buckets:
    - raw-documents: Original uploaded PDF files
    - extracted-images: Extracted images from PDFs
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
    ):
        """Initialize MinIO client.

        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000")
            access_key: MinIO access key
            secret_key: MinIO secret key
            secure: Use HTTPS if True
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._ensure_buckets()

    def _ensure_buckets(self):
        """Ensure required buckets exist."""
        buckets = ["raw-documents", "extracted-images"]
        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info(f"Created MinIO bucket: {bucket}")
            except S3Error as e:
                logger.error(f"Failed to create bucket {bucket}: {e}")
                raise

    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file to MinIO.

        Args:
            bucket_name: Target bucket name
            object_name: Object name (path) in bucket
            file_data: File binary data
            content_type: MIME type

        Returns:
            Object name (path) in bucket
        """
        try:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )
            logger.info(f"Uploaded {object_name} to {bucket_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Failed to upload {object_name}: {e}")
            raise

    def download_file(self, bucket_name: str, object_name: str) -> bytes:
        """Download file from MinIO.

        Args:
            bucket_name: Source bucket name
            object_name: Object name (path) in bucket

        Returns:
            File binary data
        """
        try:
            response = self.client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Failed to download {object_name}: {e}")
            raise

    def get_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate presigned URL for temporary access.

        Args:
            bucket_name: Bucket name
            object_name: Object name (path) in bucket
            expires: URL expiration time

        Returns:
            Presigned URL
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires,
            )
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
            raise

    def delete_file(self, bucket_name: str, object_name: str):
        """Delete file from MinIO.

        Args:
            bucket_name: Bucket name
            object_name: Object name (path) in bucket
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted {object_name} from {bucket_name}")
        except S3Error as e:
            logger.error(f"Failed to delete {object_name}: {e}")
            raise

    def list_files(self, bucket_name: str, prefix: Optional[str] = None) -> list[str]:
        """List files in bucket.

        Args:
            bucket_name: Bucket name
            prefix: Filter by prefix (optional)

        Returns:
            List of object names
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=True,
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Failed to list files in {bucket_name}: {e}")
            raise

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """Check if file exists in bucket.

        Args:
            bucket_name: Bucket name
            object_name: Object name (path) in bucket

        Returns:
            True if file exists
        """
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False
