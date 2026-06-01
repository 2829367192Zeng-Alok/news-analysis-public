# -*- coding: utf-8 -*-
"""
GoldSentinel Lite — 提示词模块 v2.0
包含：筛选阶段 / 宏观基线 System Prompt / 详细分析 User Prompt / 后端调用示例
"""
from __future__ import annotations

from typing import Any, Mapping


# ══════════════════════════════════════════════════════════════════
# 1. 筛选阶段提示词（独立调用，保守门控）
# ══════════════════════════════════════════════════════════════════

FILTER_PROMPT_TEMPLATE = """你是黄金市场新闻的相关性筛选器。你的首要原则是：宁可放行存疑新闻，绝不过滤可能相关的内容。

【判断标准】
若新闻涉及以下任一领域，relevance 输出 true：
- 美联储政策、利率决议、通胀数据（CPI/PCE/PPI）、实际利率走势
- 美元指数、美元流动性、美债收益率
- 地缘冲突、制裁、战争、核危机、大国博弈
- 全球央行购金、黄金ETF、黄金期货持仓
- 金融市场恐慌、避险情绪、系统性风险事件
- 主要经济体（美/欧/中）GDP、就业、PMI等宏观数据

【判定为 false 的情形】
仅当新闻明确属于以下类型时才输出 false：
- 纯娱乐、体育、社会新闻
- 单一企业微观经营动态（非金融机构）
- 与宏观经济、地缘政治完全无关的地方性事件

【输出规则】
- 仅输出一个 JSON 对象，无任何其他内容
- direction：对黄金的粗略方向（1利多 / -1利空 / 0不确定），若 relevance 为 false 则输出 0
- impact：粗略影响强度（1-5），若 relevance 为 false 则输出 0

{{"relevance": true或false, "direction": 0, "impact": 0}}

新闻标题：{title}
新闻正文：
{content}
"""


# ══════════════════════════════════════════════════════════════════
# 2. 宏观基线 System Prompt（每次调用前格式化注入）
# ══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_TEMPLATE = """你是一位资深黄金宏观分析师。你的所有分析必须锚定参考在以下【当前宏观基线】之上，而非依赖训练数据中的历史市场状态。

━━━ 当前宏观基线（{baseline_date} 更新）━━━

【客观市场数据】
- 美联储立场：{fed_stance}
- 10Y 实际利率（TIPS）：{real_rate_10y}%
- 美元指数 DXY：{dxy}
- 黄金现货价格：{gold_price} 美元/盎司
- 市场情绪动量：{sentiment_momentum}/100（0=强烈看空，100=强烈看多）
- 当前地缘风险等级：{geo_risk_level}（低/中/高/极高）

【人工研判层 — 政治状态与长链路分析】
{manual_context}

━━━ 基线使用原则 ━━━
1. 新闻的影响是在当前基线上的「边际变化」。例如：基线已是偏鹰派，若新闻暗示进一步鹰派，
   边际冲击有限；若新闻暗示转鸽，则边际冲击显著。
2. 人工研判层提供了复杂政治事件的长链路逻辑。当新闻触及相关议题时，
   必须优先采用该长链路逻辑，而非简单的线性推断（如「地缘风险→黄金上涨」）。
3. 若新闻信息与基线数据存在明显矛盾，须在 conclusion 字段中显式说明该矛盾。
"""


# ══════════════════════════════════════════════════════════════════
# 3. 详细分析 User Prompt
# ══════════════════════════════════════════════════════════════════

ANALYZE_PROMPT_TEMPLATE = """请对以下新闻进行结构化分析，严格按照步骤执行，最终输出一个 JSON 对象。

━━━ 步骤一：关键信息提取 ━━━
从新闻中提取主体、核心动作、关键数据、事件结果，形成 3-6 个关键词，存入 keyword 字段。

━━━ 步骤二：五路径传导分析 ━━━

对每条路径，先判断影响类型，再输出 direction、impact 和说明文字。

【影响类型判断 — 直接 vs 次生】
- 直接影响：新闻直接涉及该路径的核心变量
  示例：「美联储宣布加息」→ interest 路径为直接影响
- 次生传导：需经过 1 步以上间接推导才能触及该路径
  示例：「伊朗局势升级」→ 油价→通胀→实际利率 → interest 路径为次生传导
- 次生路径的 impact 须在直接判断值基础上 ×0.5 后取整（最低为 1）
  示例：直接判断为 4 → 次生后输出 2；直接判断为 3 → 次生后输出 1（取整向下）
- 在说明文字中标注「[次生]」字样，使分析可追溯

【高强度冲突检测】
- 若某两条路径方向完全相反（一为 1，另一为 -1），且双方 impact 均 ≥ 4，
  则判定为「高强度冲突」，uncertain 置为 true，confidence 每对冲突 -15

【五路径定义与判断规则】

① interest（美债实际利率）
   实际利率↑ → 持金机会成本↑ → 利空（direction=-1）
   实际利率↓ → 持金机会成本↓ → 利多（direction=1）
   不涉及 → direction=0，impact=0，说明填「不涉及」
   ⚠️ 结合基线实际利率水平判断边际变化的显著性；
      若经由通胀→利率的间接链路，标注 [次生]

② dollar（美元指数）
   美元↑ → 黄金以美元计价承压 → 利空（direction=-1）
   美元↓ → 黄金计价支撑 → 利多（direction=1）
   不涉及 → direction=0，impact=0，说明填「不涉及」
   ⚠️ 注意：避险情绪可同时推升美元和黄金，此时 dollar 与 emotion 方向可以一致

③ warrisk（地缘政治风险）
   冲突升级/制裁加码/危机爆发 → 避险需求↑ → 利多（direction=1）
   局势缓和/协议达成 → 避险需求↓ → 利空（direction=-1）
   不涉及 → direction=0，impact=0，说明填「不涉及」
   ⚠️ 若基线人工研判层对该地区有长链路分析，必须采用该逻辑；
      地缘事件若经由「油价→通胀→利率」链路影响 interest，该 interest 为次生传导

④ liquidity（资本市场流动性）
   流动性收紧/信用危机/美元荒 → 黄金遭流动性抛售 → 利空（direction=-1）
   流动性宽松/QE预期/降息预期 → 实物资产需求↑ → 利多（direction=1）
   不涉及 → direction=0，impact=0，说明填「不涉及」

⑤ emotion（市场情绪）
   恐慌/避险情绪升温 → 黄金避险买入↑ → 利多（direction=1）
   风险偏好回升/贪婪情绪主导 → 资金流出黄金 → 利空（direction=-1）
   不涉及 → direction=0，impact=0，说明填「不涉及」

━━━ 步骤三：综合判断 ━━━

【confidence 计算】
起点：85
- 每出现一对高强度冲突路径（双方 impact≥4 且方向相反）：-15
- 新闻信息模糊或缺乏具体数据：-10
- 基线人工研判层明确覆盖该议题，采用了长链路逻辑：+5
最终值限定在 0–100 范围内

【uncertain 规则】
- confidence 计算结果 < 60：uncertain = true
- 存在任意一对高强度冲突路径：uncertain = true（无论 confidence 值）
- 其余情况：uncertain = false

【direction 综合规则】
- 短期方向以 emotion 和 dollar 路径为主导权重
- 若存在高强度冲突路径，顶层 direction = 0
- 若无冲突，按各涉及路径（impact > 0）加权多数方向决定
- 综合 impact：取各涉及路径（impact > 0）的均值，四舍五入

【时效分层结论】（各 20 字以内）
- shorttime（1–5日）：情绪与美元主导，说明方向与核心驱动
- midtime（1–4周）：实际利率与流动性主导
- longtime（1–6月）：地缘与基本面主导，若基线有长链路逻辑须体现

【其他字段】（字数上限严格执行）
- insight：后续值得跟踪的关键信号或风险点，30 字以内
- conclusion：整体影响结论，40 字以内
  - 存在高强度冲突时：必须含「路径冲突」字样
  - uncertain=true 时：必须含「不确定」字样
  - 采用基线长链路逻辑时：简要体现链路结论而非简单线性描述

━━━ 输出要求 ━━━
仅输出以下 JSON，字段顺序固定，不含 markdown 标记，不含任何注释或额外文字：

{{
  "relevance": true,
  "direction": 0,
  "impact": 0,
  "confidence": 85,
  "uncertain": false,
  "interest_direction": 0, "interest_impact": 0,
  "dollar_direction": 0, "dollar_impact": 0,
  "warrisk_direction": 0, "warrisk_impact": 0,
  "liquidity_direction": 0, "liquidity_impact": 0,
  "emotion_direction": 0, "emotion_impact": 0,
  "keyword": [],
  "Reference": [],
  "interest": "",
  "dollar": "",
  "warrisk": "",
  "liquidity": "",
  "emotion": "",
  "shorttime": "",
  "midtime": "",
  "longtime": "",
  "insight": "",
  "conclusion": ""
}}

新闻标题：{title}
新闻正文：
{content}
"""


# ══════════════════════════════════════════════════════════════════
# 4. 宏观基线数据
# ══════════════════════════════════════════════════════════════════
# 人工维护的字段定义见 SYSTEM_PROMPT_TEMPLATE 占位符；数据文件请放在
# config/macro_baseline.yaml（可从 config/macro_baseline.example.yaml 复制），
# 由 macro_baseline.load_macro_baseline() 加载，再经 format_system_prompt() 注入。


def format_system_prompt(baseline: Mapping[str, Any]) -> str:
    """将人工维护的宏观基线字典格式化为 SYSTEM_PROMPT_TEMPLATE 所需文本。"""
    def _s(key: str, default: str = "") -> str:
        v = baseline.get(key, default)
        if v is None:
            return default
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v).strip()

    return SYSTEM_PROMPT_TEMPLATE.format(
        baseline_date=_s("baseline_date", ""),
        fed_stance=_s("fed_stance", ""),
        real_rate_10y=_s("real_rate_10y", ""),
        dxy=_s("dxy", ""),
        gold_price=_s("gold_price", ""),
        sentiment_momentum=_s("sentiment_momentum", ""),
        geo_risk_level=_s("geo_risk_level", ""),
        manual_context=_s("manual_context", ""),
    )

