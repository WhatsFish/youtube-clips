---
name: topic-discover
version: 1
purpose: 从多源中文 RSS 候选里挑出契合 Profile 的视频选题
last_updated: 2026-05-12
required_placeholders:
  - profile_block
  - feed_registry_block
  - candidates_block
notes: |
  这条 prompt 接在 RSS fetch + 关键词预过滤之后。输入：N 个候选条目
  （来自微博/知乎/澎湃/36氪等），加上 Profile 完整定位。输出：5-10 个
  最贴合频道方向的话题，每个含 title / description / suggested_angle。
  pipeline 把输出落到 topics 表 status='pending'，操作员审批。
---

你帮一个中文视频频道选题。频道完整定位见下方 PROFILE。

你的任务：**从下面这批 RSS 候选里挑出 5-10 个最契合频道方向的话题**。

## 挑选原则

- **贴合频道核心定位**。看 PROFILE.channel.channel_position 和 tone —— 频道做什么、对谁、关心什么。只挑能服务这个定位的。
- **可深挖**。能延伸出洞见、对比、判断的话题优先；纯事件通报（"X 公司被罚 X 元"这种）跳过，除非有深度可挖。
- **时效性 + 普世性**。最近发生 + 多数中国观众有切身感的优先。专业小众话题除非频道就是专业向，否则跳过。
- **避免清单 / 标题党**。原标题就是"3 个原因 / 5 个迹象 / 你绝对想不到"那种，要么改写要么跳过。
- **拒绝纯娱乐**：明星八卦、综艺花絮、电竞、追星，除非频道明确就是娱乐向。

## 输出要求

每个被选中的话题给三个字段：

- **title**：12-25 字的中文标题。要有钩子、可作为视频 title 直接用。**不要照抄原标题**——很多 RSS 标题是清单体或新闻体，需要改写成视频钩子语气。
- **description**：1-2 句中文。说这个话题值得做的"角度"是什么——不是事件本身，是延伸出去能讲什么。
- **suggested_angle**：1-2 句。给视频脚本写作的引子——这条做出来应该走哪个论点 / 哪个对比 / 哪个反共识。

附带：reasoning（选这条的理由）和 source_feed（来自哪个 feed）。

## 输出 JSON

```json
{{
  "picks": [
    {{
      "title": "中文标题",
      "description": "1-2 句话",
      "suggested_angle": "1-2 句话",
      "reasoning": "为什么挑这条",
      "source_feed": "zhihu_hot",
      "source_link": "https://..."
    }}
  ],
  "skipped_reason": "如果一个都没挑（罕见），写一句话原因；否则 null"
}}
```

**重要**：JSON 字符串内部用中文引号「」或弯引号""，不要用 ASCII 双引号。

================ PROFILE ================
{profile_block}

================ FEED REGISTRY（候选来自哪些源） ================
{feed_registry_block}

================ 候选条目 ================
{candidates_block}
