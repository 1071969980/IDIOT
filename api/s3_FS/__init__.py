import boto3
from botocore.client import Config
from typing import BinaryIO
from loguru import logger

S3_ENDPOINT = "http://seaweed:8333"

CONTRACT_REVIEW_BUCKET = "contract-review"

# 配置 S3 客户端
S3_CLIENT = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,  # SeaweedFS S3 服务地址
    aws_access_key_id="any",                # SeaweedFS 默认访问密钥
    aws_secret_access_key="any",            # SeaweedFS 默认密钥  # noqa: S106
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
setup_bucket(CONTRACT_REVIEW_BUCKET)

#---

def upload_object(file_like_obj: BinaryIO, bucket_name: str, object_name: str) -> bool:
    """
    上传对象
    """
    try:
        S3_CLIENT.upload_fileobj(file_like_obj, bucket_name, object_name)
        return True
    except Exception as e:
        logger.error(f"Error uploading object: {e}")
        return False

def download_object(file_like_obj: BinaryIO, bucket_name: str, object_name: str) -> bool:
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