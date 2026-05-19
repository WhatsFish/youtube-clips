-- Ninth Profile: AI 深度 (ai-deep-cn).
-- Producer 模式。**专攻 AI 题材**——AI 风云人物 / 先进 AI 技术 / 重要
-- AI 事件三轴。单视频聚焦一个角度（人物深度 / 技术拆解 / 事件分析），
-- 频道整体不偏科。
--
-- 这是 archival 工具链的主用频道：Jensen / Sam Altman / Demis Hassabis
-- / 王兴兴 / Liang Wenfeng（梁文锋）的 archival 影像在 YouTube / B 站
-- 都有（GTC keynote、国会作证、TED 演讲、采访录像），agent 通过
-- search_*_archival + localize_in_video 真实剪辑这些片段，比 AI 生成
-- 假视频或 stock 通用画面 quality 高一档。
--
-- 题材边界：
--   ✓ 人物：Jensen Huang / Sam Altman / Demis / Dario / 马斯克 / Yann LeCun
--     / 王兴兴 / 梁文锋 / 杨植麟 等
--   ✓ 技术：Blackwell / B200 / DeepSeek V3-MoE / GPT-5 / Gemini 3 /
--     Claude / Sora / 具身智能 / RAG / 推理优化 等
--   ✓ 事件：GTC / OpenAI 内乱 / AI 立法听证 / DeepSeek 发布 / AI 大模型
--     编码竞赛 / 苹果 AI 战略 / 中美 AI 监管博弈 等
--   ✗ 应用层 / 操作教程（不是本频道定位）
--   ✗ AI 工具评测（太短平快）
--
-- Voice：Yunze（中年沉稳）配深度内容气质；rate 6 偏慢、留思考空间。
-- 2026-05-19 上线，配套 archival MVP（PR 1-4）首发频道。
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-ai-deep-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'ai-deep-cn',
  'AI 深度 — producer 模式，命题创作，专攻 AI 三轴（风云人物 / 先进技术 / 重要事件）。每条视频聚焦一个角度，archival 工具拉真实演讲 / 发布会 / 访谈剪进画面。深度感讲述者气质。',
  '{
    "source": {
      "platforms": ["doubao", "pexels", "archival-youtube", "archival-bilibili"],
      "language": null,
      "content_hints": []
    },
    "output": {
      "platforms": ["bilibili_long"],
      "language": "zh",
      "tts_voice": "zh-CN-YunzeNeural",
      "tts_rate_pct": 6,
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
      "channel_position": "中文 AI 深度频道。专讲全球 AI 三轴：**(1) 风云人物**（Jensen Huang / Sam Altman / Demis / Dario / 马斯克 / Yann LeCun / 王兴兴 / 梁文锋 / 杨植麟 等）**(2) 先进技术**（Blackwell / B200 / DeepSeek V3-MoE / GPT-5 / Sora / 具身智能 / 推理优化 等）**(3) 重要事件**（GTC / OpenAI 内乱 / AI 立法 / DeepSeek 发布 / 中美 AI 监管博弈 等）。每条视频**聚焦一个具体角度**——人物深度 / 技术拆解 / 事件分析，不做泛泛综述。**用真实存档画面**（archival 工具）支撑论述，比 AI 生成假视频可信度高一档",
      "tone": "**深度讲述者气质**——理性 + 沉稳 + 带技术分量，但不端架子、不背书、不堆术语。像一位读过文献、看过 keynote、跟过几轮 AI 周期的朋友跟你慢慢说一件值得讲的事。**重视事实 + 因果 + 时间线**——告诉观众「这事是怎么发生的」「为什么重要」「指向哪里」。**绝不要**「答案扎心」「细思极恐」「炸裂」「硬核」这类爆款词。Jensen 不叫「老黄」、Sam Altman 不叫「奥特曼」——用全名或姓",
      "vocabulary": "中文为主，AI 专有名词保留英文（Blackwell / Transformer / MoE / RLHF / attention）；通识术语第一次出现简单解释一句；公司名 / 产品代号第一次出现给一句背景（「Hopper 是英伟达 2022 年发布的上一代数据中心 GPU 架构」）。**不编具体数字**——参数量 / 训练成本 / 估值，不确定就用「公开估算」「行业披露」",
      "verbal_tics": ["回到", "更准确地说", "再往下一层", "值得注意的是", "归根结底", "退一步看"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "重磅",
        "你绝对想不到",
        "细思极恐",
        "答案扎心",
        "炸裂",
        "硬核",
        "震惊",
        "老黄",
        "奥特曼"
      ],
      "must_include_disclaimer": false,
      "style_exemplars": {
        "ref_bvids": ["BV1AbwSzeEKD", "BV1a5QRYCE5j"]
      },
      "video_format": {
        "depth_mode": "deep",
        "target_duration_min": "5-8",
        "outline_points": "8-12",
        "shots_per_video": "16-22",
        "pacing": "dense",
        "inter_shot_pause_sec": 0.0,
        "explain_unfamiliar_concepts": true,
        "directive": "ai-deep 是优质深度频道：每个论点都要展开（事实/逻辑/例子），不能直接抛结论；非通识 AI 概念第一次出现先解释再展开；视频偏长（5-8 min），所以**节奏必须紧凑**，shot 之间几乎不留 pause。**archival 优先**：人物 / 演讲 / 发布会 / 重大事件画面**全部走 archival** 拉真实视频片段，不要用 person 静图代替能动起来的现场。"
      },
      "topic_discovery": {
        "feed_ids": ["36kr_latest", "zhihu_hot"],
        "include_keywords": [
          "AI", "GPT", "OpenAI", "Anthropic", "Claude", "Gemini", "DeepSeek",
          "黄仁勋", "Sam Altman", "Musk", "马斯克", "梁文锋",
          "Blackwell", "Hopper", "B200", "H200",
          "大模型", "推理", "MoE", "transformer", "RAG",
          "智能体", "agent", "AGI", "ASI",
          "英伟达", "NVIDIA", "微软", "Microsoft", "苹果", "Apple",
          "字节", "百度", "阿里", "腾讯", "智谱", "Kimi", "百川"
        ],
        "exclude_keywords": [
          "明星", "综艺", "饭圈", "电竞", "动漫",
          "彩票", "美妆", "穿搭", "宠物"
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
    "topic_generation_prompt": "你为一个面向中文受众的「AI 深度」频道选题。**频道三轴**：(1) AI 风云人物（Jensen / Sam Altman / Demis / 马斯克 / 王兴兴 / 梁文锋 等）(2) 先进 AI 技术（Blackwell / DeepSeek V3 / GPT-5 / Sora / 推理优化 / 具身智能 等）(3) 重要事件（GTC / OpenAI 内乱 / AI 立法 / 中美博弈 等）。**单条聚焦一个具体角度**——避免「2026 年 AI 十大事件」清单体。**重视深度 + 因果 + 时间线**——把事件放在更大背景里讲，而不是单点新闻通报。规避：纯应用教程、AI 工具评测、纯炒作 / FOMO 内容。**每条都要有可深挖的「为什么」**。每次产出 5-10 个候选 topic，每个含中文标题 + 描述 + 角度。",
    "edit_style_prompt": "你写命题创作 narration：**深度讲述者气质**，理性 + 沉稳 + 带技术分量。16-22 个 shot（深度模式），每 shot 30-45 字。论点驱动结构（thesis → evidence → counter → takeaway），不是事件流水账。**优先用 archival 工具拉真实演讲 / 发布会画面**做证据支撑——比 person 静图 + AI 假视频强一档。AI 专有名词第一次出现解释一句。不编具体数字，不上爆款腔。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
