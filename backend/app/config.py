from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    environment: str = 'development'
    database_url: str = 'sqlite:///./.data/workspace.db'
    storage_backend: str = 'local'
    storage_path: str = '.data/objects'
    s3_endpoint: str | None = None
    s3_bucket: str = 'workspace'
    s3_sse: str = 'AES256'
    aws_region: str = 'us-east-1'
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_bearer_token_bedrock: str | None = None
    session_secret: str = 'development-only-change-this-before-deployment'
    secure_cookies: bool = False
    public_url: str = 'http://localhost:5173'
    auth_mode: str = 'demo'
    oidc_metadata_url: str = ''
    oidc_client_id: str = ''
    oidc_client_secret: str = ''
    llm_provider: str = 'demo'
    llm_model: str = ''
    openai_api_key: str = ''
    azure_openai_api_key: str = ''
    azure_openai_endpoint: str = ''
    azure_openai_api_version: str = '2024-10-21'
    max_input_tokens: int = 24000
    max_output_tokens: int = 10000
    llm_timeout: int = 120
    renderer_url: str = 'http://localhost:3001'
    renderer_secret: str = 'development-renderer-secret'
    embedded_worker: bool = True
    upload_max_mb: int = 15
    retention_days: int = 90
    download_ttl: int = 300
    jobs_per_hour: int = 30
    ocr_enabled: bool = False

    def validate_runtime(self):
        if self.environment == 'production':
            if (self.auth_mode != 'oidc' or self.llm_provider == 'demo' or not self.secure_cookies
                or len(self.session_secret) < 32 or 'development' in self.session_secret
                or 'development' in self.renderer_secret or self.storage_backend != 's3'
                or not self.database_url.startswith('postgresql') or not self.public_url.startswith('https://')):
                raise RuntimeError('Production requires OIDC, a live provider, HTTPS secure cookies, strong secrets, PostgreSQL and S3.')
        if self.auth_mode == 'oidc' and not all([self.oidc_metadata_url, self.oidc_client_id, self.oidc_client_secret]):
            raise RuntimeError('Configure OIDC metadata URL, client ID and secret.')
        Path('.data').mkdir(exist_ok=True)


settings = Settings()
