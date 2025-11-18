from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from clients.openrouter_client import OpenRouterClient

from .redis_client import RedisQueueClient
from .sequence_runner import SequenceGenerationRunner

LOGGER = logging.getLogger(__name__)


def run_sequence_generation(
    project_id: str,
    session_id: str,
    project_name: str,
    *,
    event_callback: Optional[Callable[[dict], None]] = None,
    redis_client: Optional[RedisQueueClient] = None,
    llm_client: Optional[OpenRouterClient] = None,
) -> None:
    """
    Public entry point used by the main system or API server.

    Args:
        project_id: Unique project identifier (UUID string).
        session_id: Conversation/session ID.
        project_name: Human-readable project label used by ReactAgent.
        event_callback: Optional callable receiving event dictionaries for SSE/WS.
        redis_client: Optional pre-configured RedisQueueClient.
        llm_client: Optional OpenRouterClient reuse (to share rate limits).
    """
    runner = SequenceGenerationRunner(
        redis_client=redis_client,
        llm_client=llm_client,
        event_callback=event_callback,
    )
    LOGGER.info(
        "启动序列生成 pipeline (project_id=%s, session_id=%s)", project_id, session_id
    )
    runner.run(project_id, session_id, project_name)

