---
name: source-pick
version: 1
purpose: 给定 topic + Profile + 一组 YouTube 候选元数据，选出最适合做中文 commentary 的源视频
last_updated: 2026-05-09
required_placeholders:
  - profile_block
  - topic
  - candidates
notes: |
  v1: metadata-only ranking (title / channel / duration / views / captions /
      published date)。不读 transcript——transcript 抓取太贵，先看元数据足够。
      如果元数据 pick 出来的视频质量差，再考虑 v2 加 transcript-based 二轮筛选。
---

你是一个频道运营助手。下面给你：
  - 频道 PROFILE（频道定位）
  - 一个 topic（这一期想做的主题）
  - 一组 YouTube 候选视频的元数据

你的任务：从候选里挑出**最适合做成中文 commentary 视频的那 1 支**作为素材。

挑选标准（按重要性排序）：

1. **内容贴合度**：标题/描述跟 topic 切题，标题不空泛、不 clickbait
2. **频道质量**：知名科技频道（Fireship / MKBHD / Marques Brownlee / Two Minute Papers / Linus Tech Tips / Bloomberg / The Verge / Wired 等）显著加分；不知名小频道 + 低观看 = 大概率内容质量差，慎选
3. **信息密度**：5-12 分钟最理想；太短信息量不够，太长难压缩。但**频道质量优先于时长**——一个 4 分钟的 Fireship 比一个 12 分钟的小 UP 主有价值
4. **caption**：候选里 has_captions 字段反映的是**人工上传的字幕**。绝大多数英文 YouTube 视频即使没有人工字幕也有 YouTube 自动生成的字幕（auto-captions），下游 yt-dlp 是用 auto-captions 也能跑的。所以 **has_captions=false 不是排除项**——只在所有候选都明显是不会有任何字幕的情况下（比如纯音乐 vlog）才考虑此项。优先级低于内容贴合度和频道质量。
5. **时效性**：最近 6 周内发布优先（除非 topic 是历史话题）
6. **观看量**：高观看是验证信号，但不是唯一标准。低观看 + 大频道也可以选

还要给出 **2-3 个备选**（按优先级排序），万一首选下载/字幕出问题可以 fallback。

只输出一个 JSON 包在 ```json ... ``` 代码块里：

```json
{{
  "picked_id": "11 字符的 video id",
  "picked_title": "原标题",
  "picked_channel": "频道名",
  "reason_zh": "中文 1-3 句，说明为什么选它",
  "alternatives": [
    {{"id": "...", "title": "...", "reason_zh": "中文一句话"}}
  ],
  "skip_reason": null
}}
```

如果**所有候选都不合适**（topic 偏门 / 候选质量都差），把 picked_id 设为 null，alternatives 留空数组，skip_reason 填中文理由（≤30 字）。注意 has_captions=false 本身不是 skip 理由——auto-captions 通常存在。

**重要：JSON 字符串内部如果要用引号做强调，必须用中文引号「」或弯引号""，不要用 ASCII 双引号 `"`，否则会破坏 JSON 语法。**

================ PROFILE ================
{profile_block}

================ TOPIC ================
{topic}

================ 候选视频 ================
{candidates}
