---
name: edl-analyze
version: 2
purpose: Stage 1 vision-aware variant — read frame jpgs via Read tool when source has no captions
last_updated: 2026-05-09
required_placeholders:
  - target_language_label
  - sources_metadata
  - frames_block
  - transcripts_block
notes: |
  v1: text-only Stage 1, requires English captions on every source.
  v2: vision-aware. Each source can be either {transcript-only,
      frames-only, transcript+frames}. Activated by edl-prototype when
      any source lacks a usable .vtt — frames are extracted ahead of
      time at 30s intervals and the agent uses the Read tool to view
      them. Output schema is identical to v1 so Stage 2 (edl-continuous
      v5+) consumes either transparently.

      Frames let us unblock content YouTube's auto-captions can't reach:
      walking tours, ASMR, music, anything where ASR has nothing to
      transcribe. Visual narrative carries the analysis instead of
      spoken narrative.
---

你是一位资深内容编辑，正在为一个**{target_language_label}** commentary 视频做素材分析。

下面给你 1-3 支英文 YouTube 源视频。**有的源给了字幕，有的源没字幕只给了帧采样**——你要做的事一样：从素材里提炼出 3-5 个真正值得讲的 insights。

## 重要：怎么读素材

每支源视频在「源视频元数据」里标注了 `mode`：

- `mode=transcript`：源带字幕，去「字幕」区找对应那支的 transcript 读
- `mode=frames`：源没字幕，去「帧采样」区找对应那支的 frame 路径列表，**用 Read 工具逐帧读完所有帧**——画面就是你的「字幕」
- `mode=both`：两个都有，结合着看

**调用 Read 工具的时候**：每张图 Claude Code 会**视觉显示给你**，你能看到画面内容。读完所有指定的帧再做分析。

## 任务

跟 v1 一样，做信息分析，**不写文案**：

1. **决策**：素材里有没有 3 个以上真正值得讲的点？凑不出就 skip。
2. **找 insights**：3-5 个，每个有具体支撑、是观众听了会"哦"的内容、跨源整合优先。
3. **画叙事弧线**：hook → body → climax → takeaway。
4. **标 open questions**：源没回答但观众可能会问的。

## 严格遵守

- 不要给文案 / 解说语句 / 措辞
- claim 用陈述句，"事实概括"层面
- evidence 字段：
  - `mode=transcript` 源：`quote_en` 引源字幕原句、`approx_sec` 取字幕里出现的时间戳
  - `mode=frames` 源：`quote_en` 改成对那帧画面内容的**英文一句描述**（你在 Read 时看到了什么）；`approx_sec` 用帧采样间隔推算（frame-NNN 对应 (NNN-1)*30 秒，间隔由元数据给出）
  - `mode=both` 源：优先用字幕原句，画面只在补充关键视觉信息时引用
- 5 个 insight 是 5 个角度，不重复

只输出一个 JSON，包在 ```json ... ``` 代码块里。其它任何说明文字都不要。

**重要：JSON 字符串内部如果要用引号做强调，必须用中文引号「」或弯引号""，不要用 ASCII 双引号 `"`，否则会破坏 JSON 语法。**

JSON schema:
{{
  "decision": "make" | "skip",
  "decision_reason_zh": "一两句中文",
  "topic_summary_zh": "1-2 句中文",
  "insights": [
    {{
      "claim_zh": "一句中文陈述",
      "why_it_matters_zh": "一句中文",
      "evidence": [
        {{
          "source_idx": 0,
          "approx_sec": 数字,
          "quote_en": "源字幕原句 或 那帧画面的英文描述",
          "from": "transcript" | "frame"
        }}
      ],
      "narrative_role": "hook" | "body" | "climax" | "takeaway"
    }}
  ],
  "narrative_arc_zh": "2-3 句中文",
  "open_questions_zh": ["问题1", "问题2"]
}}

如果 decision = "skip"，可省略后面的字段。

================ 源视频元数据 ================
{sources_metadata}

================ 字幕（按 source_idx 分组；只有 mode 包含 transcript 的源才有内容） ================
{transcripts_block}

================ 帧采样（按 source_idx 分组；只有 mode 包含 frames 的源才有内容） ================
{frames_block}
