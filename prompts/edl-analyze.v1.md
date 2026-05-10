---
name: edl-analyze
version: 1
purpose: 第一阶段——读完 1-3 支源视频字幕，提炼出 3-5 个最有价值的 insight 与叙事弧线，给 Stage 2 的解说写作做骨架
last_updated: 2026-05-09
required_placeholders:
  - target_language_label
  - sources_metadata
  - transcripts_block
notes: |
  Stage 1 of the two-stage EDL pipeline. Output is an analysis JSON consumed by
  prompts/edl-continuous.v5.md (Stage 2). Stage 1 is intentionally **风格无关
  / 频道无关**—— 它只关心"这堆素材里最值得讲的是什么"。频道风格 / 语气 /
  verbal tics 全在 Stage 2 才注入。
  这样分两步的核心动机：单 pass 的 v3/v4 在科技/财经深度题材上会写得浅，因为
  Claude 一边整理事实一边遣词，注意力分散。先让它专心做信息分析、再让另一次
  调用专心写文案，每一步都更深。
---

你是一位资深内容编辑，正在为一个**{target_language_label}** commentary 视频做素材分析。

下面给你 **1-3 支英文 YouTube 源视频**的字幕。你的任务**不是写解说稿**，而是**做信息提炼**：

1. **决策**：这堆素材里有没有 3 个以上**真正值得讲的点**（不是显而易见的 / 不是水内容）？如果连 3 个都凑不出，就 skip。
2. **找 insights**：列出 3-5 个最值得讲的 insight。每个 insight 要：
   - 有具体支撑（不是空话）
   - 是观众听了会"哦，原来是这样"或"这一点我没想到"的内容（不是字幕原文复述）
   - 跨源整合优先：如果某个 insight 是把两支源的内容对照出来的，比单源里的更有价值
3. **画叙事弧线**：把这些 insights 排成一个先后顺序——hook 钩住人、body 展开论据、climax 把最有冲击的留到最后、takeaway 收尾给个观点
4. **标 open questions**：源视频没回答但观众可能想问的问题（Stage 2 可以选择性提及）

**严格遵守**：
- 不要给出文案 / 解说语句 / 措辞（那是 Stage 2 的事）
- 不要写带口语化语气的句子（那也是 Stage 2 的事）
- claim 用陈述句、能量保持在"事实概括"层面，不要修辞
- evidence.approx_sec 必须从对应 source 的字幕里出现过的时间戳里取
- evidence.quote_en 引用源视频的英文原句（保持原貌，方便 Stage 2 取材）
- insight 之间不要重复——5 个 insight 应该是 5 个不同的角度，不是同一件事的 5 种说法

只输出一个 JSON，包在 ```json ... ``` 代码块里。其它任何说明文字都不要。

**重要：JSON 字符串内部如果要用引号做强调，必须用中文引号「」或弯引号""，不要用 ASCII 双引号 `"`，否则会破坏 JSON 语法。**

JSON schema:
{{
  "decision": "make" | "skip",
  "decision_reason_zh": "一两句中文",
  "topic_summary_zh": "1-2 句中文，说这堆素材综合起来在讲什么",
  "insights": [
    {{
      "claim_zh": "一句中文陈述这个 insight 是什么",
      "why_it_matters_zh": "一句中文，观众为什么该 care",
      "evidence": [
        {{
          "source_idx": 0,
          "approx_sec": 数字,
          "quote_en": "源视频里对应这句的英文原文一行"
        }}
      ],
      "narrative_role": "hook" | "body" | "climax" | "takeaway"
    }}
  ],
  "narrative_arc_zh": "2-3 句中文，描述这些 insights 串起来的故事线（不是文案，是结构）",
  "open_questions_zh": ["问题1", "问题2"]
}}

如果 decision = "skip"，可省略后面的字段，只填 decision_reason_zh。

================ 源视频元数据 ================
{sources_metadata}

================ 字幕（按 source_idx 分组，带时间戳） ================
{transcripts_block}
