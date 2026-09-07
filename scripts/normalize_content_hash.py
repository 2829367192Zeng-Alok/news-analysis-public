#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
content_hash 数据归一脚本。

背景：历史上 utils.compute_content_hash 为 MD5（32 hex，"::" 分隔），news_fetcher 内部为
blake2b（64 hex，"\\n" 分隔），二者已被统一为 blake2b（见 utils.py）。本脚本把库内仍以
旧 MD5 写入的行重算为 blake2b，并在可选 --dedupe 模式下合并重算后出现的重复 raw_news
（保留最小 id，把 selected_news / news_analysis_detail 的引用改指保留行）。

用法（务必先 dry-run）：
  python scripts/normalize_content_hash.py --dry-run
  python scripts/normalize_content_hash.py --update
  python scripts/normalize_content_hash.py --update --dedupe

回滚：--update 前请备份受影响表（raw_news / selected_news / news_analysis_detail）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from models import (
    NewsAnalysisDetail,
    RawNews,
    SelectedNews,
    get_db_session,
)
from utils import compute_content_hash, compute_content_hash_legacy_md5

TABLES = ("raw_news", "selected_news", "news_analysis_detail")


def _is_legacy_md5(value: str) -> bool:
    """MD5 是 32 位 hex；blake2b 是 64 位 hex。非 64 位一律视为旧值。"""
    return value is not None and len(value) == 32


def _fetch_pairs(session, model) -> List[Tuple[int, str, str, str]]:
    rows = session.execute(select(model.id, model.title, model.content, model.content_hash)).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def _recompute(pairs) -> Tuple[List[Tuple[int, str, str]], int]:
    """返回 [(id, old_hash, new_hash)] 与受影响（值会变化）的行数。"""
    updates: List[Tuple[int, str, str]] = []
    affected = 0
    for pid, title, content, old_hash in pairs:
        new_hash = compute_content_hash(title, content)
        if old_hash != new_hash:
            updates.append((pid, old_hash, new_hash))
            affected += 1
    return updates, affected


def _apply_updates(session, model, updates) -> None:
    from sqlalchemy import update as sa_update

    for pid, _old, new_hash in updates:
        session.execute(sa_update(model).where(model.id == pid).values(content_hash=new_hash))
    if updates:
        session.commit()
        print(f"  已更新 {len(updates)} 行 {model.__tablename__}")


def _dedupe_table(session, model) -> int:
    """
    表内按 content_hash 去重（保留最小 id）。三表之间仅以 content_hash 关联、
    无外键，因此逐表独立去重是安全的；删除冗余行不会破坏其他表的引用完整性。
    """
    from sqlalchemy import delete as sa_delete

    rows = session.execute(
        select(model.id, model.content_hash).order_by(model.id.asc())
    ).all()
    seen: Dict[str, int] = {}
    drop_ids: List[int] = []
    for pid, h in rows:
        if h in seen:
            drop_ids.append(pid)
        else:
            seen[h] = pid

    if not drop_ids:
        print(f"  {model.__tablename__}: 无重复，跳过")
        return 0

    for pid in drop_ids:
        session.execute(sa_delete(model).where(model.id == pid))
    session.commit()
    print(f"  {model.__tablename__}: 已删除 {len(drop_ids)} 条重复行（保留最小 id）")
    return len(drop_ids)


def _dedupe_all(session) -> None:
    """重算后三表各自可能产生同 hash 重复行（同一新闻两条不同旧 hash 造成），逐表去重。"""
    total = 0
    for model in (RawNews, SelectedNews, NewsAnalysisDetail):
        total += _dedupe_table(session, model)
    print(f"  去重合计: {total} 行")


def main() -> None:
    parser = argparse.ArgumentParser(description="content_hash 归一为 blake2b（可先去重）")
    parser.add_argument("--dry-run", action="store_true", help="只报告受影响行数，不写库")
    parser.add_argument("--update", action="store_true", help="执行重算（--update 与 --dry-run 互斥）")
    parser.add_argument("--dedupe", action="store_true", help="重算后合并重复 raw_news（仅与 --update 连用）")
    args = parser.parse_args()

    if args.dry_run and args.update:
        raise SystemExit("--dry-run 与 --update 不能同时使用")

    session = get_db_session()
    try:
        print("== 扫描 content_hash 现状 ==")
        legacy_total = 0
        for model in (RawNews, SelectedNews, NewsAnalysisDetail):
            pairs = _fetch_pairs(session, model)
            legacy = sum(1 for *_ , h in pairs if _is_legacy_md5(h))
            updates, affected = _recompute(pairs)
            print(
                f"{model.__tablename__}: 共 {len(pairs)} 行, 32位旧hash {legacy} 行, "
                f"重算后变化 {affected} 行"
            )
            legacy_total += legacy

        if legacy_total == 0:
            print("未发现旧 MD5 行（32 位 hash），无需归一。")
            return

        if args.dry_run:
            print("dry-run 结束：以上为将受影响的行数，未写库。")
            return

        if not args.update:
            print("未指定 --update，仅做扫描（加 --update 执行，--dedupe 可选）。")
            return

        print("== 执行归一 ==")
        for model in (RawNews, SelectedNews, NewsAnalysisDetail):
            pairs = _fetch_pairs(session, model)
            updates, _ = _recompute(pairs)
            _apply_updates(session, model, updates)

        if args.dedupe:
            print("== 去重三表重复 content_hash ==")
            _dedupe_all(session)
        print("完成")
    finally:
        session.close()


if __name__ == "__main__":
    main()
