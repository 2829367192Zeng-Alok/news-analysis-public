# -*- coding: utf-8 -*-
"""分析完成后触发的 QQ 群推送。"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, List

from config import settings

from pipeline_notify_format import format_analysis_message
from qq_push.onebot_http import send_group_msg

if TYPE_CHECKING:
    from models import NewsAnalysisDetail

logger = logging.getLogger(__name__)


def push_analysis_details(details: List[NewsAnalysisDetail]) -> None:
    """
    将本轮新增的 analysis 详情推送到配置的 QQ 群。
    失败仅打日志，不向外抛异常（由调用方决定是否捕获）。
    """
    cfg = settings.qq_push
    if not cfg.enabled:
        logger.debug("QQ 推送未启用（QQ_PUSH_ENABLED）")
        return
    if not details:
        return
    if not cfg.group_ids:
        logger.warning("QQ 推送已启用但未配置 QQ_GROUP_IDS，跳过")
        return

    for detail in details:
        text = format_analysis_message(
            detail,
            web_base_url=cfg.web_base_url,
            conclusion_max_len=cfg.conclusion_max_len,
        )
        for gid in cfg.group_ids:
            try:
                send_group_msg(
                    api_root=cfg.onebot_http_base,
                    group_id=int(gid),
                    message=text,
                    access_token=cfg.access_token,
                )
                logger.info(
                    "QQ 推送成功 group_id=%s detail_id=%s title=%s",
                    gid,
                    getattr(detail, "id", None),
                    (detail.title or "")[:80],
                )
            except Exception as e:
                logger.warning(
                    "QQ 推送失败 group_id=%s detail_id=%s: %s",
                    gid,
                    getattr(detail, "id", None),
                    e,
                )
            delay = max(0, cfg.send_delay_ms) / 1000.0
            if delay:
                time.sleep(delay)
