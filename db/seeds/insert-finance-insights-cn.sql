-- Second demo Profile to stress-test the architecture: same source/output
-- pairing as tech-insights-cn (English YouTube → Chinese Bilibili), but
-- different domain, different tone, different verbal tics, different
-- voice. If the rendered output is *audibly and stylistically different*
-- from tech-insights-cn, the Profile abstraction is doing real work and
-- the prompt template is properly profile-driven.
--
-- Apply by hand:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-finance-insights-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'finance-insights-cn',
  'English finance / markets / macro YouTube videos → Chinese Bilibili commentary. Companion Profile to tech-insights-cn for stress-testing the layered Profile model.',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": ["macro", "markets", "investing", "fed", "earnings", "crypto"]
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunyangNeural",
      "tts_rate_pct": 8,
      "aspect_ratio": "16:9"
    },
    "style": {
      "template": "continuous_commentary",
      "pacing": "measured",
      "audio_strategy": "ducked_original",
      "source_audio_volume": 0.10,
      "narration_volume": 1.6,
      "caption_strategy": "burn_zh"
    },
    "branding": {
      "intro_path": null,
      "outro_path": null,
      "watermark": null
    },
    "channel": {
      "channel_position": "面向中文受众的 Bilibili 财经 / 宏观频道",
      "production_mode": "synthesis",
      "tone": "克制、有依据、敢下判断但不煽动；不给买卖建议，永远是 decision support 不是 advice",
      "vocabulary": "金融术语直接用（CPI / 美债 / 久期 / 风险溢价 / 加息周期），不解释每个名词；数字必须给出且明确单位",
      "verbal_tics": ["关键变量是", "需要看一眼", "风险点在于", "市场在 price in 的是", "把账算清楚"],
      "forbidden_phrases": [
        "建议买入",
        "建议卖出",
        "保证赚钱",
        "稳赚不赔",
        "财富自由",
        "今天我们要讲",
        "大家好欢迎收看"
      ],
      "must_include_disclaimer": true,
      "disclaimer_zh": "本视频信息仅供决策参考，不构成投资建议。"
    },
    "topic_generation_prompt": "你为一个面向中文受众的财经科普频道选题。候选话题应当聚焦最近 1-2 周内英文财经 YouTube 上有讨论度的内容（央行政策、宏观数据、龙头公司财报、行业拐点、监管动态），适合做 3-5 分钟连续解说。规避个股具体买卖话题。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句中文（15-50 字）配一段源视频画面。语气克制但敢下判断，金融术语直接用。原音 0.10，中文 1.6 倍。**收尾必须带 disclaimer**：引用 channel.disclaimer_zh 字段的原文。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
