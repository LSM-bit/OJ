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

    # 判题网关（gRPC，独立于 HTTP 端口）
    judge_grpc_port: int = 50051
    judge_gateway_tokens: list[str] = ["dev-judge-token"]
    problem_data_dir: str = "./data/problems"  # 测试数据根目录（生产换对象存储）

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
