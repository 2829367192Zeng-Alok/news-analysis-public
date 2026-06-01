# -*- coding: utf-8 -*-
"""加载人工维护的宏观基线（YAML/JSON），供 prompts_new 的 System Prompt 注入。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# 无任何配置文件时的占位（字段需与 SYSTEM_PROMPT_TEMPLATE 一致，避免 Key 缺失）
EMPTY_MACRO_BASELINE: Dict[str, Any] = {
    "baseline_date": "",
    "fed_stance": "",
    "real_rate_10y": "",
    "dxy": "",
    "gold_price": "",
    "sentiment_momentum": "",
    "geo_risk_level": "",
    "manual_context": "",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _load_baseline_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise ImportError(
                "读取 YAML 基线需要安装 PyYAML：pip install pyyaml"
            ) from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"宏观基线文件必须是对象/dict: {path}")
    return data


def load_macro_baseline(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    读取宏观基线。未指定 path 时依次尝试：
    config/macro_baseline.yaml → macro_baseline.yml → macro_baseline.json；
    若均不存在，再加载同目录下的 macro_baseline.example.yaml（便于本地开箱跑通）；
    最后回退 EMPTY_MACRO_BASELINE。
    """
    root = _project_root()
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.extend(
            [
                root / "config" / "macro_baseline.yaml",
                root / "config" / "macro_baseline.yml",
                root / "config" / "macro_baseline.json",
            ]
        )

    for p in candidates:
        if not p.exists():
            continue
        return _load_baseline_file(p)

    example = root / "config" / "macro_baseline.example.yaml"
    if example.exists():
        return _load_baseline_file(example)

    return dict(EMPTY_MACRO_BASELINE)
