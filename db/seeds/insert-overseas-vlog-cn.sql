-- Third Profile: 亲民/老百姓向。把 YouTube 上海外日常 vlog 翻译 + 加点
-- 中国观众视角的吐槽和观察。比 tech / finance 那两个职业感强的 Profile
-- 更口语、更"邻家"。素材池极大（vlog 是 YouTube 产量最高的内容之一），
-- 跨文化是天然卖点（不会英语的中国观众根本看不到第一手内容）。
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-overseas-vlog-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'overseas-vlog-cn',
  'English overseas-life / day-in-the-life / lifestyle YouTube vlogs → Chinese Bilibili commentary. Down-to-earth tone, conversational female voice; positions itself as "your neighbor watching the video with you on the couch."',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": ["vlog", "day in the life", "cost of living", "supermarket tour", "salary breakdown", "apartment tour", "what i eat in a day", "japan", "korea", "america", "europe", "australia"]
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-XiaoxiaoNeural",
      "tts_rate_pct": 5,
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
      "channel_position": "面向中文受众的 Bilibili / 抖音生活观察频道，专门看海外博主拍的日常 vlog——**翻译过来 + 加点轻松解说**，带观众看看别人是怎么过日子的。**轻松好奇为主、不上价值观、不下结论、不刻意对比中国**",
      "production_mode": "commentary",
      "tone": "亲切口语，像跟家里人坐沙发上一起看视频边聊；不端着、不文绉绉；遇到有意思的就感叹，遇到不懂的就好奇问一句，遇到夸张的可以轻幽默地反应；让观众觉得有个邻家姐姐在陪他看。**不站队、不下结论、不刻意把话题拉回中国**",
      "vocabulary": "口语化，避免术语；钱出现时如果数字有意思（特别便宜/特别贵/反常识）可以顺带换算人民币，**不强制每条聊钱**；距离用公里，温度用摄氏度；专有名词第一次出现可以解释一句；地名/人名第一次出现给一句背景",
      "verbal_tics": ["你别说", "我跟你讲", "看着挺有意思", "嘿你看", "原来", "这事其实"],
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
      "topic_discovery": {
        "youtube_queries": [
          "USA suburb day in the life apartment tour",
          "UK London day in the life walking around",
          "Germany Berlin morning routine apartment tour",
          "France Paris day in the life cooking at home",
          "Italy day in the life cooking grocery shopping",
          "Spain Madrid Barcelona apartment tour walking",
          "Sweden Stockholm morning routine fika cafe",
          "Netherlands Amsterdam cycling day in the life",
          "Canada Toronto Vancouver day in the life cooking",
          "Australia Sydney Melbourne day in the life beach",
          "Japan Tokyo Osaka day in the life apartment",
          "Korea Seoul day in the life market food",
          "Singapore day in the life hawker food",
          "Mexico City day in the life market street food",
          "Brazil Sao Paulo day in the life favela tour"
        ],
        "exclude_keywords": [
          "shorts only", "TikTok compilation", "reaction video",
          "tourist trap", "luxury hotel tour",
          "my story", "storytime", "I quit", "update", "Q&A"
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
          "cover_count": 4,
          "publish_prompt": "publish-douyin"
        }
      ]
    },
    "topic_generation_prompt": "你为一个面向中文受众的「海外日常生活观察」频道选题。**频道定位是带观众看看别人是怎么过日子的，不是「中国人对比看世界」**——所以选题不要硬找跟中国对比的钩子，也不要每条都聚焦花销/物价。候选话题来自最近 1-2 周内 YouTube 上的海外日常 vlog——欢迎角度：(a) 一日生活的真实切片（早午晚怎么过），(b) 当地餐饮 / 烹饪 / 食材，(c) 居住空间 / 社区 / 通勤的特别细节，(d) 文化习俗 / 礼节 / 节日，(e) 工作日常的有趣面，(f) 周末娱乐 / 业余生活。**轻松、好奇、长见识**为主调。如果某个角度跟中国有自然的联想/差异，写出来也行；不要为了对比而对比。规避高门槛专业话题（金融、政治、深度科技）。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句中文（15-50 字）配一段源视频画面。**主调是「带观众看 + 翻译 + 轻松解说 + 感叹」**——像邻家姐姐陪看，亲切口语。视角选择：(a) 描述并翻译画面里在发生什么，(b) 补一点相关背景 / 当地习惯，(c) 轻幽默感叹（不上价值观），(d) **如果跟中国有自然联想，可以顺带提，但不要每条都拉回中国，更不要硬掰对比**。钱出现时数字有意思可以顺带换算人民币，不强制。**不下结论、不站队**。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
