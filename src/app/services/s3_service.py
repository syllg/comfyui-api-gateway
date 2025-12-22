"""
S3 service for uploading and managing files in AWS S3.
"""
import os
import boto3
from typing import Optional
from botocore.exceptions import ClientError, NoCredentialsError
from src.app.settings.setting import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    S3_BUCKET_NAME,
    S3_ENABLED,
    S3_ENDPOINT_URL,
    S3_CUSTOM_DOMAIN,
)
from src.app.utils.log import get_logger

logger = get_logger(__name__)

# S3 client singleton
_s3_client: Optional[boto3.client] = None


def log_s3_configuration():
    """Log non-sensitive S3 configuration for debugging."""
    safe_region = AWS_REGION or "unspecified"
    safe_bucket = S3_BUCKET_NAME or "unspecified"
    safe_endpoint = S3_ENDPOINT_URL or "aws-default"
    logger.debug(
        "S3 config -> enabled=%s bucket=%s region=%s endpoint=%s custom_domain=%s",
        S3_ENABLED,
        safe_bucket,
        safe_region,
        safe_endpoint,
        S3_CUSTOM_DOMAIN or "not-set",
    )
def get_s3_client():
    """Get or create S3 client singleton."""
    global _s3_client
    
    if not S3_ENABLED:
        return None
        
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.warning("S3 credentials not configured. S3 features disabled.")
        return None
        
    if not S3_BUCKET_NAME:
        logger.warning("S3 bucket name not configured. S3 features disabled.")
        return None
    
    if _s3_client is None:
        try:
            client_kwargs = {
                "service_name": "s3",
                "aws_access_key_id": AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
                "region_name": AWS_REGION,
            }
            if S3_ENDPOINT_URL:
                client_kwargs["endpoint_url"] = S3_ENDPOINT_URL

            _s3_client = boto3.client(**client_kwargs)
            # Test connection by checking bucket
            _s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            log_s3_configuration()
            logger.info(f"Connected to S3 bucket: {S3_BUCKET_NAME}")
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            _s3_client = None
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                logger.error(
                    "S3 bucket '%s' not found (endpoint=%s, region=%s)",
                    S3_BUCKET_NAME,
                    S3_ENDPOINT_URL or "aws-default",
                    AWS_REGION,
                )
            else:
                logger.error(
                    "Failed to connect to S3 (bucket=%s endpoint=%s region=%s): %s",
                    S3_BUCKET_NAME or "unspecified",
                    S3_ENDPOINT_URL or "aws-default",
                    AWS_REGION or "unspecified",
                    e,
                )
            _s3_client = None
        except Exception as e:
            logger.error(f"Unexpected error connecting to S3: {e}", exc_info=True)
            _s3_client = None
    
    return _s3_client

def upload_file_to_s3(
    local_file_path: str,
    s3_key: Optional[str] = None,
    bucket_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    """
    Upload a file to S3.
    Args:
        local_file_path: Path to local file to upload
        s3_key: S3 object key (path in bucket). If None, uses filename from local path
        bucket_name: S3 bucket name. If None, uses default from settings
        content_type: MIME type of the file (e.g., 'image/jpeg')
        
    Returns:
        S3 URL of uploaded file, or None if upload failed
    """
    s3_client = get_s3_client()
    if not s3_client:
        return None
    
    bucket = bucket_name or S3_BUCKET_NAME
    
    if not os.path.exists(local_file_path):
        logger.error(f"Local file not found: {local_file_path}")
        return None
    
    if s3_key is None:
        # Use filename from local path
        s3_key = os.path.basename(local_file_path)
    
    logger.debug(
        "Uploading file to S3 -> bucket=%s key=%s endpoint=%s",
        bucket,
        s3_key,
        S3_ENDPOINT_URL or "aws-default",
    )

    try:
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        s3_client.upload_file(
            local_file_path,
            bucket,
            s3_key,
            ExtraArgs=extra_args if extra_args else None,
        )
        
        # Generate S3 URL
        s3_url = _build_public_url(s3_key, bucket)
        logger.info(f"Uploaded file to S3: {s3_url}")
        return s3_url
        
    except ClientError as e:
        logger.error(f"Failed to upload file to S3: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error uploading to S3: {e}", exc_info=True)
        return None

def upload_bytes_to_s3(
    file_bytes: bytes,
    s3_key: str,
    bucket_name: Optional[str] = None,
    content_type: Optional[str] = None,
) -> Optional[str]:
    """
    Upload bytes directly to S3.
    
    Args:
        file_bytes: File content as bytes
        s3_key: S3 object key (path in bucket)
        bucket_name: S3 bucket name. If None, uses default from settings
        content_type: MIME type of the file (e.g., 'image/jpeg')
        
    Returns:
        S3 URL of uploaded file, or None if upload failed
    """
    s3_client = get_s3_client()
    if not s3_client:
        return None
    
    bucket = bucket_name or S3_BUCKET_NAME
    
    try:
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        logger.debug(
            "Uploading bytes to S3 -> bucket=%s key=%s bytes=%d endpoint=%s",
            bucket,
            s3_key,
            len(file_bytes),
            S3_ENDPOINT_URL or "aws-default",
        )

        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_bytes,
            **extra_args,
        )
        
        # Generate S3 URL
        s3_url = _build_public_url(s3_key, bucket)
        logger.info(f"Uploaded bytes to S3: {s3_url}")
        return s3_url
        
    except ClientError as e:
        logger.error(f"Failed to upload bytes to S3: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error uploading to S3: {e}", exc_info=True)
        return None


def delete_file_from_s3(
    s3_key: str,
    bucket_name: Optional[str] = None,
) -> bool:
    """
    Delete a file from S3.
    
    Args:
        s3_key: S3 object key (path in bucket)
        bucket_name: S3 bucket name. If None, uses default from settings
        
    Returns:
        True if deletion successful, False otherwise
    """
    s3_client = get_s3_client()
    if not s3_client:
        return False
    
    bucket = bucket_name or S3_BUCKET_NAME
    
    try:
        s3_client.delete_object(Bucket=bucket, Key=s3_key)
        logger.info(f"Deleted file from S3: {s3_key}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete file from S3: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting from S3: {e}", exc_info=True)
        return False


def _build_public_url(s3_key: str, bucket_name: Optional[str]) -> str:
    """Return the public URL for an object, honoring custom domains if provided."""
    normalized_key = s3_key.lstrip("/")
    if S3_CUSTOM_DOMAIN:
        base = S3_CUSTOM_DOMAIN.rstrip("/")
        return f"{base}/{normalized_key}"

    bucket = bucket_name or S3_BUCKET_NAME
    return f"https://{bucket}.s3.{AWS_REGION}.amazonaws.com/{normalized_key}"


def get_s3_url(s3_key: str, bucket_name: Optional[str] = None) -> str:
    """
    Generate S3 URL for a given key.
    """
    return _build_public_url(s3_key, bucket_name)

