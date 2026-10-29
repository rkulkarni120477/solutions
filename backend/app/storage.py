from pathlib import Path
import boto3
from botocore.config import Config
from .config import settings


class Storage:
    def __init__(self):
        self.root = Path(settings.storage_path).resolve()
        self.client = None
        if settings.storage_backend == 's3':
            self.client = boto3.client('s3', endpoint_url=settings.s3_endpoint, region_name=settings.aws_region,
                                       aws_access_key_id=settings.aws_access_key_id, aws_secret_access_key=settings.aws_secret_access_key,
                                       aws_session_token=settings.aws_session_token,
                                       config=Config(connect_timeout=10, read_timeout=30, retries={'max_attempts': 2}))

    def path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Invalid object key')
        return path

    def put(self, key, data, content_type='application/octet-stream'):
        if self.client:
            options = {'ServerSideEncryption': settings.s3_sse} if settings.s3_sse else {}
            self.client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type, **options)
        else:
            path = self.path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def get(self, key):
        if self.client:
            return self.client.get_object(Bucket=settings.s3_bucket, Key=key)['Body'].read()
        return self.path(key).read_bytes()

    def delete(self, key):
        if self.client:
            self.client.delete_object(Bucket=settings.s3_bucket, Key=key)
        else:
            self.path(key).unlink(missing_ok=True)


storage = Storage()
