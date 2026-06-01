# scripts/

本目录存放开发期调试脚本，**不参与生产部署**，已在 `.gitignore` 中排除跟踪。

| 文件 | 用途 |
|------|------|
| `debug_doubao.py` | 手动测试豆包 API 连通性与响应格式 |
| `debug_filter_response.py` | 检查筛选接口返回的原始 JSON |
| `debug_news_api.py` | 手动调用 Tushare 接口查看原始数据 |
| `test_api.py` | 测试 Flask API 端点 |
| `test_filter_once.py` | 对单条新闻跑一次筛选流程 |
| `test_tushare_news.py` | 验证 Tushare Token 与新闻接口 |
| `fix_crlf.py` | 修复 Windows CRLF 换行符 |

运行方式（在项目根目录）：
```bash
python scripts/debug_doubao.py
```
