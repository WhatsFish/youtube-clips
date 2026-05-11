# Local 中文素材库设计（B'-1, P2, 归档于 2026-05-11）

**状态**：design finalized，实现归为 P2 todo。原本是 phase B 第 2 项，操作员评估后判断 scope 大、且解决的不是 blocker（只是 Pexels-foreign-people 违和这种质量问题），暂缓。

**问题域**：producer 模式给中国 topic 配素材时，Pexels 经常返回明显外国人的画面，违和。当前 fallback 是 Doubao text-to-video（~¥1-2/clip），跑量起来成本上升快。本设计建一个**本地中文素材库**，让中国场景从库里取（¥0），Doubao 作为兜底而非默认。

---

## 关键设计决策（已 finalize）

1. **两层目录 tag**：`/video/youtube-clips/assets/local/<scene>/<mood>/<id>.mp4`，例如 `street/night/`, `factory/empty/`, `family/dinner/`。filesystem-first，无 DB，操作员 `ls` 即可看清覆盖。
2. **种子库 AI 兜底起步**：30 个核心 tag × 1 clip × ¥1 ≈ ¥30 一次性，之后用真实素材替换。
3. **MVP Web /assets 一起做**：覆盖表 + miss 排序 + needs_review 区块。
4. **长视频自动入档**：用 pyscenedetect 切镜头，Claude vision 分类落 tag。
5. **复核走 Web 缩略图 + 一键按钮**。

---

## 详细架构

### 1. 目录结构

```
/video/youtube-clips/assets/
├── _inbox/                 # 操作员丢长视频进来
│   └── long-vlog.mp4
├── local/                  # 入档后的可用 clip（dispatcher 读这里）
│   ├── street/
│   │   ├── night/
│   │   │   ├── 001.mp4
│   │   │   └── 001.json    # sidecar
│   │   └── day/
│   ├── factory/
│   │   ├── workers/
│   │   └── empty/
│   └── family/
│       └── dinner/
└── manifest.json           # 自动生成，操作员可补 description/wishlist
```

### 2. Sidecar JSON schema

```json
{
  "duration_sec": 12.4,
  "resolution": "1920x1080",
  "codec": "h264",
  "has_audio": true,                          // 渲染时强制静音
  "source_long_video": "long-vlog.mp4",       // 来自哪条长视频（auto-classified 时填）
  "source_t0_sec": 142.0,                     // 在原视频里的起始时间
  "auto_classified": true,
  "confidence": 0.85,                         // < 0.7 触发 needs_review
  "alt_tags": ["street/day"],                 // 第二高分 tag（参考）
  "needs_review": false,
  "source": "BV1xx (CC BY)",                  // 可选，操作员或 ingest 脚本填
  "notes": "雨夜版",                            // 可选
  "added_at": "2026-05-11T20:00:00Z"
}
```

### 3. Tag manifest（自动 + 人工混合）

```json
{
  "tags": {
    "street/night": {
      "description": "中国小城/二三线 夜晚街景",
      "use_cases": ["乡村空心", "深夜独行"],
      "min_clips": 5,
      "current_clips": 3,
      "miss_count_30d": 7,
      "wishlist": ["雨夜", "雪天"]
    }
  }
}
```

scanner 自动更新 `current_clips` / `miss_count_30d`；操作员手动维护 `description / use_cases / min_clips / wishlist`。

### 4. Stage 2 prompt 注入可用 tag

producer-script.v1.md 渲染时自动加：

```
本地素材库可用 tag（asset_strategy="local" 时用，dedup 自动处理）：
  - street/night: 中国街景，夜景，小城（5 clips）
  - factory/workers: 工厂车间作业（4 clips）
  - ...
visual_brief 能套上 tag → emit asset_strategy="local" + local_tag="<name>"。
套不上 → 才考虑 pexels（抽象场景）或 ai（中国具体人物 / 场景）。
```

shot JSON 新增 `local_tag` 字段。

### 5. Dispatcher 决策

```python
def _acquire_one_local(shot, run_used: set[str], manifest):
    tag = shot["local_tag"]
    pool = manifest.tags.get(tag, {}).clips - run_used
    if not pool:
        emit_miss(run_id, tag, shot["visual_brief_en"], fallback="ai")
        return _acquire_one_ai(shot, ...)
    clip = random.choice(list(pool))
    run_used.add(clip.id)
    return {"video_id": f"local-{clip.id}", "path": clip.path, ...}
```

### 6. asset_misses 表

```sql
CREATE TABLE asset_misses (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT REFERENCES runs(id),
  shot_idx INT,
  requested_tag TEXT,
  visual_brief_en TEXT,
  fallback_used TEXT CHECK (fallback_used IN ('pexels','ai','skip')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX asset_misses_tag_ts ON asset_misses (requested_tag, created_at DESC);
```

### 7. 长视频入档子系统

```
scripts/ingest-long-video.py _inbox/long.mp4
  a. pyscenedetect ContentDetector(threshold=27) 切镜头
  b. 抛弃 <3s 或 >30s 的段
  c. 每段提取中间帧 → /tmp/seg_NN.jpg
  d. 调 Claude vision (prompts/asset-classify.v1.md):
     - 输入: tag 菜单（含 description）+ 帧图片
     - 输出: {tag, confidence, alt_tags, reasoning}
  e. confidence >= 0.7 → 落到 /local/<tag>/，needs_review=false
  f. confidence < 0.7  → 落到 /local/<tag>/，needs_review=true
  g. tag="discard" → 整段丢弃
  h. 写中间帧 jpg 到 sidecar 旁（供 web 缩略图）
  i. 写 sidecar.json，更新 manifest
```

**成本**：10min 视频 → 30-50 段 → ~$0.10-0.15 / 条。

### 8. 复核 Web UX

`/assets` 页结构：
- 顶部：覆盖表（tag × current_clips × min_clips × miss_count_30d）。按 miss_count 倒序。
- 中部：**需要复核**区块（needs_review=true 的 clip 缩略图网格）
  - 每张缩略图下：当前 tag + alt_tags + confidence
  - 三个按钮：`✓ 保留` / `→ 改 tag(下拉)` / `🗑 删除`
  - 后端 API: `POST /youtube-clips/api/assets/<clip-id>/confirm | retag | delete`
- 底部：wishlist（操作员手写的"还想加什么"）

### 9. 渲染时取段

dispatcher 拿到 `local_tag` → manifest 查 tag → 池中减 run_used → 随机抽 → renderer 把 clip path 当 source path 用（和 Pexels 完全一致）。

### 10. 实现拆分（13 项）

| # | 任务 | 估时 |
|---|---|---|
| 1 | filesystem 结构 + manifest schema | S |
| 2 | `pipeline/local_stock.py`: scanner + tag lookup + per-run dedup | M |
| 3 | `scripts/index-assets.py`: 扫描，生成/更新 manifest | S |
| 4 | `scripts/ingest-long-video.py`: 切 + 分类 + 写 sidecar | L |
| 5 | `prompts/asset-classify.v1.md`: vision 分类 prompt | S |
| 6 | `producer-script.v1.md`: 注入 tag 菜单 + `asset_strategy: "local"` | S |
| 7 | `produce-original.py`: `_acquire_one_local` + miss logging | M |
| 8 | `db/schema.sql`: `asset_misses` 表 | S |
| 9 | `pipeline/events.py`: `emit_miss(...)` helper | S |
| 10 | Web `/assets` 页：覆盖表 + miss 排序 + needs_review + retag/delete API | M |
| 11 | Doubao 兜底种子（30 tag × 1 clip × ¥1 ≈ ¥30）| S |
| 12 | `docs/tag-taxonomy.md`: 初始 tag 列表 + 描述 | S |
| 13 | `pyscenedetect` 装到 venv | S |

总估时：约 2-3 天集中工作。

---

## 临时缓解（在 B'-1 真正实现前）

producer-script.v1.md 加一条更明确的规则：**任何 shot 涉及中国具体人物 → 必须 `asset_strategy: "ai"`，禁止 fallback 到 Pexels**（Pexels 只能配抽象场景）。

这是 30 分钟的 prompt 改动，能立刻让 shanyang-cn 这类中国 topic 视频里不再出现违和的外国人画面。Doubao 成本上升的代价是接受的——等 B'-1 后回落。
