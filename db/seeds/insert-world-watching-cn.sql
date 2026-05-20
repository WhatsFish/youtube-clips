-- Sixth Profile: 环球生活观察 (world-watching-cn).
-- Commentary 模式，跟 overseas-vlog-cn 同范式但**拓宽到全球**——日本不
-- 是中心、发达国家不是限制；东南亚 / 拉美 / 中东 / 非洲 / 北美各国
-- 日常 vlog 都进搜索。频道目标是"带中文观众认识全世界"，量为主、
-- 留存为主、对比为切入点。
--
-- 跟 overseas-vlog-cn 的具体区别：
--   - channel_position 改成"全球"而非"日本日常"
--   - edit_style_prompt 显式给"对比框"模板：钱→人民币 / 时间→中国对照
--     / 习俗→咱中国人看着... / 一小时购买力
--   - tts_voice 不锁，agent 自决（操作员选项 #2）
--   - exemplars 复用 overseas-vlog 的 + 加 36氪 (cross-cultural data style)
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-world-watching-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'world-watching-cn',
  '环球生活观察 — commentary 模式，跟海外博主镜头看全世界日常。日本以外的国家也来。重点是中文观众视角的对比和指认（物价/工资/习俗），量为主，留存为主。Voice 由 agent 按内容自决。',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": [
        "day in the life", "vlog", "cost of living", "supermarket tour",
        "salary breakdown", "what i eat in a day",
        "Japan", "Korea", "Vietnam", "Thailand", "Philippines",
        "Mexico", "Brazil", "Argentina",
        "Germany", "France", "Italy", "Spain", "UK",
        "Egypt", "Nigeria", "Kenya",
        "USA", "Canada", "Australia"
      ]
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
      "pacing": "relaxed",
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
      "production_mode": "commentary",
      "prompt_name": "edl-commentary-world",
      "channel_position": "面向中文受众的环球生活观察频道，**带观众见识全世界各地正在发生的有趣事、领略不同的生活方式**。日本、东南亚、欧洲、拉美、非洲、北美、中东都在视野里。**轻松、好奇、长见识**为主调，不端着、不上价值观、不下结论；不是「中国人看世界」的对比节目，更像「跟朋友一起逛逛地球」",
      "tone": "亲切+好奇+轻松。像跟朋友一起看世界另一面——看到有意思的细节就描述、好奇就追问、不懂的就解释、夸张的就感叹。**不上价值观、不下结论、不站队**。不端着、不文绉绉；情绪有起伏但不夸张。中国联想是顺带的，不是主轴",
      "vocabulary": "口语化为主，避免学术词；钱出现时如果数字有意思（特别便宜/特别贵/反常识）可以顺带换算人民币，**不强制每条聊钱**；距离用公里，温度用摄氏度；专有名词第一次出现一句话解释；地名 / 人名第一次出现给一句背景",
      "verbal_tics": ["你看", "听我说", "在 X 国这边", "你别说", "这事其实", "原来"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "深度剖析",
        "不容忽视",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "重磅"
      ],
      "must_include_disclaimer": false,
      "style_exemplars": {
        "ref_bvids": ["BV1fgoVBGE2M", "BV1kLdsByEhq", "BV12T4y1F7LT"]
      },
      "outro": {
        "text_line1_zh": "跟着镜头去看更多地球角落",
        "text_line2_zh": "点赞关注，下条见",
        "background_prompt_en": "abstract cinematic background, sky blue gradient transitioning to sunset gold on the horizon, with a hint of vast open atmosphere, traveling spirit, very minimalist, no text no faces no objects",
        "duration_sec": 3
      },
      "topic_discovery": {
        "youtube_queries": [
          "Vietnam daily life street food vlog",
          "Mexico City surprising culture quirks vlog",
          "Portugal Lisbon weird everyday rituals",
          "Argentina Buenos Aires unique daily routine",
          "Kazakhstan Almaty cultural shock vlog",
          "Egypt Cairo unusual local customs",
          "Indonesia Bali daily oddities vlog",
          "Turkey Istanbul daily life surprises",
          "Brazil Sao Paulo cultural difference",
          "Thailand Bangkok weird local life",
          "Philippines Manila daily customs surprise",
          "Iceland Reykjavik daily life quirks",
          "South Africa Cape Town daily routine",
          "Korea Seoul weird everyday things",
          "Italy daily routine cultural quirks"
        ],
        "exclude_keywords": [
          "shorts only", "TikTok compilation", "reaction video"
        ],
        "max_picks": 8
      },
      "publish_channels": [
        {
          "platform": "bilibili_long",
          "render_aspect": "16:9",
          "cover_aspect": "16:10",
          "cover_size": "1280x800",
          "cover_count": 4,
          "publish_prompt": "publish-bilibili"
        },
        {
          "platform": "douyin",
          "render_aspect": "9:16",
          "cover_aspect": "9:16",
          "cover_size": "1024x1920",
          "cover_count": 0,
          "publish_prompt": "publish-douyin"
        }
      ]
    },
    "topic_generation_prompt": "你为一个面向中文受众的「环球生活观察」频道选题。**频道定位是带观众见识不同地方的生活方式，不是「中国人看世界」的对比节目**——所以选题时不要硬找跟中国对比的钩子，也不要每条都聚焦物价工资。候选话题来自最近 1-2 周内 YouTube 上的海外日常 vlog 与生活观察内容，**国家务必多样化**（每批至少覆盖 4 个不同国家或大洲，避免连日本/北美刷屏）。欢迎角度：(a) 当地独特的文化习俗 / 仪式 / 礼节，(b) 当地特色食物 / 烹饪 / 餐桌习惯，(c) 城市或乡村的独特生活细节（通勤方式、住房形态、社区结构），(d) 工作日常的有趣切面（特殊职业、上下班节奏），(e) 历史 / 地理小知识（一个细节带出更大背景），(f) 教育、育儿、老年生活。**轻松 + 长见识 + 有趣**为主调——让中国观众笑一下、惊一下、长点见识。如果某个角度跟中国有自然的联想/差异（不强求），写出来也行；不要为了对比而对比。规避高门槛专业话题、规避新闻时政。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL，**主打「带观众见识 + 解释 + 感叹」**——而不是「中国观众视角的对比 / 吐槽」。8-12 个 shot，每个 shot 一句中文（25-40 字）配源视频画面。**视角选择**：(a) 描述并解释画面里在发生什么，(b) 补一点相关的背景 / 历史 / 地理科普，(c) 适当的轻幽默感叹（不上价值观），(d) **如果跟中国有自然的联想或差异，可以顺带一提，但不要硬掰**——更不要每个 shot 都拉回中国。**不下结论、不站队、不上价值观**。亲切口语，verbal_tics 自然嵌入。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
