# -*- coding: utf-8 -*-
"""
系统健康告警服务：当流水线各阶段长时间无新增数据时，通过飞书机器人发送告警。

使用方式（在流水线主循环中调用）：
    from feishu_webhook.alert_service import PipelineHealthChecker
    checker = PipelineHealthChecker()
    checker.check_and_alert()   # 每轮流水线结束后调用

告警触发条件（阈值均可通过环境变量调整）：
    - ALERT_RAW_STALE_MINUTES    : raw_news 无新增超过 N 分钟（默认 30）
    - ALERT_ANALYZE_STALE_MINUTES: news_analysis_detail 无新增超过 N 分钟（默认 60）

抑制机制：
    - 同一告警类型在 ALERT_SUPPRESS_MINUTES（默认 60）分钟内不重复发送。
    - 故障恢复后会发送一条"恢复正常"通知（每类只发一次）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from config import settings
from feishu_webhook.webhook_client import send_text_message
from utils import now_beijing_naive

logger = logging.getLogger(__name__)

# ---------- 告警阈值（分钟） ----------
_RAW_STALE_MIN = int(os.getenv("ALERT_RAW_STALE_MINUTES", "30"))
_ANALYZE_STALE_MIN = int(os.getenv("ALERT_ANALYZE_STALE_MINUTES", "60"))
_SUPPRESS_MIN = int(os.getenv("ALERT_SUPPRESS_MINUTES", "60"))


def _send_alert(text: str) -> None:
    """向所有配置的飞书 Webhook 发送告警消息。失败仅记日志。"""
    cfg = settings.feishu_webhook
    if not cfg.enabled or not cfg.webhook_urls:
        logger.debug("飞书告警跳过：Webhook 未启用或未配置")
        return
    for url in cfg.webhook_urls:
        try:
            send_text_message(webhook_url=url, text=text)
            logger.info("飞书告警发送成功")
        except Exception as e:
            logger.warning("飞书告警发送失败: %s", e)


class PipelineHealthChecker:
    """
    流水线健康检查器。在流水线进程的生命周期内复用同一实例，
    以利用内存状态做告警抑制。
    """

    def __init__(self) -> None:
        # last_alert_time[alert_key] = 上次发送告警的时间
        self._last_alert: Dict[str, datetime] = {}
        # 记录上次已知的"最新 create_time"，用于判断是否有新数据写入
        self._last_known: Dict[str, Optional[datetime]] = {
            "raw": None,
            "analyze": None,
        }
        # 告警是否正在触发中（用于发送"恢复"通知）
        self._alerting: Dict[str, bool] = {
            "raw": False,
            "analyze": False,
        }

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def check_and_alert(self) -> None:
        """
        查询数据库中各层最新写入时间，判断是否需要发送告警或恢复通知。
        应在每轮流水线结束后调用（即使流水线因无新闻而提前退出）。
        """
        try:
            self._check_layer(
                layer_key="raw",
                stale_minutes=_RAW_STALE_MIN,
                alert_title="【告警】采集层停止",
                recover_title="【恢复】采集层已恢复",
                alert_body_fn=self._raw_alert_body,
            )
        except Exception:
            logger.exception("采集层健康检查异常")

        try:
            self._check_layer(
                layer_key="analyze",
                stale_minutes=_ANALYZE_STALE_MIN,
                alert_title="【告警】分析层停止",
                recover_title="【恢复】分析层已恢复",
                alert_body_fn=self._analyze_alert_body,
            )
        except Exception:
            logger.exception("分析层健康检查异常")

    def notify_api_error(self, step: str, error_type: str, detail: str) -> None:
        """
        流水线步骤遇到需要人工介入的 API 错误时主动告警（如 404 接口不可用）。
        同类错误在抑制窗口内只发一次。

        :param step:       步骤名，如 "步骤2筛选" / "步骤3分析"
        :param error_type: 错误类型标签，如 "404" / "403"
        :param detail:     错误详情（截断到 200 字符）
        """
        key = f"api_error:{step}:{error_type}"
        if self._is_suppressed(key):
            return
        now = now_beijing_naive()
        text = (
            f"【API告警】{step} 出现 {error_type} 错误，需人工检查\n"
            f"时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"详情：{detail[:200]}\n"
            f"可能原因：API Key 失效 / 模型 ID 变更 / 接口路径变更\n"
            f"请检查豆包控制台并更新 .env 配置。"
        )
        _send_alert(text)
        self._last_alert[key] = now
        logger.warning("已发送 API 错误告警: step=%s type=%s", step, error_type)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _check_layer(
        self,
        layer_key: str,
        stale_minutes: int,
        alert_title: str,
        recover_title: str,
        alert_body_fn,
    ) -> None:
        latest_time = self._query_latest_time(layer_key)
        now = now_beijing_naive()
        threshold = now - timedelta(minutes=stale_minutes)

        is_stale = (latest_time is None) or (latest_time < threshold)

        if is_stale:
            if not self._is_suppressed(layer_key):
                if latest_time is not None:
                    self._last_known[layer_key] = latest_time
                text = alert_body_fn(
                    title=alert_title,
                    latest_time=self._last_known.get(layer_key),
                    stale_minutes=stale_minutes,
                    now=now,
                )
                _send_alert(text)
                self._last_alert[layer_key] = now
                self._alerting[layer_key] = True
                logger.warning("已发送告警: %s (latest=%s)", layer_key, latest_time)
        else:
            self._last_known[layer_key] = latest_time
            if self._alerting.get(layer_key):
                text = (
                    f"{recover_title}\n"
                    f"时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"最新数据写入：{latest_time.strftime('%Y-%m-%d %H:%M:%S') if latest_time else '未知'}"
                )
                _send_alert(text)
                self._alerting[layer_key] = False
                self._last_alert.pop(layer_key, None)
                logger.info("已发送恢复通知: %s", layer_key)

    def _is_suppressed(self, key: str) -> bool:
        """判断该告警 key 是否在抑制窗口内。"""
        last = self._last_alert.get(key)
        if last is None:
            return False
        return (now_beijing_naive() - last) < timedelta(minutes=_SUPPRESS_MIN)

    @staticmethod
    def _query_latest_time(layer_key: str) -> Optional[datetime]:
        """查询各层最新 create_time，失败返回 None。"""
        try:
            from sqlalchemy import select, func
            from models import get_db_session, RawNews, NewsAnalysisDetail
            session = get_db_session()
            try:
                if layer_key == "raw":
                    col = RawNews.create_time
                else:
                    col = NewsAnalysisDetail.create_time
                result = session.scalar(select(func.max(col)))
                return result
            finally:
                session.close()
        except Exception as e:
            logger.warning("查询 %s 最新时间失败: %s", layer_key, e)
            return None

    @staticmethod
    def _raw_alert_body(
        title: str,
        latest_time: Optional[datetime],
        stale_minutes: int,
        now: datetime,
    ) -> str:
        last_str = (
            latest_time.strftime("%Y-%m-%d %H:%M:%S") if latest_time else "从未写入"
        )
        stale_duration = ""
        if latest_time:
            delta = now - latest_time
            stale_duration = f"（已停止约 {int(delta.total_seconds() // 60)} 分钟）"
        return (
            f"{title}{stale_duration}\n"
            f"时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"最后采集：{last_str}\n"
            f"阈值：超过 {stale_minutes} 分钟无新数据触发\n"
            f"可能原因：Tushare Token 失效 / 网络中断 / 进程崩溃\n"
            f"请登录 ECS 检查进程状态：systemctl status financial-news 或查看 logs/"
        )

    @staticmethod
    def _analyze_alert_body(
        title: str,
        latest_time: Optional[datetime],
        stale_minutes: int,
        now: datetime,
    ) -> str:
        last_str = (
            latest_time.strftime("%Y-%m-%d %H:%M:%S") if latest_time else "从未写入"
        )
        stale_duration = ""
        if latest_time:
            delta = now - latest_time
            stale_duration = f"（已停止约 {int(delta.total_seconds() // 60)} 分钟）"
        return (
            f"{title}{stale_duration}\n"
            f"时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"最后分析写入：{last_str}\n"
            f"阈值：超过 {stale_minutes} 分钟无新数据触发\n"
            f"可能原因：豆包 API 限流(429) / 接口变更(404) / API Key 失效\n"
            f"请检查 logs/ 中最新报错，并前往豆包控制台确认账户状态。"
        )
