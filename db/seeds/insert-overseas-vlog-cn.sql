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
      "channel_position": "面向中文受众的 Bilibili / 抖音生活观察频道，专门看海外博主拍的日常 vlog，翻译加上中国观众视角的吐槽和观察",
      "production_mode": "commentary",
      "tone": "亲切口语，像跟家里人坐沙发上一起看视频边聊；不端着、不文绉绉；遇到夸张的地方就吐槽，遇到有意思的就感叹；让观众觉得有个邻家姐姐在陪他看",
      "vocabulary": "口语化，避免术语；钱要换算成人民币给出参考（按当时汇率，给个大概数字），距离用公里，温度用摄氏度；专有名词第一次出现可以解释一句",
      "verbal_tics": ["你别说", "这事咱中国人看着", "我跟你讲", "看着挺有意思", "嘿你看", "这一对比"],
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
          "USA suburb daily life vlog day in the life",
          "UK London daily routine vlog",
          "Germany Berlin everyday life vlog",
          "France Paris daily life vlog",
          "Italy daily life vlog day in the life",
          "Spain Madrid Barcelona daily vlog",
          "Sweden Stockholm daily routine vlog",
          "Netherlands Amsterdam daily life",
          "Canada Toronto Vancouver daily vlog",
          "Australia Sydney Melbourne daily life",
          "Japan Tokyo Osaka daily life vlog",
          "Korea Seoul daily life vlog",
          "Singapore daily routine vlog",
          "Mexico daily life day in the life vlog",
          "Brazil daily life vlog"
        ],
        "exclude_keywords": [
          "shorts only", "TikTok compilation", "reaction video",
          "tourist trap", "luxury hotel tour"
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
    "topic_generation_prompt": "你为一个面向中文受众的「海外日常生活观察」频道选题。候选话题应当聚焦最近 1-2 周内 YouTube 上的海外日常 vlog（一日花销、住房成本、超市买菜、上班通勤、租房、餐饮日常、文化反差类内容），适合做 3-5 分钟轻松向解说。规避高门槛专业话题（金融、政治、深度科技）。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL：连续中文解说不间断，源视频做 B-roll。8-15 个 shot，每个 shot 是一句中文（15-50 字）配一段源视频画面。语气像邻家姐姐跟观众一起看视频边吐槽，亲切口语；钱要换算成人民币给个参考；遇到夸张的地方可以吐槽，遇到有意思的地方可以感叹。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
