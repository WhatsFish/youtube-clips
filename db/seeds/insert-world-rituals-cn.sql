-- Eighth Profile: 远方的仪式 (world-rituals-cn).
-- Commentary 模式。专门讲全球各地的**仪式 / 习俗 / 礼俗** —— 婚丧嫁娶、
-- 成人礼、节庆、宗教仪式、食物禁忌、社群规则。区别于 curiosity-cn 的
-- 「奇闻冷知识」散点小知识（语言学 / 动物 / 历史细节），这个号更像
-- 人类学纪录片切片——单条围绕一种具体仪式 / 习俗展开。
--
-- 来源最佳产区：撒哈拉以南非洲、东南亚（印尼/菲律宾/巴新）、中南美
-- （亚马逊 / 玻利维亚 / 墨西哥）、大洋洲（瓦努阿图 / 所罗门）、南亚 /
-- 中东 / 中亚特殊礼俗。视觉浓密的纪录片型源最适合。
--
-- 关键 tone 约束：**平视 + 好奇 + 解释 + 敬畏**。绝对不要"哈哈他们好
-- 原始""这也太离谱了"这种猎奇 / 评判 / 西方中心化视角——民俗题材最
-- 容易翻车成这种。所有不熟悉的做法都假定有其逻辑，解释清楚为什么。
--
-- 起源：印尼"换 10 头猪做新娘"那条在 curiosity-cn 数据好，操作员意识
-- 到这类内容值得单开一个号深挖。2026-05-19 上线。
--
-- Apply:
--   docker exec -i -e PGPASSWORD="$YOUTUBE_CLIPS_PG_PASSWORD" \
--     traffic-monitor-db-1 \
--     psql -h localhost -U youtube_clips -d youtube_clips \
--     < db/seeds/insert-world-rituals-cn.sql

INSERT INTO profiles (name, description, config_jsonb, active)
VALUES (
  'world-rituals-cn',
  '远方的仪式 — commentary 模式，专讲全球各地的婚丧、成人礼、节庆、宗教、食物禁忌等具体仪式 / 习俗。平视讲述、不猎奇、不评判、解释为什么。东南亚 / 非洲 / 中南美 / 大洋洲为主要产区。',
  '{
    "source": {
      "platforms": ["youtube"],
      "language": "en",
      "content_hints": [
        "tribe", "tribal", "ritual", "ceremony", "tradition", "custom",
        "wedding tradition", "bride price", "dowry", "marriage custom",
        "coming of age", "initiation", "rite of passage",
        "funeral custom", "death ritual",
        "festival", "religious ceremony",
        "Indonesia", "Papua", "Philippines",
        "Kenya", "Tanzania", "Ethiopia", "Madagascar", "Namibia",
        "Amazon", "Bolivia", "Mexico",
        "Vanuatu", "Solomon", "Polynesia",
        "Bhutan", "Nepal", "Pakistan"
      ]
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
      "channel_position": "面向中文受众的「远方的仪式」频道——专讲全球各地的具体仪式与习俗：婚礼、葬礼、成人礼、节庆、宗教仪式、食物禁忌、社群规则。**平视 + 好奇 + 解释 + 带点敬畏**为基调，不猎奇、不评判、不上价值观、不站在外面看。让中文观众理解一种他不熟悉的人是怎么过日子、为什么这么过的",
      "tone": "讲述者气质，平视 + 好奇 + 带敬畏。像一个见过世面、读过书、又愿意陪你慢慢解释的朋友——不夸张、不戏剧化、不端着、不卖弄。**绝对不要**「哈哈他们好原始」「这也太离谱了」「细思极恐」这类猎奇 / 评判 / 哗众取宠的语气。所有不熟悉的做法都假定有其逻辑，**解释清楚为什么**——比如「换 10 头猪」不是落后，是当地经济结构 + 家庭责任 + 社群信用体系的复合表达",
      "vocabulary": "口语化但有信息密度，专有名词（地名 / 民族名 / 仪式名）第一次出现一句话解释清楚；不熟悉的食物 / 物件给个直观对照；钱出现时换算人民币给个直觉。**通识表达**，不编具体数字，不确定的用「公开资料显示」「人类学家估算」",
      "verbal_tics": ["你看", "这事其实", "更有意思的是", "再深一层", "原来", "听说过吗"],
      "forbidden_phrases": [
        "综上所述",
        "本期内容",
        "深度剖析",
        "今天我们要讲",
        "大家好欢迎收看",
        "让我们一起",
        "重磅",
        "哈哈",
        "细思极恐",
        "你绝对想不到",
        "答案扎心",
        "震惊",
        "炸裂",
        "硬核",
        "落后",
        "原始",
        "野蛮",
        "愚昧",
        "迷信"
      ],
      "must_include_disclaimer": false,
      "topic_discovery": {
        "youtube_queries": [
          "tribal wedding ceremony Africa",
          "bride price dowry tradition documentary",
          "coming of age ritual tribe",
          "Maasai ceremony Kenya tradition",
          "Indonesia tribal wedding custom",
          "Papua New Guinea tribe ritual",
          "Ethiopian Hamar bull jumping ceremony",
          "Madagascar famadihana turning bones",
          "Bolivia Aymara wedding ceremony",
          "Amazon tribe daily life ritual",
          "Bhutan Nepal Buddhist ceremony tradition",
          "Vanuatu land diving ritual",
          "Mexico Day of the Dead tradition deep",
          "Mongolia nomadic wedding ceremony",
          "Tibet sky burial death ritual",
          "Philippines Igorot tribe ceremony",
          "Namibia Himba tribe daily ritual",
          "India tribal coming of age",
          "funeral custom unusual culture documentary",
          "remote village daily life ritual"
        ],
        "exclude_keywords": [
          "shorts only", "TikTok compilation", "reaction video",
          "you wont believe", "shocking", "creepy", "horror",
          "crazy", "weirdest", "ranked", "10 most"
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
    "topic_generation_prompt": "你为一个面向中文受众的「远方的仪式」频道选题。**频道定位**：讲全球各地的具体仪式与习俗——婚礼、葬礼、成人礼、节庆、宗教仪式、食物禁忌、社群规则。**单条围绕一种具体仪式 / 习俗展开**，不做「X 国十大奇闻」清单体。**关键要求**：(a) 平视讲述、不猎奇、不评判，所有不熟悉的做法都假定有其逻辑要解释「为什么」（经济结构、家庭责任、信用体系、自然环境、历史脉络）；(b) 国家务必多样化，每批至少覆盖 3 个不同大洲（撒哈拉以南非洲 / 东南亚 / 中南美 / 大洋洲 / 南亚 / 中东 / 中亚都欢迎，避免连续欧洲北美）；(c) 优先视觉浓密的纪录片型源（婚礼现场 / 仪式现场 / 部落日常），避免单口讲述。规避：纯娱乐八卦、新闻时政、当地负面新闻 / 灾难报道。每次产出 5-10 个候选 topic，每个含中文标题、一段中文描述和 3-5 个英文搜索关键词。",
    "edit_style_prompt": "你写 continuous commentary 风格的 EDL，**主调是「带观众走进 + 解释 + 敬畏感叹」**。9-13 个 shot，每个 shot 一句中文（25-45 字）配源视频画面。**视角选择**：(a) 描述并翻译画面里在发生什么（这是什么仪式 / 什么物件 / 什么动作），(b) 解释为什么——经济结构 / 家庭责任 / 信用体系 / 自然环境 / 历史脉络，(c) 适度的敬畏感叹（不夸张），(d) 必要时给中国观众一个直观对照（不强求，不硬掰）。**不评判、不猎奇、不站在外面看**。允许 1-2 个静音 shot 让画面 + bgm 自己说话（看到震撼场面时）。亲切但有分量的口语，verbal_tics 自然嵌入。原音 0.10，中文 1.6 倍。"
  }'::jsonb,
  TRUE
)
ON CONFLICT (name) DO UPDATE SET
  description = EXCLUDED.description,
  config_jsonb = EXCLUDED.config_jsonb,
  updated_at = NOW();
