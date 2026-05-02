# -*- coding: utf-8 -*-
"""筛选与详细分析使用的豆包提示词（可按需替换为你的已准备提示词）。"""

# 筛选阶段：要求模型仅输出 JSON，包含 relevance, direction, impact
FILTER_PROMPT_TEMPLATE = """你是一个金融新闻筛选助手。请考虑美债实际利率、美元指数、地缘政治风险、资本市场流动性、市场情绪五个维度，快速判断下面这条新闻是否与黄金市场相关。
仅输出一个 JSON 对象，不要其他说明，格式如下：
{{"relevance": true或false, "direction": 0, "impact": 0}}

新闻标题：{title}

新闻正文：
{content}
"""

# 详细分析阶段：要求模型输出包含 32 个字段的 JSON（与 news_analysis_detail 表一致）
ANALYZE_PROMPT_TEMPLATE = """你是一个资深黄金宏观分析师。


请对下面这条新闻进行结构化分析，先
提取新闻可能影响黄金的关键信息，保留主体、动作、数据、结果作为关键词，
再
考虑美债实际利率、美元指数、地缘政治风险、资本市场流动性、市场情绪（避险/恐慌/看涨）五个传导路径，分别分析该新闻对市场的影响，并判断该影响程度为【低 中 高 极高】，给出一句话解释。
然后
结合五个传导路径的分析结果，综合判断出对黄金市场的短期/中期/长期影响，给出影响方向（利多/利空）及影响强度，并给出50字以内的简要分析。


最后根据分析结果输出一个 JSON 对象，包含以下字段（均为字符串，除非注明类型）：
- relevance: bool，是否与宏观/市场相关
- direction: int，短期影响方向（1/-1/0）（利多/利空/中性）
- impact: int，短期影响程度（1-5）（5 最强）
- interest_direction, interest_impact: int，实际利率维度的方向和程度
- dollar_direction, dollar_impact: int，美元指数方向和程度
- warrisk_direction, warrisk_impact: int，地缘政治风险方向和程度
- liquidity_direction, liquidity_impact: int，资本市场流动性方向和程度
- emotion_direction, emotion_impact: int，市场情绪方向和程度
- keyword: 字符串数组，关键词
- Reference: 字符串数组，参考内容（可空）
- interest, dollar, warrisk, liquidity, emotion: 字符串，各传导路径的分析说明
- shorttime, midtime, longtime: 字符串，短期/中期/长期结论
- insight: 字符串，投资启示
- conclusion: 字符串，核心结论

仅输出上述 JSON，不要 markdown 标记外的内容。

新闻标题：{title}

新闻正文：
{content}
"""
