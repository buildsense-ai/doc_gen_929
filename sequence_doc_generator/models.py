from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    """Redis queue task status."""

    WAITING = "waiting"
    WORKING = "working"
    PAUSED = "paused"
    WORKED = "worked"

    @classmethod
    def from_value(cls, value: str) -> "TaskStatus":
        try:
            return cls(value)
        except ValueError:
            return cls.WAITING


@dataclass
class Brief:
    """Structured summary returned to the planning / front-end layer."""

    summary: str = ""
    suggestions_for_next: str = ""
    word_count: int = 0
    generated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Brief"]:
        if not data:
            return None
        return cls(
            summary=data.get("summary", ""),
            suggestions_for_next=data.get("suggestions_for_next", ""),
            word_count=int(data.get("word_count", 0)),
            generated_at=data.get("generated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "suggestions_for_next": self.suggestions_for_next,
            "word_count": self.word_count,
            "generated_at": self.generated_at,
        }


@dataclass
class CumulativeSummary:
    """Cumulative summary that grows with each completed chapter."""

    overall_summary: str = ""
    chapter_summaries: List[Dict[str, Any]] = field(default_factory=list)
    total_word_count: int = 0
    last_updated: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["CumulativeSummary"]:
        if not data:
            return None
        return cls(
            overall_summary=data.get("overall_summary", ""),
            chapter_summaries=list(data.get("chapter_summaries", [])),
            total_word_count=int(data.get("total_word_count", 0)),
            last_updated=data.get("last_updated"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_summary": self.overall_summary,
            "chapter_summaries": self.chapter_summaries,
            "total_word_count": self.total_word_count,
            "last_updated": self.last_updated,
        }

    def add_chapter(self, chapter_index: int, title: str, brief: Brief) -> None:
        """Add a new chapter's brief to the cumulative summary."""
        chapter_entry = {
            "index": chapter_index,
            "title": title,
            "summary": brief.summary,
            "suggestions_for_next": brief.suggestions_for_next,
            "word_count": brief.word_count,
            "generated_at": brief.generated_at,
        }
        self.chapter_summaries.append(chapter_entry)
        self.total_word_count += brief.word_count
        self.last_updated = brief.generated_at

    def get_context_for_next_chapter(self) -> str:
        """Generate context string for the next chapter based on cumulative summary."""
        if not self.chapter_summaries:
            return ""
        
        context_parts = []
        if self.overall_summary:
            context_parts.append(f"整体进展: {self.overall_summary}")
        
        # 添加最近几个章节的摘要
        recent_chapters = self.chapter_summaries[-3:]  # 最近3个章节
        for chapter in recent_chapters:
            context_parts.append(f"第{chapter['index']+1}章 {chapter['title']}: {chapter['summary']}")
        
        # 添加最新的建议
        if recent_chapters:
            last_suggestion = recent_chapters[-1].get("suggestions_for_next")
            if last_suggestion:
                context_parts.append(f"前章建议: {last_suggestion}")
        
        return " | ".join(context_parts)


@dataclass
class SectionTask:
    """Represents a single chapter task inside the Redis queue."""

    index: int
    title: str
    how_to_write: str
    status: TaskStatus = TaskStatus.WAITING
    estimated_words: int = 0
    original_index: Optional[int] = None
    session_id: Optional[str] = None
    project_name: Optional[str] = None
    reason: Optional[str] = None
    content: Optional[str] = None
    brief: Optional[Brief] = None
    generated_at: Optional[str] = None
    missing_info: List[str] = field(default_factory=list)
    rag_analysis: Optional[Dict[str, Any]] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_redis_entry(cls, data: Dict[str, Any]) -> "SectionTask":
        brief = Brief.from_dict(data.get("brief"))
        known_keys = {
            "index",
            "title",
            "how_to_write",
            "status",
            "estimated_words",
            "original_index",
            "session_id",
            "project_name",
            "reason",
            "content",
            "brief",
            "generated_at",
            "missing_info",
            "rag_analysis",
        }
        extra = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            index=int(data.get("index", data.get("original_index", 0))),
            title=data.get("title", ""),
            how_to_write=data.get("how_to_write", ""),
            status=TaskStatus.from_value(data.get("status", "waiting")),
            estimated_words=int(data.get("estimated_words", 0)),
            original_index=data.get("original_index"),
            session_id=data.get("session_id"),
            project_name=data.get("project_name"),
            reason=data.get("reason"),
            content=data.get("content"),
            brief=brief,
            generated_at=data.get("generated_at"),
            missing_info=list(data.get("missing_info", [])),
            rag_analysis=data.get("rag_analysis"),
            extra_fields=extra,
        )

    def to_redis_entry(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "index": self.index,
            "title": self.title,
            "how_to_write": self.how_to_write,
            "status": self.status.value,
            "estimated_words": self.estimated_words,
            "original_index": self.original_index,
            "session_id": self.session_id,
            "project_name": self.project_name,
            "reason": self.reason,
            "content": self.content,
            "generated_at": self.generated_at,
            "missing_info": self.missing_info,
            "rag_analysis": self.rag_analysis,
        }
        if self.brief:
            payload["brief"] = self.brief.to_dict()
        payload.update(self.extra_fields)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_redis_entry(), ensure_ascii=False)


def queue_key(project_id: str, session_id: str) -> str:
    return f"task_queue:{project_id}:{session_id}"


def gen_state_key(project_id: str, session_id: str) -> str:
    return f"gen_state:{project_id}:{session_id}"


def writer_continue_key(project_id: str, session_id: str) -> str:
    return f"writer_continue:{project_id}:{session_id}"


def cumulative_summary_key(project_id: str, session_id: str) -> str:
    return f"cumulative_summary:{project_id}:{session_id}"

