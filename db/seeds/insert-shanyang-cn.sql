-- Seventh Profile: 山羊君的社会洞察 (shanyang-cn).
-- Producer 模式，跟 editorial-cn 同范式但**更克制更狠**——专挖中国当代
-- 社会痛点：乡村空心、农民失地、就业、戾气、失独老人、产业关停后续、
-- 政策衰减。低频高质量，每条都要有深度+洞见+判断。
--
-- 跟 editorial-cn 的具体区别：
--   - tone 强调"克制 + 反 b 站爆款腔" —— **不要"答案扎心又现实"的标题党感**
--   - forbidden 加上一组 b 站常见标题党词，避免落入俗套
--   - exemplars 复用 36氪 + 失业 + 口红效应（这些就是社会痛点 op-ed 范式）
--   - tts_voice 不锁，agent 自决（操作员选项 #2）
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-shanyang-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'shanyang-cn',
  '山羊君的社会洞察 — producer 模式，命题创作，专挖中国当代社会痛点。低频高质量。克制不煽动、反 b 站爆款腔。Voice 由 agent 按内容自决。',
  '{
    "source": {
      "platforms": ["doubao", "pexels"],
      "language": null,
      "content_hints": []
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": null,
      "tts_rate_pct": null,
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
      "channel_position": "中文社会洞察频道，挖痛点、找反共识、给判断。题材聚焦中国当代社会问题——乡村空心化、农民失地、就业困境、戾气盛行、失独老人、产业关停后续、政策衰减。低频，高质量，每条都要有深度+洞见+价值观点",
      "tone": "**克制、沉稳、反爆款腔**。不卖惨、不空喊、不哗众取宠；像有思考能力的旁观者；引用要克制、判断要敢、词汇要精；文气接近书面但保持可听性；**绝不要 b 站常见的「答案扎心」「细思极恐」「我跟你讲」那种煽动语气**",
      "vocabulary": "中文为主，专有名词可保留英文；通识表达，不编具体数字 / 引述；遇到具体事件名（例如「湖南烟花厂爆炸」）可以直接引用，但相关数据若不确定就用「公开报道」「行业估算」等通用化表述",
      "verbal_tics": ["本质上", "再深一层", "说白了", "归根结底", "退一步看"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "重磅",
        "你别说",
        "我跟你讲",
        "划重点",
        "答案扎心又现实",
        "你绝对想不到",
        "细思极恐",
        "看完不淡定了",
        "炸裂",
        "硬核"
      ],
      "must_include_disclaimer": false,
      "style_exemplars": {
        "ref_bvids": ["BV12T4y1F7LT", "BV1Su411a7A3", "BV1KkRZBGEwi"],
        "dynamic": {
          "target_count": 3,
          "min_views": 100000,
          "duration_band": "3",
          "max_age_days": 730
        }
      },
      "video_format": {
        "depth_mode": "deep",
        "target_duration_min": "5-8",
        "outline_points": "8-12",
        "shots_per_video": "16-22",
        "pacing": "dense",
        "inter_shot_pause_sec": 0.0,
        "explain_unfamiliar_concepts": true,
        "directive": "shanyang 是优质深度频道：每个论点都要展开（事实/逻辑/例子），不能直接抛结论；非通识概念第一次出现先解释再展开；视频偏长（5-8 min），所以**节奏必须紧凑**，shot 之间几乎不留 pause"
      },
      "topic_discovery": {
        "feed_ids": ["zhihu_hot", "thepaper_featured", "36kr_latest", "weibo_hot"],
        "include_keywords": [],
        "exclude_keywords": [
          "明星", "综艺", "网红", "追星", "粉丝", "饭圈",
          "电竞", "游戏", "动漫", "二次元", "cosplay",
          "演唱会", "选秀", "偶像", "出道", "颁奖",
          "美妆", "穿搭", "时尚",
          "彩票", "中奖",
          "宠物", "萌宠"
        ],
        "max_picks": 8
      }
    },
    "topic_generation_prompt": "你为一个面向中文受众的「社会洞察」频道选题。聚焦中国当代社会的痛点和反共识：乡村空心化、农民失地、就业困境、戾气盛行、失独老人、产业关停后续、政策衰减、阶层与代际矛盾。**结合最近的热点新闻**（如最近的工厂事故、产业关停、政策变动），从中挖掘可深挖的角度。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和挖掘角度提示。",
    "edit_style_prompt": "你写命题创作的 narration：**克制 editorial 立场**，8-11 个 shot，每 shot 30-45 字。论点驱动结构（thesis → evidence → counter → takeaway），不是事件流。每 shot 同时给 visual_brief_en（5-10 个英文词），具体可视化以便从 Pexels 取素材或 Doubao 生成。中国文化具体场景标 asset_strategy=\"ai\"。**通识表达不编具体数据，不卖惨不煽动**。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
