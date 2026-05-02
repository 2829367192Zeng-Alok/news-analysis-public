# 临时脚本：用 2 条未筛选的 raw_news 测试 news_filter 是否跑通
from news_filter import filter_news

if __name__ == "__main__":
    items = filter_news(limit=2)
    print("完成，新增 selected_news:", len(items))
