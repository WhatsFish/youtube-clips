# HTML 自创素材设计系统（agent 必读）

操作员定调：**每条 shot 都自己写一段 HTML**，不复用 template，但**必须**继承 `_styles.css` 的设计系统。`examples/` 下的 8 个文件**只是风格参考**，不是模板。读它们学风格 + 复用 class 命名规约 + 偷动画时序，**不要 1:1 复制**。

---

## 视觉规则（不可妥协）

### 配色
- **永远不用冷蓝灰** —— 不准出现 `#0b1220 / #111c2f / #3b82f6 / #ef4444` 这类冷色调
- 用 `var(--…)`，不准硬编码 hex 色值。所有 token 在 `_styles.css`
- 底色：`var(--bg-base)`（默认 linear gradient 已在 body 里设了）；需要聚焦时给某个区域用 radial 配 `var(--bg-soft)` 中心
- 主体字：`var(--text-default)` / `var(--text-strong)`
- 次要 / 标签 / kicker：`var(--text-muted)`
- 强调色三档：`var(--accent-primary)` 珊瑚橙 `#ff8a4c`（主），`var(--accent-secondary)` 芥末金 `#ffd166`（次），`var(--accent-tertiary)` 赤陶 `#e76f51`（第三/中性对比）
- 卡片 / 装饰背景：`var(--card-bg)`；分隔线：`var(--border-soft)` / `var(--border-med)`

### 排版
- 字体只用 `var(--font-stack)`（Noto Sans SC，中英文都覆盖）。**不要引入新字体**
- 标题 ≤ 50px（`var(--fs-title)`），副 kicker 22px uppercase + 字距 `4px`，正文 19px
- 大数字 130-220px 给 stat 类场景；数字必须 `font-variant-numeric: tabular-nums` + 负 letter-spacing
- **绝不用「综上所述 / 答案扎心 / 你绝对想不到 / 细思极恐 / 炸裂 / 硬核」这类爆款腔**

### 布局
- 默认 padding `var(--pad-edge)`（56px 80px，已在 `.stage` 里），如果做 quote/stat 这种居中类，可以加 `align-items: center; justify-content: center`
- 卡片：`var(--card-bg)` 底 + `var(--border-soft)` 边 + `border-radius: 14px`
- 强调色装饰条 48x4px 圆角矩形

---

## 动画规则

### 节奏（**操作员强调**）
- **慢 + 留白**。CSS 过渡 1.0-1.6s，stagger 1.0-1.2s
- 整段动画 **5-7s 完成**，pipeline 渲染时长按 narration TTS 自适应，最后总留 1-3s 静止
- **绝不在 1s 内 burst** 把所有内容同时 fade in——观众没时间看
- 三档以上元素要顺序揭示（kicker → title → 内容 stagger）

### Token（用这些，不要写死时长）
- `var(--t-fast)` 900ms —— 装饰性元素（箭头、VS chip）
- `var(--t-mid)` 1100ms —— 大多数 fade-in
- `var(--t-slow)` 1300ms —— 标题 / 大数字 reveal
- `var(--t-draw)` 3200ms —— 长线条 / 轴线绘制
- `var(--stagger)` 1100ms —— 顺序 bullet/event 之间的默认延迟

### 触发协议（**硬性**）
- 页面**必须** expose `window.startAnimation = () => { ... }`
- 通过给某个根元素加 `.playing` class 触发；CSS 写 `.playing .xxx { opacity: 1; ... }` 来驱动
- 不要 autoplay / 不要用 `setTimeout` 启动 —— pipeline 控时序

### HTML 结构契约
- 单个 `<body>` 容器 1280x720（`_styles.css` 已经处理）
- 根 stage `<div class="stage" id="stage">`
- 内部按需自己设计，没有强制 DOM 结构

---

## 写一支新 HTML 的步骤

1. **判断这个 shot 该不该用 HTML**（见下文「不要用 html 的场景」）。能用 archival / image 表达就别用 html
2. **选一个 `examples/` 文件作风格参考**——找语义最接近的（数据对比看 `bar-chart.html`，多论点看 `bullet-ppt.html`，时间脉络看 `timeline.html`，金句看 `quote-card.html`，单数字看 `stat-hero.html`，趋势看 `multi-line-chart.html`，流程看 `process-flow.html`，对比 ticker 看 `counter-comparison.html`）
3. **从骨架开始写**：`<link rel="stylesheet" href="_styles.css">` + `.stage` + 内容 + `<script>` 暴露 `window.startAnimation()`
4. **只用 CSS var**，没有 hex 色值
5. **节奏检查**：所有 stagger ≥ 1000ms，整体动画 ≤ 7s 完成

---

## 不要用 html 的场景

`asset_strategy="html"` 是结构化信息 / 数据 / 比较的最高质量自创素材，**但**：
- 画面需要真实人物 / 真实事件镜头 → `archival`（YT/B站剪）
- 真实地点风貌 → `archival` 或 `pexels`
- 抽象隐喻、纯静物、招牌、文档特写 → `image` (CogView)
- 中文具体场景 + 需要真实运动 → `ai` (Doubao)
- 任何「**没有数据 / 没有比较 / 没有时间结构 / 没有列表 / 没有金句**」的场景 → 别用 html

---

## 改设计系统的流程

操作员说要调整时：
1. 改 `_styles.css` 里的 token（颜色 / 时长）
2. 重渲染若干 `examples/` 验证
3. 操作员看了 OK → 改这个 DESIGN.md 把新规则写进规则区
