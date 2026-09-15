"""应用配置：从环境变量 / .env 读取"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 应用
    app_name: str = "OJ API"
    debug: bool = True

    # 数据库
    database_url: str = "postgresql+asyncpg://oj:oj_password@localhost:5432/oj"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # 对象存储（MinIO）：storage_backend 决定题目数据/头像的后端，minio | local
    storage_backend: str = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "oju"  # MinIO 要求用户名 ≥3 字符，与 compose 中 MINIO_ROOT_USER 一致
    minio_secret_key: str = "oj_password"
    minio_secure: bool = False
    minio_bucket_problems: str = "oj-problems"
    minio_bucket_avatars: str = "oj-avatars"

    # 判题网关（gRPC，独立于 HTTP 端口）
    judge_grpc_port: int = 50051
    judge_gateway_tokens: list[str] = ["dev-judge-token"]
    problem_data_dir: str = "./data/problems"  # local 后端的测试数据根目录（pytest 用）

    # AI 助手网关（gRPC，独立进程节点；Anthropic key 只存节点侧，这里不配）
    assistant_grpc_port: int = 50060  # 50052 与本机 IncrediBuild LicenseService 冲突，改用 50060
    assistant_node_tokens: list[str] = ["dev-assistant-token"]
    assistant_model: str = "claude-sonnet-5"
    assistant_daily_quota: int = 100          # 每用户每日对话轮数上限
    assistant_run_sample_quota: int = 20      # run_on_sample 每日次数上限

    # JWT
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # 判题
    max_code_size_kb: int = 100
    default_time_limit_ms: int = 2000
    default_memory_limit_mb: int = 256


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
