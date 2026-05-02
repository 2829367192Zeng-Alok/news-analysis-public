from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, jsonify, render_template
from sqlalchemy import select, func

from models import NewsAnalysisDetail, get_db_session


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/news")
    def api_news():
        session = get_db_session()
        try:
            q = (
                select(NewsAnalysisDetail)
                .order_by(NewsAnalysisDetail.news_datetime.desc())
                .limit(100)
            )
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
            return jsonify({"items": data})
        finally:
            session.close()

    @app.route("/api/news/<int:news_id>")
    def api_news_detail(news_id: int):
        session = get_db_session()
        try:
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
        finally:
            session.close()

    @app.route("/api/stats")
    def api_stats():
        session = get_db_session()
        try:
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
        finally:
            session.close()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

