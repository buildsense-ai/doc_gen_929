from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict

from clients.openrouter_client import OpenRouterClient

from .models import Brief, CumulativeSummary

LOGGER = logging.getLogger(__name__)


CUMULATIVE_UPDATE_PROMPT = """
你是一名专业的文档编审，需要为新完成的章节生成Brief摘要，用于保持文档整体连贯和帮助后续章节更好地衔接。

当前累积摘要:
{current_cumulative_summary}

新完成的章节:
标题: {new_chapter_title}
内容摘要: {new_chapter_summary}

请基于当前文档进展和新章节内容，输出JSON（不要包含```）：
{{
  "summary": "本章节的核心内容概述，总结主要观点和结论",
  "suggestions_for_next": "对后续章节的建议或需要衔接的重点",
  "word_count": {word_count}
}}

要求：
1. summary: 简明扼要地总结本章节的核心内容（控制在150字以内）
2. suggestions_for_next: 基于本章节内容，为后续章节提供衔接建议（控制在100字以内）
3. word_count: 本章节的字数（直接使用提供的值）
4. 保持整体文档的连贯性和逻辑性
"""


class BriefGenerator:
    """Generates structured briefs for completed chapters."""

    def __init__(self, llm_client: OpenRouterClient):
        self.llm = llm_client

    def generate(self, title: str, content: str, current_cumulative_summary: str = "") -> Brief:
        """
        生成Brief摘要，统一使用CUMULATIVE_UPDATE_PROMPT
        
        Args:
            title: 章节标题
            content: 章节内容
            current_cumulative_summary: 当前累积摘要
        
        Returns:
            Brief对象
        """
        excerpt = (content or "").strip()
        word_count = len(content or "")
        
        # 统一使用CUMULATIVE_UPDATE_PROMPT
        prompt = CUMULATIVE_UPDATE_PROMPT.format(
            current_cumulative_summary=current_cumulative_summary or "文档开始",
            new_chapter_title=title,
            new_chapter_summary=excerpt[:500],  # 使用内容摘要
            word_count=word_count
        )
        
        try:
            response = self.llm.generate(prompt)
            payload = self._parse_json(response)
            payload["generated_at"] = datetime.utcnow().isoformat()
            payload["word_count"] = word_count  # 确保word_count正确
            return Brief.from_dict(payload) or self._fallback_brief(content, title)
        except Exception as exc:
            LOGGER.warning("Brief生成失败，使用fallback: %s", exc)
            return self._fallback_brief(content, title)

    def update_cumulative_summary(
        self, 
        cumulative_summary: CumulativeSummary, 
        chapter_index: int, 
        chapter_title: str, 
        chapter_brief: Brief
    ) -> CumulativeSummary:
        """Update cumulative summary with new chapter information."""
        # 添加新章节到累积摘要
        cumulative_summary.add_chapter(chapter_index, chapter_title, chapter_brief)
        
        # 使用LLM更新整体摘要
        try:
            current_summary = cumulative_summary.overall_summary or "文档开始"
            prompt = CUMULATIVE_UPDATE_PROMPT.format(
                current_cumulative_summary=current_summary,
                new_chapter_title=chapter_title,
                new_chapter_summary=chapter_brief.summary,
            )
            
            response = self.llm.generate(prompt)
            payload = self._parse_json(response)
            
            # 更新整体摘要
            if "overall_summary" in payload:
                cumulative_summary.overall_summary = payload["overall_summary"]
                
        except Exception as exc:
            LOGGER.warning("累积摘要更新失败，保持原有摘要: %s", exc)
            # 如果LLM更新失败，使用简单的拼接方式
            if not cumulative_summary.overall_summary:
                cumulative_summary.overall_summary = f"已完成章节: {chapter_title}"
            else:
                cumulative_summary.overall_summary += f" | {chapter_title}: {chapter_brief.summary[:50]}..."
        
        return cumulative_summary

    def _parse_json(self, text: str) -> Dict[str, Any]:
        match = text.strip()
        if not match:
            return {}
        if match.startswith("```"):
            match = match.strip("`")
        json_start = match.find("{")
        json_end = match.rfind("}")
        if json_start != -1 and json_end != -1:
            match = match[json_start : json_end + 1]
        return json.loads(match)

    def _fallback_brief(self, content: str, title: str) -> Brief:
        preview = (content or "").strip()
        snippet = preview[:140] + "..." if len(preview) > 140 else preview
        return Brief(
            summary=f"{title} - {snippet}",
            suggestions_for_next="延续当前章节的重点，确保上下文衔接。",
            word_count=len(content or ""),
            generated_at=datetime.utcnow().isoformat(),
        )

