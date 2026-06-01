from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base

from config import settings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session

from utils import now_beijing_naive


# TODO: Reference 字段为历史遗留命名（首字母大写），后续若要统一命名需设计兼容迁移方案
Base = declarative_base()


class RawNews(Base):
    __tablename__ = "raw_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    news_datetime = Column(DateTime, nullable=False)
    source = Column(String(64), nullable=False)
    create_time = Column(
        DateTime, nullable=False,
        default=now_beijing_naive,
    )
    content_hash = Column(String(64), nullable=False, index=True)
    relevance = Column(Boolean, nullable=True, default=None, comment="参数_相关性（1=相关，0=不相关）")

    __table_args__ = (Index("idx_raw_content_hash", "content_hash"),)


class SelectedNews(Base):
    __tablename__ = "selected_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    news_datetime = Column(DateTime, nullable=False)
    source = Column(String(64), nullable=False)
    create_time = Column(
        DateTime, nullable=False,
        default=now_beijing_naive,
    )

    relevance = Column(Boolean, nullable=False, default=False)
    direction = Column(Integer)  # 短期影响方向
    impact = Column(Integer)  # 短期影响程度

    content_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (Index("idx_selected_content_hash", "content_hash"),)


class NewsAnalysisDetail(Base):
    __tablename__ = "news_analysis_detail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    news_datetime = Column(DateTime, nullable=False)
    source = Column(String(64), nullable=False)
    create_time = Column(
        DateTime, nullable=False,
        default=now_beijing_naive,
    )

    relevance = Column(Boolean, nullable=False, default=False)
    direction = Column(Integer)
    impact = Column(Integer)
    interest_direction = Column(Integer)
    interest_impact = Column(Integer)
    dollar_direction = Column(Integer)
    dollar_impact = Column(Integer)
    warrisk_direction = Column(Integer)
    warrisk_impact = Column(Integer)
    liquidity_direction = Column(Integer)
    liquidity_impact = Column(Integer)
    emotion_direction = Column(Integer)
    emotion_impact = Column(Integer)

    # 关键词和参考内容，使用 JSON 存储 array
    keyword = Column(JSON)
    # TODO: 历史遗留首字母大写命名，数据库列名保持不变，勿擅自迁移
    Reference = Column(JSON, comment="参考内容列表（历史遗留字段名，勿改列名）")

    interest = Column(Text)
    dollar = Column(Text)
    warrisk = Column(Text)
    liquidity = Column(Text)
    emotion = Column(Text)

    shorttime = Column(Text)
    midtime = Column(Text)
    longtime = Column(Text)
    insight = Column(Text)
    conclusion = Column(Text)

    content_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (Index("idx_detail_content_hash", "content_hash"),)


engine = create_engine(settings.db.sqlalchemy_url, pool_pre_ping=True, pool_recycle=3600)


@event.listens_for(engine, "connect")
def _set_mysql_timezone(dbapi_conn, connection_record):
    """仅在 MySQL 连接上设置会话时区为北京时间（+08:00）。"""
    if dbapi_conn is None:
        return
    if engine.dialect.name != "mysql":
        return
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET SESSION time_zone = '+08:00'")
        cursor.close()
    except Exception:
        pass  # 非 MySQL 或权限不足时忽略


SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))


def get_db_session():
    """
    返回当前线程绑定的 scoped_session 实例。
    使用完毕后请调用 remove_db_session() 归还连接，
    或直接使用 contextmanager 版（见 app.py 的 _db_session）。
    """
    return SessionLocal()


def remove_db_session() -> None:
    """
    释放当前线程的 scoped_session，归还连接池。
    应在每个请求结束或后台任务完成后调用。
    Flask 应用中可在 teardown_appcontext 中注册：
        @app.teardown_appcontext
        def shutdown_session(exc=None):
            remove_db_session()
    """
    SessionLocal.remove()

