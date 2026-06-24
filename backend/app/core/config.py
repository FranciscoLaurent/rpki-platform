"""应用配置管理，基于 pydantic-settings 从环境变量读取。"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置项。

    所有配置项均可通过环境变量覆盖，环境变量名不区分大小写。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用基础配置
    APP_NAME: str = "RPKI 网络安全管理平台"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # 数据库配置（生产环境必须通过环境变量设置）
    DATABASE_URL: str = "postgresql+asyncpg://rpki:rpki@localhost:5432/rpki_platform"

    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"

    # Kafka 配置
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # ClickHouse 配置
    CLICKHOUSE_URL: str = "http://localhost:8123"
    CLICKHOUSE_DATABASE: str = "rpki_platform"
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""

    # 安全配置
    # WARNING: SECRET_KEY 必须通过环境变量设置，此默认值仅供本地开发，生产环境务必覆盖
    SECRET_KEY: str = "dev-secret-key-change-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 默认 1 天
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 刷新令牌有效期（天）

    # 登录安全配置
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5  # 最大连续登录失败次数
    ACCOUNT_LOCK_DURATION_MINUTES: int = 15  # 账户锁定时长（分钟）

    # TLS/mTLS 配置
    TLS_ENABLED: bool = False
    TLS_CERT_FILE: str | None = None
    TLS_KEY_FILE: str | None = None
    TLS_CERT_PATH: str | None = None  # 兼容别名：TLS 证书路径
    TLS_KEY_PATH: str | None = None  # 兼容别名：TLS 私钥路径
    TLS_CA_PATH: str | None = None  # CA 证书路径（用于 mTLS 客户端证书校验）
    TLS_MIN_VERSION: str = "TLSv1.2"  # TLS 最低版本：TLSv1.2 / TLSv1.3
    MTLS_ENABLED: bool = False
    MTLS_CA_FILE: str | None = None
    MTLS_CA_PATH: str | None = None  # 兼容别名：mTLS CA 证书路径
    MTLS_CLIENT_CERT_REQUIRED: bool = False  # 是否强制要求客户端证书

    # IP 白名单（空列表表示不限制）
    IP_WHITELIST: list[str] = []
    IP_WHITELIST_ENABLED: bool = False  # 是否启用 IP 白名单（显式开关）
    IP_WHITELIST_PATHS: list[str] = []  # 仅对指定路径前缀启用白名单（为空则全部生效）

    # 密钥轮换配置
    SECRET_KEY_ROTATION_INTERVAL_DAYS: int = 90  # JWT 密钥轮换间隔（天）
    PREVIOUS_SECRET_KEYS: list[str] = []  # 旧密钥列表，用于平滑过渡
    KEY_ROTATION_INTERVAL_DAYS: int = 90  # 数据加密密钥轮换间隔（天）

    # 敏感数据加密密钥（Fernet 密钥，留空则按 SECRET_KEY 派生）
    ENCRYPTION_KEY: str | None = None
    # 字段级加密专用密钥（Fernet 密钥，留空则复用 ENCRYPTION_KEY/SECRET_KEY 派生）
    FIELD_ENCRYPTION_KEY: str | None = None

    # 异常登录检测配置
    ANOMALOUS_LOGIN_OFFICE_HOURS_START: int = 8  # 工作时间起始小时
    ANOMALOUS_LOGIN_OFFICE_HOURS_END: int = 18  # 工作时间结束小时
    ANOMALOUS_LOGIN_NEW_GEO_THRESHOLD: int = 0  # 新地理位置阈值（0 表示始终检测）

    # 注册配置
    OPEN_REGISTRATION: bool = False  # 是否开放注册

    # 初始超级管理员配置（生产环境必须通过环境变量设置密码）
    DEFAULT_ADMIN_USERNAME: str = "admin"
    # WARNING: 必须通过环境变量 DEFAULT_ADMIN_PASSWORD 设置，此默认值仅供本地开发
    DEFAULT_ADMIN_PASSWORD: str = "change-me-in-production"
    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"

    # CORS 配置
    CORS_ORIGINS: list[str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """支持以逗号分隔的字符串形式配置 CORS 来源。"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        return ["*"]

    @field_validator("IP_WHITELIST", mode="before")
    @classmethod
    def parse_ip_whitelist(cls, v: object) -> list[str]:
        """支持以逗号分隔的字符串形式配置 IP 白名单。"""
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator("IP_WHITELIST_PATHS", mode="before")
    @classmethod
    def parse_ip_whitelist_paths(cls, v: object) -> list[str]:
        """支持以逗号分隔的字符串形式配置 IP 白名单生效路径。"""
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return v
        return []

    @field_validator("PREVIOUS_SECRET_KEYS", mode="before")
    @classmethod
    def parse_previous_secret_keys(cls, v: object) -> list[str]:
        """支持以逗号分隔的字符串形式配置旧密钥列表。"""
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        if isinstance(v, list):
            return v
        return []


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（带缓存）。"""
    return Settings()


# 全局配置实例
settings = get_settings()
