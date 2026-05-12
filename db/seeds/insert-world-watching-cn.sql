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
      "channel_position": "面向中文受众的环球生活观察频道，带观众看全世界各国的日常生活——日本、东南亚、欧洲、拉美、非洲、北美都在视野里。每条视频带中文观众认识一种不一样的日常",
      "tone": "亲切+好奇+对比意识。像跟朋友一起看世界另一面；不端着、不文绉绉；遇到具体物价、工资、习俗就指认；保持中国观众视角的代入感；遇到反差/小贵小便宜会感叹，遇到陌生细节会解释",
      "vocabulary": "口语化为主，避免学术词；**钱必须折算人民币**给个参考（按当时汇率，大概数字即可）；距离用公里，温度用摄氏度；专有名词第一次出现一句话解释",
      "verbal_tics": ["你看", "听我说", "在 X 国这边", "这一对比", "咱中国人看着", "你别说"],
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
      "topic_discovery": {
        "youtube_queries": [
          "Vietnam Ho Chi Minh daily life vlog",
          "Mexico City daily life cost of living",
          "Portugal Lisbon expat daily vlog",
          "Argentina Buenos Aires daily life",
          "Kazakhstan Almaty daily routine",
          "Egypt Cairo daily life vlog",
          "Indonesia Bali daily routine expat",
          "Turkey Istanbul cost of living vlog",
          "Brazil Sao Paulo daily routine",
          "Thailand Bangkok daily life vlog",
          "Philippines Manila salary breakdown",
          "Australia Sydney cost of living daily"
        ],
        "exclude_keywords": [
          "shorts only", "TikTok compilation", "reaction video"
        ],
        "max_picks": 8
      }
    },
    "topic_generation_prompt": "你为一个面向中文受众的「环球生活观察」频道选题。候选话题应当聚焦最近 1-2 周内 YouTube 上的海外日常 vlog（任何国家都行，不限于日本和发达国家），重点放在能引起中国观众对比兴趣的内容：物价、工资、习俗、住房、餐饮、上下班。规避高门槛专业话题。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL，**主打中国观众视角的对比和指认**。8-12 个 shot，每个 shot 一句中文（25-40 字）配源视频画面。三个对比框可以反复用：(1) 价格→折算人民币给个对比，(2) 工资→换算成「一小时能买什么」的购买力对照，(3) 习俗→「咱中国人看着...」加吐槽或感叹。亲切口语、verbal_tics 用得自然，钱有具体数字时一定要给。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
