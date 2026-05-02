# -*- coding: utf-8 -*-
"""
配置从环境变量读取；若存在默认配置文件会优先加载。
默认加载顺序：当前目录 .env → 用户目录 .financial_news_analysis.env
ECS 部署时请将 DB_HOST 设为云数据库内网地址（同地域/VPC 内连接更快且免公网流量）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy.engine import URL


def _load_default_env_files() -> None:
    """从默认路径加载 .env，避免在代码中写死密钥。先加载用户目录，再加载项目目录（后者覆盖）。"""
    try:
        import dotenv  # type: ignore
    except ImportError:
        return
    for path in (
        Path.home() / ".financial_news_analysis.env",
        Path.cwd() / ".env",
    ):
        if path.exists():
            dotenv.load_dotenv(path, override=True)


_load_default_env_files()


@dataclass
class DatabaseConfig:
    """数据库配置。默认兼容 MySQL，可通过 DB_DIALECT 切换至 PostgreSQL。"""
    dialect: str = os.getenv("DB_DIALECT", "mysql").strip().lower()
    # 可直接覆盖完整 SQLAlchemy URL（最高优先级）
    database_url: str = os.getenv("DATABASE_URL", "").strip()

    # 兼容旧 MySQL 变量（DB_*）以及显式 MYSQL_* 变量
    mysql_host: str = os.getenv("MYSQL_HOST", os.getenv("DB_HOST", "127.0.0.1"))
    mysql_port: int = int(os.getenv("MYSQL_PORT", os.getenv("DB_PORT", "3306")))
    mysql_user: str = os.getenv("MYSQL_USER", os.getenv("DB_USER", "root"))
    mysql_password: str = os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD", ""))
    mysql_name: str = os.getenv("MYSQL_DB_NAME", os.getenv("DB_NAME", "news_analysis"))
    mysql_driver: str = os.getenv("MYSQL_DRIVER", "pymysql")

    # PostgreSQL 变量
    postgres_host: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_name: str = os.getenv("POSTGRES_DB_NAME", "news_analysis")
    postgres_driver: str = os.getenv("POSTGRES_DRIVER", "psycopg")
    postgres_sslmode: str = os.getenv("POSTGRES_SSLMODE", "").strip()

    @property
    def mysql_sqlalchemy_url(self) -> str:
        return URL.create(
            drivername=f"mysql+{self.mysql_driver}",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    @property
    def postgres_sqlalchemy_url(self) -> str:
        query = {}
        if self.postgres_sslmode:
            query["sslmode"] = self.postgres_sslmode
        return URL.create(
            drivername=f"postgresql+{self.postgres_driver}",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_name,
            query=query,
        ).render_as_string(hide_password=False)

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.dialect in ("postgres", "postgresql"):
            return self.postgres_sqlalchemy_url
        return self.mysql_sqlalchemy_url


@dataclass
class TushareConfig:
    token: str = os.getenv("TUSHARE_TOKEN", "")


@dataclass
class DoubaoConfig:
    """豆包（火山引擎 Ark）Responses API 配置。"""
    api_key: str = os.getenv("DOUBAO_API_KEY", "")
    api_base_url: str = os.getenv(
        "DOUBAO_API_BASE_URL",
        "https://ark.cn-beijing.volces.com",
    )
    # 默认模型（未单独配置筛选/分析时使用）
    model_id: str = os.getenv(
        "DOUBAO_MODEL_ID",
        "doubao-seed-2-0-lite-260215",
    )
    # 筛选阶段使用的模型；不设或空则用 model_id
    model_id_filter: str = os.getenv("DOUBAO_MODEL_ID_FILTER", "")
    # 详细分析阶段使用的模型；不设或空则用 model_id
    model_id_analyze: str = os.getenv("DOUBAO_MODEL_ID_ANALYZE", "")


class Settings:
    db = DatabaseConfig()
    tushare = TushareConfig()
    doubao = DoubaoConfig()


settings = Settings()
