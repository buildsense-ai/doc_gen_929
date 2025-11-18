# Sequence Document Generator

本目录提供一个与 Todo Planning Agent/前端协同的"序列式"文档生成工作流，核心能力：

1. **Redis 队列驱动**：按照 `task_queue:{project_id}:{session_id}` 中的章节任务逐个执行。
2. **复用现有 Agent**：
   - `ReactAgent`：通过适配器模式，将单章节任务包装成临时的report_guide格式，调用现有的检索逻辑
   - `SimpleContentGeneratorAgent`：直接使用其`generate_content_from_json()`方法，该方法本身就是为单章节设计的，完美适配序列生成需求
3. **增量摘要传递**：每完成一个章节，系统会更新累积摘要并传递给下一章节的生成过程，确保内容的连贯性和上下文衔接。
4. **Brief 输出**：每个完成的章节都会生成结构化 Brief，供 Todo Planning / 前端展示。
5. **等待机制**：章节完成后挂起，等待 `writer_continue:{project_id}:{session_id}` 信号或超时自动继续。
6. **事件钩子**：通过 `event_callback` 将关键事件推送给前端或 FastAPI SSE 管道。

## 目录结构

```
sequence_doc_generator/
├── __init__.py                 # 对外导出 run_sequence_generation
├── README.md                   # 本文件
├── brief_generator.py          # Brief 生成逻辑
├── models.py                   # 队列 Task/Brief 数据模型
├── pipeline.py                 # 对外入口函数
├── redis_client.py             # Redis 封装
└── sequence_runner.py          # 主循环
```

## Redis 约定

| Key | 说明 |
| --- | --- |
| `task_queue:{project_id}:{session_id}` | Redis List，元素为章节任务 JSON，同 `writer-agent-integration.md` |
| `gen_state:{project_id}:{session_id}` | 可选，记录当前生成状态（generating/idle 等） |
| `writer_continue:{project_id}:{session_id}` | 字符串 Key，值为 `"true"` 表示允许继续；读取后立即删除 |
| `sequence_logs:{project_id}:{session_id}` | 可选 Redis Stream，记录 runner 侧日志 |

任务状态沿用 `waiting / working / paused / worked`。`paused` 代表资料不足；需要 Todo Planning Agent 或用户补充信息后再改回 `waiting`。

## 事件（供前端/SSE）

`run_sequence_generation` 接收可选 `event_callback`，每个事件都是字典：

| event_type | 触发时机 | 关键字段 |
| --- | --- | --- |
| `sequence_started` | 进入主循环前 | `project_id`, `session_id`, `project_name` |
| `chapter_started` | 某章节设为 `working` | `task_index`, `title` |
| `chapter_paused` | 资料不足 | `task_index`, `title`, `missing_info` |
| `chapter_completed_awaiting_confirmation` | 章节完成等待确认 | `content`, `brief`, `quality_score`, `word_count` |
| `continue_timeout` | 等待确认超时 | `task_index` |
| `chapter_failed` | 生成异常 | `task_index`, `error` |
| `all_completed` | 队列无 `waiting` 任务 | - |

前端收到 `chapter_completed_awaiting_confirmation` 后，可展示章节内容 + Brief，并在合适时机调用现有 API 设置 `writer_continue` 信号让生成继续。

## 调用方式

```python
from sequence_doc_generator import run_sequence_generation

def handle_event(evt: dict):
    # 将事件推送到SSE、WebSocket或日志系统
    print(evt)

run_sequence_generation(
    project_id="957150ea-2def-4d73-a7f6-4a96369e1909",
    session_id="7b02f72b-525f-4a47-ad0c-c28f8dac8967",
    project_name="医灵古庙",
    event_callback=handle_event,
)
```

> ⚠️ 注意：主系统需确保同一 `(project_id, session_id)` 只启动一个 runner 实例，可通过 Redis 分布式锁实现。

## Brief 格式

```json
{
  "summary": "本章节的核心内容概述，2-3句话总结主要观点和结论",
  "suggestions_for_next": "对下一章的衔接建议",
  "word_count": 850,
  "generated_at": "2025-01-10T08:30:00Z"
}
```

若 LLM 解析失败则使用简化 fallback，仍保证字段齐全，便于前端消费。

## 增量摘要机制

系统通过累积摘要实现章节间的上下文传递：

### 累积摘要结构
```json
{
  "overall_summary": "整个文档的总体进展摘要",
  "chapter_summaries": [
    {
      "index": 0,
      "title": "项目背景",
      "summary": "本章节概述了...",
      "suggestions_for_next": "下一章节应重点关注...",
      "word_count": 1500,
      "generated_at": "2024-01-01T10:00:00Z"
    }
  ],
  "total_word_count": 1500,
  "last_updated": "2024-01-01T10:00:00Z"
}
```

### 传递流程
1. **章节生成前**：从Redis获取累积摘要，提取上下文信息传递给ReactAgent和ContentGenerator
2. **章节生成后**：更新累积摘要，添加新章节的Brief信息
3. **上下文构建**：为下一章节构建包含最近3个章节摘要和前章建议的上下文字符串

### Redis存储
- **Key**: `cumulative_summary:{project_id}:{session_id}`
- **过期时间**: 7天
- **数据格式**: JSON字符串

## 与 Todo Planning Agent 协作

1. Todo Agent 负责编排/修改 Redis queue（更新 `status`、`how_to_write` 等）。
2. Sequence runner 每次循环都会重新读取 queue，自动感知最新排序与状态。
3. 章节完成后，runner 将 Brief 推送给事件回调，Todo Agent 可基于 Brief 决定是否调整剩余任务，再通过设置 `writer_continue` 释放 runner。

这样即可在不修改现有 Orchestrator/React/Content 逻辑的前提下，实现串行生成 + 实时反馈的闭环。***

