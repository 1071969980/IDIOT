import boto3
from botocore.client import Config
from typing import IO
from loguru import logger

S3_ENDPOINT = "http://minio:9000"

DEFAULT_BUCKET = "default"
USER_SPACE_BUCKET = "user-space"

# 配置 S3 客户端
S3_CLIENT = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id="minio",
    aws_secret_access_key="minio_password",  # noqa: S106
    config=Config(signature_version="v4"), # 必须使用 S3v4 签名
)

def setup_bucket(bucket_name:str) -> bool:
    """
    创建存储桶
    """
    try:
        S3_CLIENT.create_bucket(Bucket=bucket_name)
        return True
    except Exception as e:
        if e.__class__.__name__ == "BucketAlreadyExists":
            return True
        logger.error(f"Error creating bucket: {e}")
        return False


# init buckets
setup_bucket(DEFAULT_BUCKET)
setup_bucket(USER_SPACE_BUCKET)

#---

def upload_object(file_like_obj: IO[bytes], bucket_name: str, object_name: str) -> bool:
    """
    上传对象
    """
    try:
        S3_CLIENT.upload_fileobj(file_like_obj, bucket_name, object_name)
        return True
    except Exception as e:
        logger.error(f"Error uploading object: {e}")
        return False

def download_object(file_like_obj: IO[bytes], bucket_name: str, object_name: str) -> bool:
    """
    下载对象
    """
    try:
        S3_CLIENT.download_fileobj(bucket_name, object_name, file_like_obj)
        return True
    except Exception as e:
        logger.error(f"Error downloading object: {e}")
        return False
    
def delete_object(bucket_name: str, object_name: str) -> bool:
    """
    删除对象
    """
    try:
        S3_CLIENT.delete_object(Bucket=bucket_name, Key=object_name)
        return True
    except Exception as e:
        logger.error(f"Error deleting object: {e}")
        return False

def copy_object(source_bucket: str, source_key: str, dest_bucket: str, dest_key: str) -> bool:
    """
    复制对象
    """
    try:
        copy_source = {'Bucket': source_bucket, 'Key': source_key}
        S3_CLIENT.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
        return True
    except Exception as e:
        logger.error(f"Error copying object: {e}")
        return False

def object_exists(bucket_name: str, object_key: str) -> bool:
    """
    检查对象是否存在
    """
    try:
        S3_CLIENT.head_object(Bucket=bucket_name, Key=object_key)
        return True
    except Exception:
        return False


def rename_object(bucket_name: str, old_key: str, new_key: str) -> bool:
    """
    重命名对象（通过复制+删除实现）
    """
    try:
        # 先复制到新位置
        if copy_object(bucket_name, old_key, bucket_name, new_key):
            # 复制成功后删除原对象
            return delete_object(bucket_name, old_key)
        return False
    except Exception as e:
        logger.error(f"Error renaming object: {e}")
        return False