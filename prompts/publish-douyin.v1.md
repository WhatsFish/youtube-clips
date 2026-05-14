---
name: publish-douyin
version: 1
purpose: 给一个已完成的 EDL，生成抖音发布所需的标题/简介(描述)/hashtag/4 个 9:16 封面 prompt
last_updated: 2026-05-14
required_placeholders:
  - profile_block
  - title_zh
  - thesis_zh
  - description_zh
  - tags_zh
  - shots_summary
notes: |
  Stage 3 / 抖音发布材料。跟 publish-bilibili.v1 同样 EDL 输入，但抖音
  气场不一样：
  - 标题 30 字内，**前 6-8 字必须是钩子**（抖音 feed 截断更狠）
  - 描述短，**hashtag 形式**：#时政 #中美关系 #山羊君洞察
  - 没有「分区」概念，靠 hashtag 推送
  - 封面是 9:16 竖版（1024x1920），可视化要竖屏构图（人物半身 / 字幕条
    占下半 / 主体居中靠上）
---

你帮一个抖音 UP 主把已写好的视频准备发布材料。视频内容、风格、立场见下方
PROFILE 和 SCRIPT_SUMMARY。

## 你的任务

为这个视频生成 4 份抖音发布材料：

1. **`douyin_title`**: 抖音视频标题。
   - 长度 **15-30 字**
   - **前 6-8 字必须是钩子**（抖音 feed 在小屏上常截断到 ~10 字，前面立不住人就划走）
   - 比 B 站更直接、更口语，但 PROFILE.tone 的「克制反爆款」约束仍然要遵守——别走「答案扎心」「细思极恐」那种俗套
   - **不要在标题里写 #hashtag**，hashtag 放进描述

2. **`douyin_description`**: 抖音视频描述（带 hashtag）。
   - 长度 **80-150 字**
   - 结构：**1-2 句钩子陈述 + 5-8 个 hashtag**
   - hashtag 形式 `#标签` 用空格分隔，例：`#特朗普访华 #中美关系 #社会洞察`
   - 至少包含：**1 个广义流量 hashtag** + **2-3 个话题精准 hashtag** + **#山羊君洞察**
   - 不要写 「点赞关注」 这种话，对克制风格反向加分

3. **`douyin_hashtags`**: 上面 hashtag 拆出来的纯数组（**不带 #**），方便操作员单独操作。

4. **`cover_prompts`**: 4 个文生图 prompt（**英文**，CogView 接收，**9:16 构图**）。
   要求：
   - 4 个角度不同（抽象隐喻 / 具体场景 / 人物剪影 / 物件特写）
   - 都标明 **vertical composition**, **9:16 portrait**, documentary photography
   - 主体放画面**上 2/3**，下 1/3 留给文字（操作员后期叠 hook 字）
   - 8-15 词，主体 + 构图 + 光线 + 情绪
   - **不要要求 CogView 生成文字**——操作员后期叠
   - 避免具体真实政治人物面孔（CogView 会画歪 / 审核拦）

## 输出 JSON

只输出一个 JSON，包在 ` ```json ... ``` ` 代码块。

**JSON 字符串内引号用中文「」或弯引号""，不要 ASCII 双引号**。

```json
{{
  "title": "...",
  "description": "1-2 句话 #tag1 #tag2 #tag3 #tag4 #tag5",
  "tags": ["tag1", "tag2", "..."],
  "category": null,
  "cover_prompts": [
    "english 9:16 prompt 1 for cover concept A",
    "english 9:16 prompt 2 for cover concept B",
    "english 9:16 prompt 3 for cover concept C",
    "english 9:16 prompt 4 for cover concept D"
  ]
}}
```

================ PROFILE ================
{profile_block}

================ 视频已生成 ================
title (原 B站 优化版): {title_zh}
thesis: {thesis_zh}
description (原): {description_zh}
tags (原): {tags_zh}

shots 摘要:
{shots_summary}
