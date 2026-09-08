# db_migrations — 数据库变更目录

本目录登记所有需要**在已有数据库上执行的 SQL/数据迁移**。纯代码初始化（`init_db.py` 幂等补列）之外的变更统一走这里，保证生产变更可追溯、可回滚。

## 约定

```
db_migrations/
└── YYYYMMDD_<snake_case_用途>/
    ├── up.sql        # 正向迁移（幂等优先）
    ├── down.sql      # 回滚脚本（可选）
    └── README.md     # 影响面、执行环境、验证与回滚说明
```

- 目录名用日期前缀 + 用途，如 `20260907_normalize_content_hash/`。
- `up.sql` 尽量幂等（`ADD COLUMN IF NOT EXISTS` / 先查后建）。
- 每个迁移在 `docs/project_context_index.md` §5 技术债清单或对应专项文档中登记一条记录。
- 执行前必须备份或至少导出受影响表；执行后跑 `init_db.py` 复核一致性。

## 当前登记

| 日期 | 目录 | 内容 | 状态 |
|---|---|---|---|
| 2026-09-07 | `scripts/normalize_content_hash.py` | content_hash 统一 blake2b 的数据归一（先 `--dry-run` 后 `--update`，可选 `--dedupe`） | 脚本就绪，**生产未执行** |
| 2026-09-07 | `init_db.py`（代码内置，非 SQL 目录） | ① 清理 `ix_*` 冗余索引；② best-effort 创建 `uq_raw_content_hash` 唯一索引；③ v2 补 `confidence`/`uncertain` 两列 | 代码就绪，**生产 pull 后需跑一次 init_db** |

> 注：`normalize_content_hash.py` 以脚本形式提供（涉及跨表级联与去重），故未拆成纯 SQL；其他纯结构变更按上方目录约定落盘。执行顺序与回滚见 `docs/production_update_ops_2026-09-07.md` §2。
