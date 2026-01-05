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
        if not markdown_text or not markdown_text.strip():
            raise ValueError("markdown_text 为空")
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

        # 兼容当前 OpenRouterClient.generate() 只支持 user role：把系统约束写到同一 prompt 顶部
        instruction = f"""
你是一个论文写作的 Writer Agent。你将接收一篇论文的 markdown 全文，以及用户的修改指令。

【硬约束】：
1) 必须输出完整 markdown_text（全文）。不得只输出片段/差分/补丁。
2) 除非用户明确要求，否则不要改动无关章节；尽量局部插入/改写目标章节。
3) 尽量保留用户原文；润色尽量局部。若必须大范围改动，务必在 summary 说明改动范围。
4) 语言={language}；文风={tone}；引用格式={citation_style}（如需要引用占位符，请使用符合该规范的风格描述）。
5) 输出格式必须是严格 JSON，且只能输出 JSON，不要输出额外文本。

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

【可用 RAG 关键事实（可选）】：
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
        简单启发式：当原文较长且输出明显过短时，判定为“疑似非全文输出”。
        """
        try:
            o = (original or "").strip()
            u = (updated or "").strip()
            if len(o) < 1200:
                return False
            if len(u) < 0.6 * len(o):
                return True
            return False
        except Exception:
            return False


