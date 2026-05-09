-- One-shot update for the tech-insights-cn Profile.
--
-- bootstrap.sh's INSERT ... ON CONFLICT DO NOTHING leaves an existing
-- row alone, so when we evolve the demo Profile we apply changes here
-- as a separate UPDATE and run this file by hand:
--
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/update-tech-insights-cn.sql
--
-- Keep this in sync with the seed in schema.sql so a fresh bootstrap and
-- this UPDATE produce the same row shape.

UPDATE profiles
SET
  description = 'English tech YouTube videos → Chinese Bilibili commentary. Demo Profile for the Phase 2 MVP.',
  config_jsonb = '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": ["tech review", "AI news", "developer tools"]
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunxiNeural",
      "tts_rate_pct": 15,
      "aspect_ratio": "16:9"
    },
    "style": {
      "template": "continuous_commentary",
      "pacing": "medium",
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
      "tone": "年轻、专业、有态度，可以有 mild hot take",
      "vocabulary": "技术术语直接用，不需要每个名词都解释",
      "verbal_tics": ["划重点", "反常识的是", "这就有意思了", "值得注意的是"],
      "forbidden_phrases": ["大家好欢迎收看", "今天我们要讲", "如有错误欢迎指正"]
    },
    "topic_generation_prompt": "你为一个面向中文受众的科技频道选题。候选话题应当聚焦最近 1-2 周内英文科技 YouTube 上有讨论度的内容（AI、开发者工具、新品发布、行业动态），适合做 3-5 分钟连续解说视频。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句中文（15-50 字）配一段源视频画面。语气年轻、专业、有态度。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  updated_at = NOW()
WHERE name = 'tech-insights-cn';
