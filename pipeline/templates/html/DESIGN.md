# HTML 自创素材设计系统（agent 必读）

操作员定调：**暖色 + 年轻化 + 现代感 + 一点趣味**。不要 editorial-magazine 的硬端正脸；像 Linear / Notion / Things 那种柔但有锐度的产品视觉。圆角大、强调色饱和、动画微微有弹性、装饰元素可以可爱（小几何块、SVG icon、按比例示意图）。

每条 shot 都自己写一段 HTML，不复用 template，但**必须**继承 `_styles.css` 的设计系统。`examples/` 下的文件**只是风格参考**，不是模板。读它们学风格、偷动画时序模式，**不要 1:1 复制**。

---

## 视觉规则（不可妥协）

### 配色
- **永远不用冷蓝灰** —— 不准出现 `#0b1220 / #111c2f / #3b82f6 / #ef4444` 这类冷色调
- **绝不**硬编码 hex 色值 —— 用 `var(--…)`。所有 token 在 `_styles.css`
- 底色：`var(--bg-base)` 默认（已加 subtle radial 暖色光斑提味）；需要更聚焦的页面可以 `var(--bg-elev)` 或 radial 配 `var(--bg-soft)` 中心
- 主体字：`var(--text-default)` / `var(--text-strong)`
- 次要 / 标签 / kicker：`var(--text-muted)`
- 强调色五档：
  - `var(--accent-primary)` 珊瑚橙 `#ff8a4c` —— 主强调，默认数字 / 主线
  - `var(--accent-secondary)` 芥末金 `#ffd166` —— 第二系列 / 次要高亮
  - `var(--accent-tertiary)` 赤陶 `#e76f51` —— 第三系列 / 中性对比
  - `var(--accent-pink)` 粉珊瑚 `#ff6b9d` —— **可爱 / 强调一个 outlier**（节制用）
  - `var(--accent-sage)` 鼠尾草绿 `#88c099` —— **温和正面 / 增长项 / 健康指标**
- 卡片：`var(--card-bg)` 默认 / `var(--card-bg-warm)` 暖一点；分隔：`var(--border-soft)` `var(--border-med)`

### 排版
- 字体只用 `var(--font-stack)`（Noto Sans SC）。**不要引入新字体**
- 标题 ≤ 50px（`var(--fs-title)`），副 kicker 22px uppercase + 字距 `var(--letter-kicker)` 4px，正文 19px
- 大数字 130-220px 给 stat 类场景；数字必须 `font-variant-numeric: tabular-nums` + 负 letter-spacing
- **绝不**爆款腔（「综上所述 / 答案扎心 / 你绝对想不到 / 细思极恐 / 炸裂 / 硬核」）

### 形状语言
- 卡片 / 容器圆角：`var(--radius-card)` 20px（不要小于 16px，看着才年轻）
- chip / 小标签：`var(--radius-chip)` 10px
- 圆形 / 胶囊：`var(--radius-pill)` 999px

### 布局 + 字幕安全区（**硬性**）
- 默认 padding 已在 `.stage` 里：top 56, x 80, **bottom 180**
- 视频底部 ~140-180px 是 burn_zh 字幕带，**html 主体内容禁止压到那里**
- `_styles.css` 已经把 .stage 的 padding-bottom 设到 180px，**不要 override**

---

## 动画规则

### 节奏
- **慢 + 留白**。过渡 1.0-1.6s，stagger 1.0-1.2s
- 整段动画 **5-7s 完成**，pipeline 渲染时长按 narration TTS 自适应，最后总留 1-3s 静止
- **绝不在 1s 内 burst** 把所有内容同时 fade in
- 顺序揭示：kicker → title → 内容 stagger

### Token（用这些，不要写死时长）
- `var(--t-fast)` 900ms —— 装饰性元素（箭头、徽标、chip）
- `var(--t-mid)` 1100ms —— 大多数 fade-in
- `var(--t-slow)` 1300ms —— 标题 / 大数字 reveal
- `var(--t-draw)` 3200ms —— 长线条 / 轴线绘制
- `var(--stagger)` 1100ms —— 顺序元素之间默认延迟

### 缓动（**用这些有曲线的，不要光秃秃 `ease`**）
- `var(--ease-snap)` —— 默认，强 settle，cubic-bezier(.2, 1.0, .3, 1)
- `var(--ease-bounce)` —— 轻微 overshoot 有弹性，cubic-bezier(.34, 1.56, .64, 1)。用在「东西从外面飞进来」「数字突然出现」这种有趣的场合
- `var(--ease-draw)` —— 线条 / 轴线绘制

### 触发协议（**硬性**）
- 页面**必须** expose `window.startAnimation = () => { ... }`
- 通过给某个根元素加 `.playing` class 触发；CSS 写 `.playing .xxx { ... }` 来驱动
- 不要 autoplay / 不要用 `setTimeout` 启动

---

## 充分利用 HTML 的可视化能力（**操作员强调**）

html 不是「动画 PPT」。能画示意图就**画示意图**，不要只是把数字列出来。常见做法：

- **按比例几何**：narration 提"车宽 1.95 米 / 车位 2.4 米 / 余量 40 cm"——画两个按比例的矩形（1.95/2.4 = 81%）+ 标注余量 + 动画放大开门弧线。**这比文字列表说服力高一档**
- **流向 / 关系图**：用 SVG 画箭头连接 A → B → C，标注每段的"信息含义"
- **空间演示**：用 absolute positioning + transform 演示物体相对位置 / 大小变化
- **数据 + 图形**：数字配 SVG 柱 / 线 / 圆，不是孤立数字
- **图标化**：用 emoji 或简单 SVG 表达概念（🚗 / 🅿️ / 📈 / 🏭 / 💰）

**判断 trick**：你写完 html 后看一遍——**如果这条 html 拿掉只剩纯文字，narration 信息没丢，那这条 html 写得不够好**。html 要传递文字传不了的信息（比例、空间、相对关系、节奏）。

---

## 写一支新 HTML 的步骤

1. **判断这个 shot 该不该用 HTML**（见 producer prompt 的 ROI 树）——能用 archival / image 表达就别用 html
2. **选一个 `examples/` 文件作风格参考**——找语义最接近的
3. **从骨架开始**：`<link rel="stylesheet" href="_styles.css">` + `.stage` + 内容 + `<script>` 暴露 `window.startAnimation()`
4. **只用 CSS var**，没有 hex 色值
5. **节奏检查**：所有 stagger ≥ 1000ms，整体动画 ≤ 7s 完成
6. **底部禁区检查**：内容不压到底部 180px

---

## 改设计系统的流程

操作员说要调整时：
1. 改 `_styles.css` 里的 token（颜色 / 时长 / 缓动）
2. 重渲染若干 `examples/` 验证
3. 操作员看了 OK → 改这个 DESIGN.md 把新规则写进规则区
