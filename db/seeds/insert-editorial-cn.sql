-- Fifth Profile: producer 模式（命题创作 / 自创）。第一个不依赖源 YouTube
-- 视频的 Profile —— topic + Profile 由 agent 自己写大纲、写文案、配
-- Pexels 库存画面。区别于 commentary（陪同观察源）/ synthesis（综合多
-- 源观点输出）。
--
-- 风格定位：editorial（编辑性）—— 像 The Atlantic 视频版 / Vox 解释员，
-- 不娱乐、不口语化、不"邻家姐姐"，是有立场有结构的「编辑视频」。沉
-- 稳男声，节奏中等。
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-editorial-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'editorial-cn',
  'Producer-mode profile: 命题创作 (topic-first, script-first). 不依赖 YouTube 源，由 agent 写大纲+文案，Pexels 库存视频做画面。Editorial 立场，沉稳男声，3-4 分钟解释员风格。',
  '{
    "source": {
      "platforms": ["pexels"],
      "language": null,
      "content_hints": []
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunzeNeural",
      "tts_rate_pct": 5,
      "aspect_ratio": "16:9"
    },
    "style": {
      "template": "continuous_commentary",
      "pacing": "measured",
      "audio_strategy": "ducked_original",
      "source_audio_volume": 0.05,
      "narration_volume": 1.6,
      "caption_strategy": "burn_zh"
    },
    "branding": {
      "intro_path": null,
      "outro_path": null,
      "watermark": null
    },
    "channel": {
      "production_mode": "producer",
      "channel_position": "面向中文受众的 Bilibili 编辑性视频频道，做 3-4 分钟的解释员风格命题创作（不是评论别人的视频，是自己讲一个题目）",
      "tone": "沉稳、有结构、不煽动、不耍宝；像在镜头前认真讲一件事的解释员；引述要克制、有立场但不偏激；文气接近书面但保持口语易听",
      "vocabulary": "中文为主，专有名词可保留英文（YouTube、AI、GDP），避免大段英文；通识表达，不编具体数字 / 引述",
      "verbal_tics": ["要这么看", "归根结底", "说回来", "退一步讲", "本质上"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "重磅",
        "你别说",
        "划重点"
      ],
      "must_include_disclaimer": false
    },
    "topic_generation_prompt": "你为一个面向中文受众的编辑性视频频道选题。命题视频，不依赖现成 YouTube 源。题材偏向：观察社会现象、解释一个被忽视的趋势、回顾一段历史、提出一个反共识观点。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述。",
    "edit_style_prompt": "你写命题创作的 narration：thesis-driven 编辑性立场，8-12 个 shot，每 shot 25-45 字。每 shot 同时给 visual_brief_en（5-10 个英文词），具体可视化以便从 Pexels 取素材。通识表达不编具体数据。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
