import os

import boto3
from botocore.client import Config
from typing import IO
from loguru import logger

# 原有 MinIO 端点 (主应用使用，保持短名称)
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://minio:9000")

# JuiceFS 专用 MinIO 端点 (跨命名空间，使用 FQDN)
JUICEFS_S3_ENDPOINT = os.environ.get("JUICEFS_S3_ENDPOINT", "http://juicefs-minio.idiot-user-space-storage.svc.cluster.local:9000")

DEFAULT_BUCKET = "default"
USER_SPACE_BUCKET = "user-space"

# MinIO 凭证 (两个 MinIO 共用)
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minio")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minio_password")

# 配置 S3 客户端 (主应用使用)
S3_CLIENT = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    config=Config(signature_version="v4"),  # 必须使用 S3v4 签名
)

# 配置 JuiceFS S3 客户端 (User Pod 使用)
JUICEFS_S3_CLIENT = boto3.client(
    "s3",
    endpoint_url=JUICEFS_S3_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    config=Config(signature_version="v4"),  # 必须使用 S3v4 签名
)


def setup_bucket(bucket_name: str, client=None) -> bool:
    """
    创建存储桶

    Args:
        bucket_name: 存储桶名称
        client: S3 客户端，默认使用主应用客户端
    """
    if client is None:
        client = S3_CLIENT
    try:
        client.create_bucket(Bucket=bucket_name)
        return True
    except Exception as e:
        if e.__class__.__name__ == "BucketAlreadyExists":
            return True
        logger.error(f"Error creating bucket: {e}")
        return False


# init buckets (主应用)
setup_bucket(DEFAULT_BUCKET)
setup_bucket(USER_SPACE_BUCKET)

#---


def upload_object(file_like_obj: IO[bytes], bucket_name: str, object_name: str, client=None) -> bool:
    """
    上传对象
    """
    if client is None:
        client = S3_CLIENT
    try:
        client.upload_fileobj(file_like_obj, bucket_name, object_name)
        return True
    except Exception as e:
        logger.error(f"Error uploading object: {e}")
        return False


def download_object(file_like_obj: IO[bytes], bucket_name: str, object_name: str, client=None) -> bool:
    """
    下载对象
    """
    if client is None:
        client = S3_CLIENT
    try:
        client.download_fileobj(bucket_name, object_name, file_like_obj)
        return True
    except Exception as e:
        logger.error(f"Error downloading object: {e}")
        return False


def delete_object(bucket_name: str, object_name: str, client=None) -> bool:
    """
    删除对象
    """
    if client is None:
        client = S3_CLIENT
    try:
        client.delete_object(Bucket=bucket_name, Key=object_name)
        return True
    except Exception as e:
        logger.error(f"Error deleting object: {e}")
        return False


def copy_object(source_bucket: str, source_key: str, dest_bucket: str, dest_key: str, client=None) -> bool:
    """
    复制对象
    """
    if client is None:
        client = S3_CLIENT
    try:
        copy_source = {"Bucket": source_bucket, "Key": source_key}
        client.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
        return True
    except Exception as e:
        logger.error(f"Error copying object: {e}")
        return False


def object_exists(bucket_name: str, object_key: str, client=None) -> bool:
    """
    检查对象是否存在
    """
    if client is None:
        client = S3_CLIENT
    try:
        client.head_object(Bucket=bucket_name, Key=object_key)
        return True
    except Exception:
        return False


def rename_object(bucket_name: str, old_key: str, new_key: str, client=None) -> bool:
    """
    重命名对象（通过复制+删除实现）
    """
    if client is None:
        client = S3_CLIENT
    try:
        # 先复制到新位置
        if copy_object(bucket_name, old_key, bucket_name, new_key, client=client):
            # 复制成功后删除原对象
            return delete_object(bucket_name, old_key, client=client)
        return False
    except Exception as e:
        logger.error(f"Error renaming object: {e}")
        return False