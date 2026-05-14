---
name: publish-bilibili
version: 1
purpose: 给一个已完成的 EDL，生成 B站发布所需的标题/简介/标签/分区/4 个封面 prompt
last_updated: 2026-05-14
required_placeholders:
  - profile_block
  - title_zh
  - thesis_zh
  - description_zh
  - tags_zh
  - shots_summary
notes: |
  Stage 3 / 发布材料生成。接在 produce-original 的 Stage 2 (script) 之后。
  跟 producer-script 的 title/description/tags **不一定一样**——这一阶段
  专门为 B站受众优化：
  - 标题钩子要更直接（B站 12-25 字标题区间，前 12 字最重要）
  - 简介前 50 字关键（搜索 + 推送都看）
  - tags 用 B 站常见词，覆盖搜索路径
  - 分区按内容选合适的二级分区
  - 4 个封面的 prompt：风格不同的视觉切入，让操作员挑
  封面 prompt **不是给 agent 画图的**，是给 CogView 文生图的 prompt。
---

你帮一个 B 站 UP 主把已写好的视频准备发布材料。视频内容、风格、立场见下方
PROFILE 和 SCRIPT_SUMMARY。

## 你的任务

为这个视频生成 5 份 B站 发布材料：

1. **`bili_title`**: 12-25 字 B站标题。
   - 前 12 字必须能站住（B站标题在列表/推送里常被截断到 12-15 字）
   - 钩子要直接但不爆款腔（参考 PROFILE.tone 的「克制 + 反爆款」约束）
   - 不要复制原 narration 标题，给一个 B站-specific 的版本

2. **`bili_description`**: B站 视频简介。
   - **前 50 字最关键**（搜索 + 推送算法都看这段）
   - 整体 100-200 字
   - 不要凑 hashtag，写成完整两三句
   - 结尾可以问一个引导互动的问题（可选）

3. **`bili_tags`**: 6-10 个标签。
   - B站允许最多 10 个标签
   - 一定要包含：1-2 个**广义流量词**（如「时政」「社会观察」）+ 2-3 个**话题精准词**（如「特朗普访华」「中美关系」）+ 1-2 个**频道身份词**（如「山羊君洞察」「深度观察」）
   - 单个标签 ≤ 8 字

4. **`bili_category`**: B站二级分区。从这些选 1 个：
   - `knowledge.social_law_psychology` 知识 → 社科·法律·心理（**深度社会议题首选**）
   - `knowledge.humanities_history` 知识 → 人文历史
   - `knowledge.science` 知识 → 科学科普
   - `knowledge.finance_business` 知识 → 财经商业（财经主题）
   - `news.current_affairs` 资讯 → 时事（时政热点首选）
   - `news.tech` 资讯 → 科技

5. **`cover_prompts`**: 4 个文生图 prompt（**英文**，CogView 接收）。每个产出 1 张封面候选。
   要求：
   - 4 个角度不同（例：抽象隐喻 / 具体场景 / 人物剪影 / 物件特写）
   - 都是 16:10 横画面 documentary photography 风格（绝不卡通 / 表情包 / 浮夸）
   - 8-15 词，包含主体 + 构图 + 光线 + 情绪
   - **不要在 prompt 里要求 CogView 生成文字**——文字操作员会后期叠加
   - 避免出现具体识别明确的政治人物面孔（CogView 会画歪，且 B 站审核可能拦）

## 输出 JSON

只输出一个 JSON，包在 ` ```json ... ``` ` 代码块。其它说明不要。

**JSON 字符串内引号用中文「」或弯引号""，不要 ASCII 双引号**。

```json
{{
  "bili_title": "...",
  "bili_description": "...",
  "bili_tags": ["...", "...", ...],
  "bili_category": "knowledge.social_law_psychology",
  "cover_prompts": [
    "english prompt 1 for cover concept A",
    "english prompt 2 for cover concept B",
    "english prompt 3 for cover concept C",
    "english prompt 4 for cover concept D"
  ]
}}
```

================ PROFILE ================
{profile_block}

================ 视频已生成 ================
title (原): {title_zh}
thesis: {thesis_zh}
description (原): {description_zh}
tags (原): {tags_zh}

shots 摘要:
{shots_summary}
