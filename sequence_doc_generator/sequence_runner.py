from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from clients.openrouter_client import OpenRouterClient

from .simple_writer_agent import SimpleWriterAgent
from .simple_editor_agent import SimpleEditorAgent
from .brief_generator import BriefGenerator
from .models import SectionTask, TaskStatus, CumulativeSummary
from .redis_client import RedisQueueClient

LOGGER = logging.getLogger(__name__)


class SequenceGenerationRunner:
    """Executes the Redis-driven sequential generation pipeline."""

    def __init__(
        self,
        redis_client: Optional[RedisQueueClient] = None,
        llm_client: Optional[OpenRouterClient] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.redis = redis_client or RedisQueueClient()
        self.llm_client = llm_client or OpenRouterClient()
        self.writer_agent = SimpleWriterAgent(self.llm_client)
        self.editor_agent = SimpleEditorAgent(self.llm_client)
        self.brief_generator = BriefGenerator(self.llm_client)
        self.event_callback = event_callback or (lambda event: None)

    # ------------------------------------------------------------------
    def run(self, project_id: str, session_id: str, project_name: str) -> None:
        tasks, _ = self.redis.load_queue(project_id, session_id)
        if not tasks:
            LOGGER.info("序列生成：队列为空，直接结束")
            return

        # 更新Redis状态为generating
        try:
            from .models import gen_state_key
            state_key = gen_state_key(project_id, session_id)
            self.redis.client.set(state_key, "generating", ex=3600)  # 1小时过期
            LOGGER.info(f"📊 更新Redis状态: {state_key} -> generating")
        except Exception as e:
            LOGGER.warning(f"⚠️ 更新Redis状态失败: {e}")

        self._emit_event(
            "sequence_started",
            project_id=project_id,
            session_id=session_id,
            project_name=project_name,
        )

        while True:
            # 首先检查是否有暂停的任务需要恢复
            paused_index, paused_task = self._find_paused_task(tasks)
            if paused_task is not None:
                # 检查是否有用户反馈需要处理
                feedback = self._check_user_feedback(project_id, session_id)
                if feedback:
                    LOGGER.info(f"处理用户反馈: {feedback['text']}")
                    # 将任务状态改为等待，以便重新处理
                    paused_task.status = TaskStatus.WAITING
                    paused_task.missing_info = []  # 清除缺失信息
                    # 可以根据反馈调整任务的how_to_write
                    if feedback.get('chapter_hint') == 'current':
                        paused_task.how_to_write += f"\n\n用户反馈: {feedback['text']}"
                    self.redis.update_task_entry(project_id, session_id, paused_index, paused_task)
                    tasks[paused_index] = paused_task
                    continue
                else:
                    # 没有反馈，跳过暂停的任务
                    LOGGER.info(f"跳过暂停任务: {paused_task.title}")
            
            queue_index, task = self.redis.find_waiting_task(tasks)
            if task is None:
                # 检查是否还有暂停的任务
                if any(t.status == TaskStatus.PAUSED for t in tasks):
                    LOGGER.info("所有等待任务已完成，但仍有暂停任务等待用户反馈")
                    self._emit_event(
                        "waiting_for_user_input", 
                        project_id=project_id, 
                        session_id=session_id,
                        paused_tasks=[t.title for t in tasks if t.status == TaskStatus.PAUSED]
                    )
                    # 等待用户反馈或继续信号
                    ack = self.redis.wait_for_continue_signal(
                        project_id,
                        session_id,
                        timeout_seconds=300,  # 5分钟超时
                        on_wait=lambda waited: LOGGER.debug("等待用户处理暂停任务 %ss...", waited),
                    )
                    if ack:
                        # 重新加载队列，继续处理
                        tasks, _ = self.redis.load_queue(project_id, session_id)
                        continue
                    else:
                        LOGGER.warning("等待用户反馈超时，序列生成暂停")
                        break
                else:
                    # ✅ 严格检查：重新加载队列并确认所有任务真的都完成了
                    tasks, _ = self.redis.load_queue(project_id, session_id)
                    
                    # 统计各状态任务数量
                    status_counts = {
                        "waiting": sum(1 for t in tasks if t.status == TaskStatus.WAITING),
                        "working": sum(1 for t in tasks if t.status == TaskStatus.WORKING),
                        "worked": sum(1 for t in tasks if t.status == TaskStatus.WORKED),
                        "paused": sum(1 for t in tasks if t.status == TaskStatus.PAUSED),
                    }
                    
                    LOGGER.info(f"📊 检查完成状态: 总数={len(tasks)}, waiting={status_counts['waiting']}, working={status_counts['working']}, worked={status_counts['worked']}, paused={status_counts['paused']}")
                    
                    # 检查是否还有未完成的任务（WAITING 或 WORKING）
                    unfinished = status_counts["waiting"] + status_counts["working"]
                    if unfinished > 0:
                        LOGGER.warning(f"⚠️ 仍有 {unfinished} 个任务未完成，继续等待...")
                        time.sleep(2)  # 等待2秒后重新检查
                        continue
                    
                    # 确保所有任务都是 WORKED 状态才发送 all_completed
                    if status_counts["worked"] == len(tasks):
                        LOGGER.info(f"✅ 所有 {len(tasks)} 个任务已完成，发送 all_completed 事件")
                        self._emit_event(
                            "all_completed", project_id=project_id, session_id=session_id
                        )
                        break
                    else:
                        LOGGER.warning(f"⚠️ 任务状态异常，继续等待... (状态分布: {status_counts})")
                        time.sleep(2)
                        continue

            # 获取当前累积摘要
            cumulative_summary = self.redis.get_cumulative_summary(project_id, session_id)
            if cumulative_summary is None:
                cumulative_summary = CumulativeSummary()

            task.status = TaskStatus.WORKING
            self.redis.update_task_entry(project_id, session_id, queue_index, task)
            self._emit_event(
                "chapter_started",
                project_id=project_id,
                session_id=session_id,
                task_index=task.index,
                title=task.title,
            )

            try:
                # 将累积摘要传递给Writer Agent进行检索
                retrieved_info = self._retrieve_context(task, project_name, cumulative_summary)
                if not self._has_sufficient_material(retrieved_info):
                    self._handle_insufficient_data(
                        project_id,
                        session_id,
                        project_name,
                        queue_index,
                        task,
                        retrieved_info,
                    )
                    tasks[queue_index] = task
                    continue

                # 将累积摘要传递给Editor Agent生成内容
                generation = self._generate_content(task, retrieved_info, cumulative_summary)
                task.content = generation.get("content")
                
                # 生成Brief时传递当前累积摘要
                context_summary = cumulative_summary.get_context_for_next_chapter()
                task.brief = self.brief_generator.generate(
                    task.title, 
                    task.content or "", 
                    current_cumulative_summary=context_summary
                )
                task.generated_at = datetime.utcnow().isoformat()
                task.status = TaskStatus.WORKED
                tasks[queue_index] = task

                # 更新累积摘要
                cumulative_summary = self.brief_generator.update_cumulative_summary(
                    cumulative_summary, task.index, task.title, task.brief
                )
                self.redis.update_cumulative_summary(project_id, session_id, cumulative_summary)

                self.redis.update_task_entry(project_id, session_id, queue_index, task)
                self._emit_event(
                    "chapter_completed_awaiting_confirmation",
                    project_id=project_id,
                    session_id=session_id,
                    task_index=task.index,
                    title=task.title,
                    content=task.content,
                    brief=task.brief.to_dict() if task.brief else None,
                    word_count=generation.get("word_count"),
                    cumulative_summary=cumulative_summary.to_dict(),
                )

                ack = self.redis.wait_for_continue_signal(
                    project_id,
                    session_id,
                    on_wait=lambda waited: LOGGER.debug(
                        "等待writer_continue信号 %ss...", waited
                    ),
                )
                if not ack:
                    LOGGER.warning("等待确认超时，自动继续执行")
                    self._emit_event(
                        "continue_timeout",
                        project_id=project_id,
                        session_id=session_id,
                        task_index=task.index,
                    )

            except Exception as exc:
                LOGGER.exception("章节处理失败: %s", exc)
                task.status = TaskStatus.PAUSED
                task.missing_info = [f"生成异常: {exc}"]
                self.redis.update_task_entry(project_id, session_id, queue_index, task)
                self._emit_event(
                    "chapter_failed",
                    project_id=project_id,
                    session_id=session_id,
                    task_index=task.index,
                    title=task.title,
                    error=str(exc),
                )
                break

    # ------------------------------------------------------------------
    def _retrieve_context(
        self, task: SectionTask, project_name: str, cumulative_summary: CumulativeSummary
    ) -> Dict[str, Any]:
        """使用SimpleWriterAgent检索资料"""
        # 获取累积摘要作为上下文
        context_summary = cumulative_summary.get_context_for_next_chapter()
        
        # 构造任务描述
        task_desc = {
            "title": task.title,
            "how_to_write": task.how_to_write
        }
        
        # 使用Writer Agent检索
        retrieved_info = self.writer_agent.retrieve_for_task(
            task_desc, 
            context_summary,
            project_name
        )
        
        return retrieved_info

    def _has_sufficient_material(self, retrieved_info: Dict[str, Any]) -> bool:
        """判断检索到的资料是否充足（标准：至少3条文本结果）"""
        text_count = len(retrieved_info.get("retrieved_text", []))
        image_count = len(retrieved_info.get("retrieved_image", []))
        table_count = len(retrieved_info.get("retrieved_table", []))
        
        # 简化判断标准：至少3条文本结果
        has_sufficient = text_count >= 3
        
        if not has_sufficient:
            LOGGER.warning(f"⚠️ 资料不足: 文本={text_count}, 图片={image_count}, 表格={table_count} (需要至少3条文本)")
        else:
            LOGGER.info(f"✅ 资料充足: 文本={text_count}, 图片={image_count}, 表格={table_count}")
            
        return has_sufficient

    def _generate_content(
        self, task: SectionTask, retrieved_info: Dict[str, Any], cumulative_summary: CumulativeSummary
    ) -> Dict[str, Any]:
        """使用SimpleEditorAgent生成内容"""
        # 获取累积摘要作为上下文
        context_summary = cumulative_summary.get_context_for_next_chapter()
        
        # 构造任务描述
        task_desc = {
            "title": task.title,
            "how_to_write": task.how_to_write
        }
        
        # 使用Editor Agent生成内容
        generation = self.editor_agent.generate_content(
            task_desc,
            retrieved_info,
            context_summary
        )
        
        return generation

    def _handle_insufficient_data(
        self,
        project_id: str,
        session_id: str,
        project_name: str,
        queue_index: int,
        task: SectionTask,
        retrieved_info: Dict[str, Any],
    ) -> None:
        # 分析具体缺失的资料类型
        text_count = len(retrieved_info.get("retrieved_text", []))
        image_count = len(retrieved_info.get("retrieved_image", []))
        table_count = len(retrieved_info.get("retrieved_table", []))
        
        missing_details = []
        if text_count == 0:
            missing_details.append("缺少文档文本资料")
        elif text_count < 3:
            missing_details.append(f"文档资料不足（当前{text_count}条，需要至少3条）")
            
        if image_count == 0 and table_count == 0:
            missing_details.append("缺少图片或表格等辅助资料（可选）")
        
        # 提供具体的补充建议
        suggestions = [
            f"请为章节'{task.title}'补充以下资料：",
            "1. 上传相关的文档资料（PDF、Word等）",
            "2. 如有需要，提供相关的图片或表格文件"
        ]
        
        task.status = TaskStatus.PAUSED
        task.missing_info = missing_details + suggestions
        
        # 记录暂停原因到日志
        LOGGER.warning(f"章节'{task.title}'因资料不足暂停: {', '.join(missing_details)}")
        
        self.redis.update_task_entry(project_id, session_id, queue_index, task)
        self._emit_event(
            "chapter_paused",
            project_id=project_id,
            session_id=session_id,
            task_index=task.index,
            title=task.title,
            missing_info=task.missing_info,
            material_analysis={
                "text_count": text_count,
                "image_count": image_count,
                "table_count": table_count,
                "total_count": text_count + image_count + table_count
            },
            suggestions=suggestions
        )

    def _find_paused_task(self, tasks: List[SectionTask]) -> Tuple[Optional[int], Optional[SectionTask]]:
        """查找第一个暂停的任务"""
        for idx, task in enumerate(tasks):
            if task.status == TaskStatus.PAUSED:
                return idx, task
        return None, None
    
    def _check_user_feedback(self, project_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """检查是否有用户反馈"""
        try:
            feedback_key = f"feedback:{project_id}:{session_id}"
            feedback_data = self.redis.client.rpop(feedback_key)  # 从队列尾部取出最新反馈
            if feedback_data:
                import json
                return json.loads(feedback_data)
        except Exception as e:
            LOGGER.warning(f"检查用户反馈失败: {e}")
        return None

    def _emit_event(self, event_type: str, **payload: Any) -> None:
        event = {"event_type": event_type, **payload}
        try:
            self.event_callback(event)
        except Exception as exc:
            LOGGER.debug("事件回调执行失败: %s", exc)

