# 序列生成API集成文档

## 概述

本文档描述了序列生成系统的API接口，用于与Todo Planning Agent和前端系统对接。序列生成系统支持逐章节生成文档，并允许用户在生成过程中提供反馈。

## API端点

### 1. 启动序列生成

**端点**: `POST /sequence_generation/start`

**描述**: 启动一个新的序列生成任务，从Redis队列中读取任务并逐章节生成文档。

**请求体**:
```json
{
  "project_id": "proj_123456",
  "session_id": "session_789",
  "project_name": "医灵古庙文物影响评估"
}
```

**响应**:
```json
{
  "status": "started",
  "message": "序列生成任务已启动",
  "project_id": "proj_123456",
  "session_id": "session_789"
}
```

### 2. 提交用户反馈

**端点**: `POST /sequence_generation/{project_id}/{session_id}/feedback`

**描述**: 在序列生成过程中提交用户反馈，影响后续章节的生成。

**请求体**:
```json
{
  "text": "第二章历史部分太简单了，需要更详细的描述",
  "chapter_hint": "current"
}
```

**chapter_hint** 可选值:
- `current`: 影响当前章节
- `next`: 影响下一章节
- `all_future`: 影响所有后续章节
- `chapter_N`: 影响特定章节（如 `chapter_2`）

**响应**:
```json
{
  "status": "received",
  "message": "反馈已收到并处理",
  "project_id": "proj_123456",
  "session_id": "session_789"
}
```

### 3. 继续生成

**端点**: `POST /sequence_generation/{project_id}/{session_id}/continue`

**描述**: 发送继续信号给序列生成器，用于在章节完成后继续生成下一章节。

**响应**:
```json
{
  "status": "sent",
  "message": "继续信号已发送",
  "project_id": "proj_123456",
  "session_id": "session_789"
}
```

### 4. 获取生成状态

**端点**: `GET /sequence_generation/{project_id}/{session_id}/status`

**描述**: 获取当前序列生成任务的状态和进度。

**响应**:
```json
{
  "project_id": "proj_123456",
  "session_id": "session_789",
  "current_status": {
    "status": "working",
    "current_chapter": 2,
    "message": "正在生成第2章内容"
  },
  "task_queue": [
    {
      "chapter_title": "项目背景",
      "status": "worked",
      "content": "..."
    },
    {
      "chapter_title": "历史文化价值",
      "status": "working",
      "content": null
    }
  ],
  "total_tasks": 5,
  "completed_tasks": 1
}
```

## 事件系统

序列生成系统通过事件回调机制与外部系统通信。以下是主要事件类型：

### 章节完成事件
```json
{
  "event_type": "chapter_completed",
  "data": {
    "project_id": "proj_123456",
    "session_id": "session_789",
    "chapter_index": 1,
    "chapter_title": "项目背景",
    "content": "章节内容...",
    "brief": {
      "summary": "本章节概述了项目的基本背景和核心要点",
      "suggestions_for_next": "下一章节应重点关注历史文化价值的详细分析",
      "word_count": 1500
    },
    "cumulative_summary": {
      "overall_summary": "已完成项目背景章节，建立了基础框架",
      "chapter_summaries": [
        {
          "index": 0,
          "title": "项目背景",
          "summary": "本章节概述了项目的基本背景和核心要点",
          "word_count": 1500
        }
      ],
      "total_word_count": 1500
    }
  }
}
```

### 章节暂停事件
```json
{
  "event_type": "chapter_paused",
  "data": {
    "project_id": "proj_123456",
    "session_id": "session_789",
    "chapter_index": 2,
    "reason": "资料不足",
    "missing_info": ["需要更多历史资料", "缺少考古数据"]
  }
}
```

### 生成完成事件
```json
{
  "event_type": "generation_completed",
  "data": {
    "project_id": "proj_123456",
    "session_id": "session_789",
    "total_chapters": 5,
    "final_document_path": "/path/to/final/document.md"
  }
}
```

## Redis数据结构

### 任务队列
**Key**: `task_queue:{project_id}:{session_id}`
**类型**: List
**内容**: JSON格式的任务对象

```json
{
  "chapter_title": "项目背景",
  "chapter_index": 0,
  "status": "waiting",
  "requirements": "描述项目的基本情况和背景",
  "content": null,
  "brief": null,
  "created_at": "2024-01-01T10:00:00Z"
}
```

### 用户反馈
**Key**: `feedback:{project_id}:{session_id}`
**类型**: List
**内容**: JSON格式的反馈对象

### 继续信号
**Key**: `writer_continue:{project_id}:{session_id}`
**类型**: String
**内容**: "true"
**过期时间**: 5分钟

### 生成状态
**Key**: `generation_status:{project_id}:{session_id}`
**类型**: String
**内容**: JSON格式的状态对象

## 前端集成指南

### 1. 启动生成流程
```javascript
// 启动序列生成
const response = await fetch('/sequence_generation/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    project_id: 'proj_123456',
    session_id: 'session_789',
    project_name: '医灵古庙文物影响评估'
  })
});
```

### 2. 监听生成进度
```javascript
// 轮询状态更新
const pollStatus = async () => {
  const response = await fetch(`/sequence_generation/${projectId}/${sessionId}/status`);
  const status = await response.json();
  
  // 更新UI显示进度
  updateProgress(status.completed_tasks, status.total_tasks);
  
  // 如果有新完成的章节，显示内容
  if (status.current_status.status === 'chapter_completed') {
    displayNewChapter(status.task_queue[status.completed_tasks - 1]);
  }
};

setInterval(pollStatus, 2000); // 每2秒检查一次
```

### 3. 提交用户反馈
```javascript
// 用户输入反馈时
const submitFeedback = async (feedbackText) => {
  await fetch(`/sequence_generation/${projectId}/${sessionId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: feedbackText,
      chapter_hint: 'current'
    })
  });
};
```

### 4. 继续生成
```javascript
// 用户确认继续生成下一章节
const continueGeneration = async () => {
  await fetch(`/sequence_generation/${projectId}/${sessionId}/continue`, {
    method: 'POST'
  });
};
```

## 错误处理

所有API端点都会返回标准的HTTP状态码：

- `200`: 成功
- `400`: 请求参数错误
- `404`: 资源不存在
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```

## 配置要求

1. **Redis服务器**: 确保Redis服务器运行在配置的地址和端口
2. **环境变量**: 设置必要的Redis连接参数
3. **依赖包**: 确保安装了所有必需的Python包

## 注意事项

1. **并发控制**: 同一个project_id和session_id组合同时只能有一个生成任务
2. **超时处理**: 如果长时间没有continue信号，系统会自动继续生成
3. **资源清理**: 完成的任务数据会在一定时间后自动清理
4. **错误恢复**: 如果生成过程中出现错误，可以通过重新启动任务来恢复
