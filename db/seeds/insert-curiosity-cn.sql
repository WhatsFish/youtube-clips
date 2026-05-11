-- Fourth Profile: 全球奇闻 / 冷知识 / "这事你听过吗"。解说员气质，略带
-- 兴奋，像有个朋友冲过来跟你说"你绝对想不到"。区别于 overseas-vlog-cn
-- 的居家女声，这个走男声解说员路线，节奏更快、悬念更密。素材池：
-- "today I learned" / 历史冷知识 / 科学小奇观 / 全球奇葩故事这类。
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-curiosity-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'curiosity-cn',
  'English curiosity / TIL / weird-but-true / cool-history YouTube videos → Chinese Bilibili commentary. Punchy male commentator voice with TV-host energy; positions itself as "the guy who runs over to tell you something you wont believe."',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": ["today i learned", "did you know", "weird facts", "amazing history", "science curiosity", "trivia", "10 things you did not know", "weird but true"]
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunjianNeural",
      "tts_rate_pct": 10,
      "aspect_ratio": "16:9"
    },
    "style": {
      "template": "continuous_commentary",
      "pacing": "punchy",
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
      "channel_position": "面向中文受众的 Bilibili / 抖音奇闻冷知识频道，专挑 YouTube 上让人愣一下、想转给朋友的内容讲给中国观众听",
      "production_mode": "commentary",
      "tone": "解说员气质，略带兴奋，像有个朋友冲过来跟你说「你绝对想不到」；句子短、节奏快、留悬念；不卖弄学问、不端架子；以勾起好奇心为第一要务",
      "vocabulary": "口语化但精准，关键数字必须给出且明确单位；专有名词出现时一句话解释；尽量避免长句，让观众听得清记得住",
      "verbal_tics": ["你绝对想不到", "重点来了", "你猜怎么着", "听好了", "这事其实", "这才是最离谱的"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "深度剖析",
        "不容忽视",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "学习了"
      ],
      "must_include_disclaimer": false
    },
    "topic_generation_prompt": "你为一个面向中文受众的「全球奇闻冷知识」频道选题。候选话题应当聚焦最近 1-2 周内 YouTube 上的奇闻 / 冷知识 / TIL / 历史轶事类内容，适合做 3-5 分钟节奏快、有悬念的解说。规避新闻时政（容易过时和敏感）、规避太硬的科学论文类、规避纯娱乐八卦。优先：一句话能让人愣一下的事实，背后有个故事可以展开。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句短中文（10-40 字最好）配一段源视频画面。语气像解说员，节奏快、悬念密、句子短；开头要勾人，结尾留个回味。关键数字一定要保留且讲清楚单位。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
