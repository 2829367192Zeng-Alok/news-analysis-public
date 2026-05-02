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
    Reference = Column(JSON)

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
    return SessionLocal()

