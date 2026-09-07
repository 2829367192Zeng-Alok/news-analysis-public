# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import os
from typing import Generator, List, Dict, Any, Optional

from flask import Flask, jsonify, request, render_template

from models import NewsAnalysisDetail, get_db_session


@contextmanager
def _db_session() -> Generator:
    """在 with 块内自动关闭 Session，异常时 rollback。"""
    session = get_db_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """将 ISO 格式字符串解析为 datetime，失败返回 None。"""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    # 兼容 JS toISOString()（带 Z）与毫秒精度
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def create_app() -> Flask:
    app = Flask(__name__)
    from models import remove_db_session

    @app.teardown_appcontext
    def _shutdown_session(exc=None):
        """每个请求结束后释放 scoped_session，归还连接池。"""
        remove_db_session()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/news")
    def api_news():
        """
        查询分析结果列表。

        Query params:
          limit  : 返回条数，默认 50，最大 200
          before : ISO 时间字符串，只返回 news_datetime < before 的记录（向前翻页）
          after  : ISO 时间字符串，只返回 news_datetime > after 的记录
        """
        from sqlalchemy import select

        try:
            limit = min(int(request.args.get("limit", 50)), 200)
        except (ValueError, TypeError):
            limit = 50

        before_dt = _parse_dt(request.args.get("before"))
        after_dt = _parse_dt(request.args.get("after"))

        with _db_session() as session:
            q = (
                select(NewsAnalysisDetail)
                .order_by(NewsAnalysisDetail.news_datetime.desc())
                .limit(limit)
            )
            if before_dt:
                q = q.where(NewsAnalysisDetail.news_datetime < before_dt)
            if after_dt:
                q = q.where(NewsAnalysisDetail.news_datetime > after_dt)

            items: List[NewsAnalysisDetail] = [row[0] for row in session.execute(q).all()]
            data: List[Dict[str, Any]] = []
            for n in items:
                data.append(
                    {
                        "id": n.id,
                        "title": n.title,
                        "source": n.source,
                        "news_datetime": n.news_datetime.isoformat()
                        if isinstance(n.news_datetime, datetime)
                        else None,
                        "relevance": bool(n.relevance),
                        "direction": n.direction,
                        "impact": n.impact,
                        "shorttime": n.shorttime,
                        "midtime": n.midtime,
                        "longtime": n.longtime,
                        "insight": n.insight,
                        "conclusion": n.conclusion,
                    }
                )
            return jsonify({"items": data, "count": len(data)})

    @app.route("/api/news/<int:news_id>")
    def api_news_detail(news_id: int):
        with _db_session() as session:
            item = session.get(NewsAnalysisDetail, news_id)
            if not item:
                return jsonify({"error": "not_found"}), 404

            data = {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "news_datetime": item.news_datetime.isoformat()
                if isinstance(item.news_datetime, datetime)
                else None,
                "relevance": bool(item.relevance),
                "direction": item.direction,
                "impact": item.impact,
                "interest_direction": item.interest_direction,
                "interest_impact": item.interest_impact,
                "dollar_direction": item.dollar_direction,
                "dollar_impact": item.dollar_impact,
                "warrisk_direction": item.warrisk_direction,
                "warrisk_impact": item.warrisk_impact,
                "liquidity_direction": item.liquidity_direction,
                "liquidity_impact": item.liquidity_impact,
                "emotion_direction": item.emotion_direction,
                "emotion_impact": item.emotion_impact,
                "keyword": item.keyword,
                "Reference": item.Reference,
                "interest": item.interest,
                "dollar": item.dollar,
                "warrisk": item.warrisk,
                "liquidity": item.liquidity,
                "emotion": item.emotion,
                "shorttime": item.shorttime,
                "midtime": item.midtime,
                "longtime": item.longtime,
                "insight": item.insight,
                "conclusion": item.conclusion,
            }
            return jsonify(data)

    @app.route("/api/stats")
    def api_stats():
        from sqlalchemy import select, func

        with _db_session() as session:
            total_news = session.scalar(select(func.count(NewsAnalysisDetail.id))) or 0
            latest_time = session.scalar(
                select(func.max(NewsAnalysisDetail.news_datetime))
            )
            return jsonify(
                {
                    "total_news": int(total_news),
                    "latest_news_time": latest_time.isoformat()
                    if isinstance(latest_time, datetime)
                    else None,
                }
            )

    return app


app = create_app()


if __name__ == "__main__":
    # 生产环境请用 gunicorn；debug 仅限本地开发显式开启（FLASK_DEBUG=1）
    debug = os.getenv("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=8000, debug=debug)

