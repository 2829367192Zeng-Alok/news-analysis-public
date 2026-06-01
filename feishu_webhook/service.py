# -*- coding: utf-8 -*-
"""分析完成后通过飞书群机器人 Webhook 推送。"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List

from config import settings
from feishu_webhook.webhook_client import send_text_message
from pipeline_notify_format import format_analysis_message

if TYPE_CHECKING:
    from models import NewsAnalysisDetail

logger = logging.getLogger(__name__)


def push_analysis_details(details: List[NewsAnalysisDetail]) -> None:
    """
    将本轮新增的 analysis 详情推送到配置的飞书 Webhook（可多群多 URL）。
    失败仅打日志，不向外抛异常。
    """
    cfg = settings.feishu_webhook
    if not cfg.enabled:
        logger.debug("飞书 Webhook 未启用（FEISHU_WEBHOOK_ENABLED）")
        return
    if not details:
        return
    if not cfg.webhook_urls:
        logger.warning("飞书 Webhook 已启用但未配置 FEISHU_WEBHOOK_URL，跳过")
        return

    for detail in details:
        text = format_analysis_message(
            detail,
            web_base_url=cfg.web_base_url,
            conclusion_max_len=cfg.conclusion_max_len,
        )
        for hook_url in cfg.webhook_urls:
            try:
                send_text_message(webhook_url=hook_url, text=text)
                logger.info(
                    "飞书推送成功 detail_id=%s title=%s",
                    getattr(detail, "id", None),
                    (detail.title or "")[:80],
                )
            except Exception as e:
                logger.warning(
                    "飞书推送失败 detail_id=%s: %s",
                    getattr(detail, "id", None),
                    e,
                )
            delay = max(0, cfg.send_delay_ms) / 1000.0
            if delay:
                time.sleep(delay)
