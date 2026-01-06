#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class DocAsPlanWriterResult:
    markdown_text: str
    summary: str = ""
    rag_analysis: Optional[Dict[str, Any]] = None


class DocAsPlanWriterAgent:
    """
    DocAsPlan Writer Agent

    目标：
    - 根据 user_query 对论文 markdown_text（全文）做局部插入/改写
    - 必须返回更新后的全文 markdown_text
    - 除非用户要求，否则不要改动无关章节
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def update_markdown(
        self,
        markdown_text: str,
        user_query: str,
        *,
        doc_id: Optional[str] = None,
        global_style: Optional[Dict[str, Any]] = None,
        rag_key_facts: Optional[List[Dict[str, Any]]] = None,
        existing_rag_analysis: Optional[Dict[str, Any]] = None,
    ) -> DocAsPlanWriterResult:
        # 允许空 markdown：用于“先生成 plan 骨架”的场景
        if markdown_text is None:
            markdown_text = ""
        if not user_query or not str(user_query).strip():
            raise ValueError("user_query 为空")

        prompt = self._build_prompt(
            markdown_text=markdown_text,
            user_query=user_query,
            doc_id=doc_id,
            global_style=global_style,
            rag_key_facts=rag_key_facts or [],
            existing_rag_analysis=existing_rag_analysis,
        )

        raw = self.llm_client.generate(prompt)
        parsed, parse_note = self._parse_llm_output(raw)

        out_md = (parsed.get("markdown_text") or "").strip()
        out_summary = (parsed.get("summary") or "").strip()
        out_rag_analysis = parsed.get("rag_analysis")

        # 回退：结构化解析失败或缺字段
        if not out_md:
            out_md = raw.strip()
            if not out_summary:
                out_summary = "模型未按约定返回 JSON，已将原始输出作为 markdown_text 回退。"
            else:
                out_summary = f"{out_summary}\n\n注：模型未返回 markdown_text，已回退为原始输出。"

        # 强制“全文输出”保护：若疑似只返回了局部片段，则回退为原文全文并提示
        if self._looks_like_partial_output(original=markdown_text, updated=out_md):
            out_md = markdown_text
            extra = "模型输出疑似非全文（可能只给了局部段落），已回退为原文全文以满足硬约束。"
            out_summary = f"{out_summary}\n\n{extra}".strip() if out_summary else extra

        if parse_note:
            out_summary = f"{out_summary}\n\n{parse_note}".strip() if out_summary else parse_note

        # 若没有新 rag_analysis，则保留原值（由调用方决定如何合并）
        if out_rag_analysis is None:
            out_rag_analysis = existing_rag_analysis

        return DocAsPlanWriterResult(
            markdown_text=out_md,
            summary=out_summary,
            rag_analysis=out_rag_analysis,
        )

    def _build_prompt(
        self,
        *,
        markdown_text: str,
        user_query: str,
        doc_id: Optional[str],
        global_style: Optional[Dict[str, Any]],
        rag_key_facts: List[Dict[str, Any]],
        existing_rag_analysis: Optional[Dict[str, Any]],
    ) -> str:
        style = global_style or {}
        tone = style.get("tone", "学术正式")
        language = style.get("language", "zh")
        citation_style = style.get("citation_style", "GBT7714")

        facts_lines: List[str] = []
        for f in rag_key_facts:
            fid = f.get("id") or ""
            fact = f.get("fact") or ""
            src = f.get("source") or ""
            conf = f.get("confidence")
            facts_lines.append(f"- {fid} | {src} | conf={conf}: {fact}".strip())
        facts_block = "\n".join(facts_lines) if facts_lines else "(无)"

        mode_rules = """
【你要先做的事：LLM 自行判定模式】：
你必须先判断本次应当进入哪种模式，并在 summary 的第一行写明：`mode=plan` 或 `mode=write`，并用一句话说明判定理由。

判定规则（由你执行，不要输出判定过程，只在 summary 给结论与理由）：
- 如果 user_query 明确要“提纲/计划/大纲/结构/plan/写作计划/目录”等 => mode=plan
- 否则，如果 markdown 缺少章节结构、缺少 `### how_to_write`，或整体明显很短/空 => mode=plan
- 否则 => mode=write
""".strip()

        plan_rules = """
【Plan生成：输出要求（你必须严格遵守）】：
1) 产出完整 markdown 骨架（从标题到各章节），不要只输出片段。
2) 若原文已有标题/目录/章节结构：尽量保留；在缺失处补齐。
3) 每个“写作章节”（至少每个 `##` 章节）都必须包含一个 `### how_to_write` 小节。
4) 每个 `### how_to_write` 必须包含以下字段（用 markdown 列表表达即可）：
   - 目标字数：给出一个范围（例如 800-1200 字）
   - 写作要点：列出 5-10 条要点（按逻辑顺序）
   - 需要引用的 RAG：给出你会用到的 rag facts id 列表（例如 [F1, F3]）；如果没有可用事实，写明“无（需要补充资料）”
   - 结构安排：建议段落结构（例如 3-5 段，每段主题句是什么）
5) 章节标题要清晰（例如：`## 第一章 引言` / `## 第二章 ...`），并尽量覆盖常见学术结构（引言/相关工作/方法/实验或分析/结论）。\n""".strip()

        write_rules = """
【按章落文：输出要求（你必须严格遵守）】：
1) 你要根据 user_query 判断要写哪个章节（例如“第一章/第1章/引言/第二章第2节”等）。
2) 默认只修改目标章节，其他章节与结构尽量保持原样（包括标题、顺序、内容）。
3) 在目标章节内：找到 `### how_to_write` 小节，将其“内容”替换为真正的正文内容（按 how_to_write 里描述的写法来写）。
   - 保留 `### how_to_write` 这个标题不变，只替换其下方文本。
   - 替换范围：从该 `### how_to_write` 标题下一行开始，到下一个同级或更高等级标题（例如下一个 `###`/`##`/`#`）之前结束。
4) 正文写作时，优先使用可用 RAG 关键事实；如引用，尽量在句末用“（来源：F1）”这种方式标注 rag fact id，避免编造来源。\n""".strip()

        # 兼容当前 OpenRouterClient.generate() 只支持 user role：把系统约束写到同一 prompt 顶部
        instruction = f"""
你是一个论文写作的 Writer Agent。你将接收一篇论文的 markdown 全文，以及用户的修改指令。

【硬约束】：
1) 必须输出完整 markdown_text（全文）。不得只输出片段/差分/补丁。
2) 除非用户明确要求，否则不要改动无关章节；尽量局部插入/改写目标章节。
3) 尽量保留用户原文；润色尽量局部。若必须大范围改动，务必在 summary 说明改动范围。
4) 语言={language}；文风={tone}；引用格式={citation_style}（如需要引用占位符，请使用符合该规范的风格描述）。
5) 输出格式必须是严格 JSON，且只能输出 JSON，不要输出额外文本。

{mode_rules}

【执行要求】：
- 当你判定 mode=plan 时，严格执行下面的 Plan生成要求。
- 当你判定 mode=write 时，严格执行下面的 按章落文要求。

{plan_rules}

{write_rules}

【你需要返回的 JSON 结构】：
{{
  "markdown_text": "<<<更新后的全文>>>",
  "summary": "可选：简短说明改动了哪些章节/做了什么插入",
  "rag_analysis": {{ }}
}}

【文档信息】：
- doc_id: {doc_id or ""}

【用户指令】：
{user_query}

【可用 RAG 关键事实】：
{facts_block}

【原始 rag_analysis（可参考，可选）】：
{json.dumps(existing_rag_analysis or {{}}, ensure_ascii=False)}

【论文 markdown 全文】：
{markdown_text}
""".strip()

        return instruction

    def _parse_llm_output(self, text: str) -> Tuple[Dict[str, Any], str]:
        """
        尝试解析模型输出为 JSON：
        - 先直接 json.loads
        - 再尝试截取首尾花括号之间的 JSON 子串
        """
        if not isinstance(text, str):
            return {}, "模型输出非字符串，无法解析 JSON。"

        s = text.strip()
        if not s:
            return {}, "模型输出为空。"

        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj, ""
        except Exception:
            pass

        # 兜底：截取 JSON 子串
        try:
            start = s.find("{")
            end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                sub = s[start : end + 1]
                obj = json.loads(sub)
                if isinstance(obj, dict):
                    return obj, "注：已从输出中截取 JSON 子串进行解析。"
        except Exception:
            pass

        return {}, "注：模型输出无法解析为 JSON，将触发回退逻辑。"

    def _looks_like_partial_output(self, *, original: str, updated: str) -> bool:
        """
        简单启发式：当原文较长且输出明显过短/结构明显缺失时，判定为“疑似非全文输出”。
        """
        try:
            o = (original or "").strip()
            u = (updated or "").strip()
            if not o:
                return False
            if len(o) < 1200:
                # 短文不做强判断，避免误伤“从空生成 plan”的场景
                return False

            # 1) 长度比启发式
            if len(u) < 0.6 * len(o):
                return True

            # 2) 结构启发式：原文有较多标题，但输出标题明显变少（常见于只吐出某一段）
            def _count_headings(s: str) -> int:
                # 统计 markdown 标题行（# / ## / ### ...）
                return sum(1 for line in s.splitlines() if line.lstrip().startswith("#"))

            o_h = _count_headings(o)
            u_h = _count_headings(u)
            if o_h >= 6 and u_h <= max(2, int(0.5 * o_h)):
                return True

            return False
        except Exception:
            return False


