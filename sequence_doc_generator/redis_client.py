from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

import redis

from .models import (
    SectionTask,
    TaskStatus,
    CumulativeSummary,
    gen_state_key,
    queue_key,
    writer_continue_key,
    cumulative_summary_key,
)

LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Local continue signal registry (used for HTTP-trigger fast paths)
# ----------------------------------------------------------------------
_INTERNAL_CONTINUE_SIGNALS: Dict[str, bool] = {}


def _internal_continue_key(project_id: str, session_id: str) -> str:
    return f"{project_id}:{session_id}"


def set_internal_continue_signal(project_id: str, session_id: str) -> None:
    """Mark that an external notification has confirmed the continue signal."""
    _INTERNAL_CONTINUE_SIGNALS[_internal_continue_key(project_id, session_id)] = True


def pop_internal_continue_signal(project_id: str, session_id: str) -> bool:
    """Return True once if an internal continue signal was registered."""
    key = _internal_continue_key(project_id, session_id)
    return _INTERNAL_CONTINUE_SIGNALS.pop(key, False)


def has_internal_continue_signal(project_id: str, session_id: str) -> bool:
    """Check whether an internal continue signal is pending."""
    key = _internal_continue_key(project_id, session_id)
    return _INTERNAL_CONTINUE_SIGNALS.get(key, False)


def _build_redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True,
    )


class RedisQueueClient:
    """Helper that encapsulates all Redis interactions required by the runner."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.client = redis_client or _build_redis_client()

    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------
    def load_queue(
        self, project_id: str, session_id: str
    ) -> Tuple[List[SectionTask], List[str]]:
        key = queue_key(project_id, session_id)
        entries = self.client.lrange(key, 0, -1)
        tasks: List[SectionTask] = []
        for entry in entries:
            try:
                data = json.loads(entry)
                tasks.append(SectionTask.from_redis_entry(data))
            except json.JSONDecodeError:
                LOGGER.warning("无法解析queue条目: %s", entry)
        return tasks, entries

    def find_waiting_task(
        self, tasks: List[SectionTask]
    ) -> Tuple[Optional[int], Optional[SectionTask]]:
        for idx, task in enumerate(tasks):
            if task.status == TaskStatus.WAITING:
                return idx, task
        return None, None

    def update_task_entry(
        self,
        project_id: str,
        session_id: str,
        queue_index: int,
        task: SectionTask,
    ) -> None:
        key = queue_key(project_id, session_id)
        try:
            self.client.lset(key, queue_index, task.to_json())
        except redis.exceptions.ResponseError as e:
            if "index out of range" in str(e):
                # 重新加载队列并查找任务
                LOGGER.warning(f"⚠️ 索引 {queue_index} 无效，尝试重新定位任务 {task.index}")
                tasks, _ = self.load_queue(project_id, session_id)
                for idx, t in enumerate(tasks):
                    if t.index == task.index:
                        LOGGER.info(f"✅ 重新定位成功: 任务{task.index} -> 队列位置{idx}")
                        self.client.lset(key, idx, task.to_json())
                        return
                LOGGER.error(f"❌ 无法找到任务 {task.index} 在队列中")
            raise

    # ------------------------------------------------------------------
    # Generation state + signals
    # ------------------------------------------------------------------
    def set_generation_state(
        self,
        project_id: str,
        session_id: str,
        state_payload: Dict[str, str],
        ttl: int = 3600,
    ) -> None:
        key = gen_state_key(project_id, session_id)
        if state_payload:
            self.client.hset(key, mapping=state_payload)
        if ttl:
            self.client.expire(key, ttl)

    def set_writer_continue(self, project_id: str, session_id: str) -> None:
        key = writer_continue_key(project_id, session_id)
        self.client.set(key, "true", ex=600)

    def check_writer_continue_signal(self, project_id: str, session_id: str) -> bool:
        """Non-destructively check whether the continue signal exists."""
        key = writer_continue_key(project_id, session_id)
        return bool(self.client.get(key))

    def wait_for_continue_signal(
        self,
        project_id: str,
        session_id: str,
        timeout_seconds: int = 300,
        poll_interval: float = 2.0,
        on_wait: Optional[Callable[[int], None]] = None,
    ) -> bool:
        key = writer_continue_key(project_id, session_id)
        start = time.time()
        while time.time() - start < timeout_seconds:
            if pop_internal_continue_signal(project_id, session_id):
                LOGGER.debug(
                    "通过内部HTTP通知收到continue信号: %s/%s", project_id, session_id
                )
                self.client.delete(key)
                return True
            value = self.client.get(key)
            if value:
                self.client.delete(key)
                return True
            if on_wait:
                waited = int(time.time() - start)
                on_wait(waited)
            time.sleep(poll_interval)
        return False

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------
    def append_task_log(
        self,
        project_id: str,
        session_id: str,
        message: str,
        level: str = "info",
    ) -> None:
        """
        Pushes a simple log message to a Redis stream (optional).
        This keeps the runner decoupled from FastAPI's SSE pipeline.
        """
        stream_key = f"sequence_logs:{project_id}:{session_id}"
        entry = {"level": level, "message": message}
        try:
            self.client.xadd(stream_key, entry, maxlen=1000, approximate=True)
        except redis.RedisError:
            LOGGER.debug("写入log stream失败: %s", stream_key)

    # ------------------------------------------------------------------
    # Cumulative Summary helpers
    # ------------------------------------------------------------------
    def get_cumulative_summary(
        self, project_id: str, session_id: str
    ) -> Optional[CumulativeSummary]:
        """Get the cumulative summary for the project session."""
        key = cumulative_summary_key(project_id, session_id)
        try:
            data = self.client.get(key)
            if not data:
                return None
            summary_data = json.loads(data)
            return CumulativeSummary.from_dict(summary_data)
        except (json.JSONDecodeError, redis.RedisError) as e:
            LOGGER.warning("获取累积摘要失败: %s", e)
            return None

    def update_cumulative_summary(
        self, project_id: str, session_id: str, cumulative_summary: CumulativeSummary
    ) -> None:
        """Update the cumulative summary in Redis."""
        key = cumulative_summary_key(project_id, session_id)
        try:
            data = json.dumps(cumulative_summary.to_dict())
            self.client.set(key, data, ex=86400 * 7)  # 7天过期
            LOGGER.debug("累积摘要已更新: %s", key)
        except (json.JSONEncodeError, redis.RedisError) as e:
            LOGGER.error("更新累积摘要失败: %s", e)

    def clear_cumulative_summary(self, project_id: str, session_id: str) -> None:
        """Clear the cumulative summary for the project session."""
        key = cumulative_summary_key(project_id, session_id)
        try:
            self.client.delete(key)
            LOGGER.debug("累积摘要已清除: %s", key)
        except redis.RedisError as e:
            LOGGER.warning("清除累积摘要失败: %s", e)

