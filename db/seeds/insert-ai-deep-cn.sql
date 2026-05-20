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
      "channel_position": "中文 AI 深度频道。专讲全球 AI 三轴：**(1) 风云人物**（Jensen Huang / Sam Altman / Demis / Dario / 马斯克 / Yann LeCun / 王兴兴 / 梁文锋 / 杨植麟 等）**(2) 先进技术**（Blackwell / B200 / DeepSeek V3-MoE / GPT-5 / Sora / 具身智能 / 推理优化 等）**(3) 重要事件**（GTC / OpenAI 内乱 / AI 立法 / DeepSeek 发布 / 中美 AI 监管博弈 等）。每条视频**聚焦一个具体问题或事件**——人物动作 / 技术细节 / 事件经过，不做泛泛综述。**多源呈现 + 留思考**为基调，不站队、不下硬结论；用真实存档画面（archival 工具）支撑事实陈述，比 AI 生成假视频可信度高一档",
      "tone": "**深度讲述者气质**——理性 + 沉稳 + 带技术分量，但不端架子、不背书、不堆术语。像一位读过文献、看过 keynote、跟过几轮 AI 周期的朋友跟你慢慢说一件值得讲的事。**重视事实 + 来源 + 多视角**——告诉观众「这事是怎么发生的」「不同的人怎么看」「还有哪些没定论的地方」。**关键约束**：不擅自下结论、不替当事人推测动机（『X 真正想要的是 Y』这种），除非有当事人原话 / 多方报道支撑。证据不够就**陈述事实、留问题给观众**，不要硬抛论点；想抛论点就**至少给 2 个独立来源**（不同媒体 / 不同立场）。**绝不要**「答案扎心」「细思极恐」「炸裂」「硬核」这类爆款词。Jensen 不叫「老黄」、Sam Altman 不叫「奥特曼」——用全名或姓",
      "vocabulary": "中文为主，AI 专有名词保留英文（Blackwell / Transformer / MoE / RLHF / attention）；通识术语第一次出现简单解释一句；公司名 / 产品代号第一次出现给一句背景（「Hopper 是英伟达 2022 年发布的上一代数据中心 GPU 架构」）。**不编具体数字**——参数量 / 训练成本 / 估值，不确定就用「公开估算」「行业披露」",
      "verbal_tics": ["回到", "更准确地说", "再往下一层", "值得注意的是", "另一种解读", "如果换个视角", "目前没有公开证据表明"],
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
      "outro": {
        "text_line1_zh": "深入了解 AI 浪潮的人物 / 技术 / 事件",
        "text_line2_zh": "点赞关注，下条见",
        "background_prompt_en": "abstract minimalist cinematic background, deep navy blue gradient transitioning to warm amber on the horizon, subtle soft light particles floating, very dark and elegant, no text no faces no objects, premium tech documentary aesthetic, ultra wide composition",
        "duration_sec": 5
      },
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
        "directive": "ai-deep 是优质深度频道：每个论点都要展开（事实/逻辑/例子）+ **多源支撑**——同一事件引 2+ 个不同来源（不同媒体/不同立场），尤其涉及当事人动机或争议性结论时；如果只有单一来源，**降级成事实陈述**或换问题问观众。非通识 AI 概念第一次出现先解释再展开。视频偏长（5-8 min），**节奏紧凑**但不仓促收尾——结尾不要总结判决，提开放问题或并列分歧即可。**archival 优先级最高（强约束）**：只要画面要出现**真实人物 OR 跟话题主题相关**，**哪怕不完全对应**也优先 archival——loose connection 也算，比如讲马斯克任何 shot 都可以用马斯克在某场合的真实画面、讲 OpenAI 某事件可以用 OpenAI 任何官方发布会画面。**质量门槛要放宽**：完整官方源最好，但搬运 / 解说 / 配图视频如果**包含主体真实镜头**也用。**只有完全无法跟主题 / 人物 / 场景产生任何联系的抽象概念（数学符号 / 模糊隐喻）才退到 image**。理想比例：archival ≥ 50% 的 shot。"
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
    "topic_generation_prompt": "你为一个面向中文受众的「AI 深度」频道选题。**频道三轴**：(1) AI 风云人物（Jensen / Sam Altman / Demis / 马斯克 / 王兴兴 / 梁文锋 等）(2) 先进 AI 技术（Blackwell / DeepSeek V3 / GPT-5 / Sora / 推理优化 / 具身智能 等）(3) 重要事件（GTC / OpenAI 内乱 / AI 立法 / 中美博弈 等）。**单条聚焦一个具体问题或事件**——避免「2026 年 AI 十大事件」清单体。**suggested_angle 应当是一个待澄清的事实或值得思考的问题**（『为什么...』『...到底意味着什么』『...的真相是什么』），而不是一个已经成型的结论（避免『...证明了 X』『...本质上是 Y』这种）。**重视事实 + 因果 + 来源**——把事件放在更大背景里讲，引用具体材料 / 报道 / 当事人原话。规避：纯应用教程、AI 工具评测、纯炒作 / FOMO 内容。每次产出 5-10 个候选 topic，每个含中文标题 + 描述 + 角度。",
    "edit_style_prompt": "你写命题创作 narration：**深度讲述者气质 + 多源呈现 + 留思考**。16-22 个 shot（深度模式），每 shot 30-45 字。**结构原则**：事实陈述 → 多方观点 → 待思考问题。**不抛硬结论**——除非有当事人原话或多方报道支撑，否则一律用『目前没有公开证据表明...』『有人这么看 / 另一种观点是...』『还无定论』。**绝不替当事人推测动机**（『X 真正想要的是 Y』这种是失败模式）。如果一段证据不够支撑你想抛的论点，**降级成事实陈述**或干脆删掉，宁缺勿凑。**收尾不要总结判决**——提一个观众值得思考的开放问题或并列摆出几方分歧即可。**画面优先级（强约束）**：archival >> 其它一切。只要画面要出现真实人物 OR 跟话题主题 / 公司 / 事件相关，**哪怕不完全对应**也优先 archival，loose connection 也算（讲马斯克某事用马斯克任何场合真实画面；讲 OpenAI 用任何 OpenAI 发布会画面）。质量门槛放宽：官方源最好，搬运 / 解说 / 配图视频如果包含主体真实镜头也用。**理想 archival ≥ 50% 的 shot**。AI 专有名词第一次出现解释一句。不编具体数字，不上爆款腔。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
