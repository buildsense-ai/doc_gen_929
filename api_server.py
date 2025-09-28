#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gauz文档Agent - FastAPI服务器
将多Agent文档生成系统封装为RESTful API服务

提供的接口：
- POST /generate_document - 生成文档（自动管理输出目录）
- GET /health - 健康检查
- GET /status - 系统状态
- POST /set_concurrency - 设置并发参数
- GET /download/{file_id} - 下载生成的文件（备用）
- MinIO自动上传 - 主要文件分发方式
"""

import sys
import os
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

# 必须在所有其他导入之前禁用ChromaDB telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_DISABLED'] = 'True'

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import json
import re
import time
import threading
from contextvars import ContextVar

# 导入主要组件
try:
    from main import DocumentGenerationPipeline
    from config.settings import setup_logging, get_config
    from config.minio_config import get_minio_client, upload_document_files
    from one_click_pipeline import one_click_generate_document
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    sys.exit(1)

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="Gauz文档Agent API",
    description="基于多Agent架构的智能长文档生成系统API服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
pipeline: Optional[DocumentGenerationPipeline] = None
generation_tasks: Dict[str, Dict[str, Any]] = {}  # 存储任务状态
file_storage: Dict[str, str] = {}  # 存储文件映射

# ===== 日志桥接到SSE（按任务） =====

# 线程ID → 任务ID 映射（将后台执行线程产生的日志绑定到当前任务）
_thread_task_map: Dict[int, str] = {}
# 正在通过SSE流式传输的任务集合：用于避免与全局桥接器重复推送
_active_sse_tasks: set[str] = set()
# 任务SSE选项（例如是否详细输出）
_task_stream_options: Dict[str, Dict[str, Any]] = {}

# 非verbose模式下抑制的标准日志片段
_SSE_SUPPRESSED_PATTERNS = [
    "初始化完成",
    "文档生成智能速率控制器初始化",
    "已跳过Web搜索健康检查",
    "Sending request to OpenRouter",
    "Token usage:",
    "OpenRouter API调用成功",
    "OpenRouter客户端会话已关闭",
]

class _StdIOTee:
    """Duplicate writes to original stream and push per-line to task SSE logs based on thread→task映射。"""
    def __init__(self, original_stream, source: str):
        self._original = original_stream
        self._source = source  # 'stdout' or 'stderr'
        self._buffer = ''
        self._lock = threading.Lock()

    def write(self, data):
        if not isinstance(data, str):
            data = str(data)
        with self._lock:
            try:
                self._original.write(data)
                self._original.flush()
            except Exception:
                pass
            self._buffer += data
            while '\n' in self._buffer:
                line, self._buffer = self._buffer.split('\n', 1)
                try:
                    task_id = _thread_task_map.get(threading.get_ident())
                    if task_id and line.strip() != '':
                        log_manager.add_log(task_id, {
                            'type': 'info',
                            'message': line,
                            'source': self._source,
                            'sse_only': True
                        })
                except Exception:
                    pass

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass

class TaskLogHandler(logging.Handler):
    """将标准日志路由到对应任务的SSE日志队列。"""
    def emit(self, record: logging.LogRecord):
        try:
            # 避免递归：忽略本模块与uvicorn日志
            if record.name in ("api_server", "uvicorn", "uvicorn.error", "uvicorn.access"):
                return
            task_id = _thread_task_map.get(getattr(record, 'thread', None))
            if not task_id:
                return
            # 若该任务正在通过SSE流式输出，则由TaskScopedHandler负责推送，这里避免重复
            if task_id in _active_sse_tasks:
                return
            level = record.levelname.lower()
            log_type = 'error' if level == 'error' else ('warning' if level == 'warning' else 'info')
            log_entry = {
                'type': log_type,
                'message': record.getMessage(),
                'logger': record.name,
            }
            # 直接写入任务日志（内部会再写系统日志，但我们已屏蔽api_server，避免回环）
            log_manager.add_log(task_id, log_entry)
        except Exception:
            # 避免SSE因日志处理异常而中断
            pass

class TaskScopedHandler(logging.Handler):
    """将所有日志(全局)路由到指定task_id对应的SSE，不再写回系统logger，避免回环。"""
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id
    def emit(self, record: logging.LogRecord):
        try:
            if record.name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                return
            # 记录已被某个同task的处理器路由过，避免重复
            routed_task = getattr(record, '_sse_routed_task_id', None)
            if routed_task == self.task_id:
                return
            try:
                setattr(record, '_sse_routed_task_id', self.task_id)
            except Exception:
                pass
            # 非verbose模式抑制部分冗余初始化/计费日志
            opts = _task_stream_options.get(self.task_id, {})
            verbose = bool(opts.get('verbose', False))
            message_text = record.getMessage()
            if not verbose:
                for frag in _SSE_SUPPRESSED_PATTERNS:
                    if frag in message_text:
                        return
            level = record.levelname.lower()
            log_type = 'error' if level == 'error' else ('warning' if level == 'warning' else 'info')
            log_entry = {
                'type': log_type,
                'message': message_text,
                'logger': record.name,
                'sse_only': True,
            }
            log_manager.add_log(self.task_id, log_entry)
        except Exception:
            pass

# 在线程池中执行的包装器：确保线程→任务ID映射存在，便于路由日志
def _wrapped_generate_without_eval(task_id: str, query: str, project_name: str, output_dir: str):
    try:
        _thread_task_map[threading.get_ident()] = task_id
        return pipeline.generate_document_without_evaluation(query, project_name, output_dir)
    finally:
        _thread_task_map.pop(threading.get_ident(), None)

def _wrapped_one_click(task_id: str, query: str, project_name: str, output_dir: str, enable_review_and_regeneration: bool):
    try:
        _thread_task_map[threading.get_ident()] = task_id
        return one_click_generate_document(query, project_name, output_dir, enable_review_and_regeneration)
    finally:
        _thread_task_map.pop(threading.get_ident(), None)

# ===== 日志管理器 =====

class LogManager:
    """任务日志管理器"""
    def __init__(self):
        self.task_logs: Dict[str, List[Dict[str, Any]]] = {}  # 存储任务日志
        # 订阅者信息：{ task_id: [ { 'queue': asyncio.Queue, 'loop': asyncio.AbstractEventLoop } ] }
        self.log_subscribers: Dict[str, List[Dict[str, Any]]] = {}
        self.max_logs_per_task = 1000  # 每个任务最多保存的日志数量
        self.loop: Optional[asyncio.AbstractEventLoop] = None  # 主事件循环（用于跨线程安全推送）
        
    def add_log(self, task_id: str, log_entry: Dict[str, Any]):
        """添加日志条目"""
        if task_id not in self.task_logs:
            self.task_logs[task_id] = []
        
        # 添加时间戳（如果没有的话）
        if 'timestamp' not in log_entry:
            log_entry['timestamp'] = datetime.now().isoformat()
        
        # 统一去除ANSI颜色码，防止前端显示异常
        try:
            msg = str(log_entry.get('message', ''))
            msg = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", msg)
            log_entry['message'] = msg
        except Exception:
            pass

        # 去重：与上一条完全相同则跳过
        try:
            last_entry = self.task_logs[task_id][-1] if self.task_logs[task_id] else None
            if (
                last_entry
                and last_entry.get('message') == log_entry.get('message')
                and last_entry.get('logger') == log_entry.get('logger')
                and last_entry.get('type') == log_entry.get('type')
            ):
                # 跳过重复
                return
        except Exception:
            pass

        self.task_logs[task_id].append(log_entry)
        
        # 限制日志数量，避免内存溢出
        if len(self.task_logs[task_id]) > self.max_logs_per_task:
            self.task_logs[task_id] = self.task_logs[task_id][-self.max_logs_per_task:]
        
        # 推送给所有订阅者
        self._notify_subscribers(task_id, log_entry)
        
        # 同时记录到系统日志（避免递归：标记为sse_only的不再写回系统日志）
        if not log_entry.get('sse_only'):
            log_level = log_entry.get('type', 'info')
            message = f"[{task_id}] {log_entry.get('message', '')}"
            if log_level == 'error':
                logger.error(message)
            elif log_level == 'warning':
                logger.warning(message)
            else:
                logger.info(message)
    
    def _notify_subscribers(self, task_id: str, log_entry: Dict[str, Any]):
        """通知订阅者（线程安全）：使用各自的事件循环调度写入队列"""
        if task_id not in self.log_subscribers:
            return

        subscribers = list(self.log_subscribers[task_id])

        def _queue_put_safe(q: asyncio.Queue, entry: Dict[str, Any]):
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                dropped = 0
                try:
                    while dropped < 10:
                        q.get_nowait()
                        dropped += 1
                    q.put_nowait(entry)
                except Exception:
                    pass

        for sub in subscribers:
            try:
                target_loop = sub.get('loop')
                target_queue = sub.get('queue')
                if target_loop and target_loop.is_running():
                    target_loop.call_soon_threadsafe(_queue_put_safe, target_queue, log_entry)
                elif self.loop and self.loop.is_running():
                    # 回退：尝试在主循环调度（同循环时有效）
                    try:
                        self.loop.call_soon_threadsafe(_queue_put_safe, target_queue, log_entry)
                    except Exception:
                        pass
                else:
                    # 最后退化：直接调用（仅在同线程/无事件循环时）
                    _queue_put_safe(target_queue, log_entry)
            except Exception:
                pass
    
    async def subscribe_logs(self, task_id: str) -> asyncio.Queue:
        """订阅任务日志（记录订阅者事件循环）"""
        queue = asyncio.Queue(maxsize=1000)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if task_id not in self.log_subscribers:
            self.log_subscribers[task_id] = []
        self.log_subscribers[task_id].append({'queue': queue, 'loop': loop})
        return queue
    
    def unsubscribe_logs(self, task_id: str, queue: asyncio.Queue):
        """取消订阅任务日志"""
        if task_id in self.log_subscribers:
            try:
                remaining: List[Dict[str, Any]] = []
                for sub in self.log_subscribers[task_id]:
                    if sub.get('queue') is not queue:
                        remaining.append(sub)
                if remaining:
                    self.log_subscribers[task_id] = remaining
                else:
                    del self.log_subscribers[task_id]
            except Exception:
                pass
    
    def get_logs(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有日志"""
        return self.task_logs.get(task_id, [])
    
    def cleanup_task_logs(self, task_id: str):
        """清理任务日志（任务完成后调用）"""
        # 保留日志1小时，然后清理
        if task_id in self.task_logs:
            # 这里可以实现延时清理，暂时保留
            pass
        
        # 立即清理订阅者
        if task_id in self.log_subscribers:
            del self.log_subscribers[task_id]

# 创建全局日志管理器
log_manager = LogManager()

# ===== 数据模型 =====

class DocumentGenerationRequest(BaseModel):
    """文档生成请求模型"""
    query: str = Field(..., description="文档生成需求描述", min_length=1, max_length=2000)
    project_name: str = Field(..., description="项目名称，用于RAG检索", min_length=1, max_length=100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "我想生成一个关于医灵古庙的文物影响评估报告",
                "project_name": "医灵古庙"
            }
        }

class OneClickGenerationRequest(BaseModel):
    """一键串联工作流请求模型（结构→检索→成文→评审→再生→合并）"""
    query: str = Field(..., description="文档生成需求描述", min_length=1, max_length=2000)
    project_name: str = Field(..., description="项目名称，用于RAG检索", min_length=1, max_length=100)
    enable_review_and_regeneration: bool = Field(default=False, description="是否启用评审+再生+合并")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "我想生成一个关于医灵古庙的文物影响评估报告",
                "project_name": "医灵古庙",
                "enable_review_and_regeneration": False
            }
        }

class ConcurrencySettings(BaseModel):
    """并发设置模型"""
    orchestrator_workers: Optional[int] = Field(None, ge=1, le=10, description="编排代理线程数")
    react_workers: Optional[int] = Field(None, ge=1, le=10, description="检索代理线程数")
    content_workers: Optional[int] = Field(None, ge=1, le=10, description="内容生成代理线程数")
    rate_delay: Optional[float] = Field(None, ge=0.1, le=10.0, description="请求间隔时间(秒)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "orchestrator_workers": 3,
                "react_workers": 5,
                "content_workers": 4,
                "rate_delay": 1.0
            }
        }

class TaskStatus(BaseModel):
    """任务状态模型"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: str
    created_at: datetime
    updated_at: datetime
    request: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class DocumentGenerationResponse(BaseModel):
    """文档生成响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="响应消息")
    files: Optional[Dict[str, str]] = Field(None, description="生成的文件（本地下载链接）")
    minio_urls: Optional[Dict[str, str]] = Field(None, description="MinIO存储的文件下载链接")

class SystemStatus(BaseModel):
    """系统状态模型"""
    service: str
    status: str
    version: str
    active_tasks: int
    total_tasks: int
    concurrency_settings: Dict[str, Any]
    uptime: str
    minio_status: str = Field(..., description="MinIO存储服务状态")

# ===== 初始化函数 =====

@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    global pipeline
    try:
        logger.info("🚀 正在启动Gauz文档Agent API服务...")
        pipeline = DocumentGenerationPipeline()
        logger.info("✅ 文档生成流水线初始化成功")
        
        # 创建输出目录
        os.makedirs("outputs", exist_ok=True)
        os.makedirs("api_outputs", exist_ok=True)
        
        # 初始化MinIO客户端
        minio_client = get_minio_client()
        if minio_client.is_available():
            logger.info("✅ MinIO客户端连接成功")
        else:
            logger.warning("⚠️ MinIO客户端连接失败，将使用本地文件存储")
        
        logger.info("🌟 Gauz文档Agent API服务启动完成！")
        # 记录事件循环到日志管理器，便于跨线程安全推送SSE
        try:
            log_manager.loop = asyncio.get_event_loop()
        except Exception:
            pass

        # 安装日志桥接处理器（一次）
        try:
            bridge_installed = any(isinstance(h, TaskLogHandler) for h in logging.getLogger().handlers)
            if not bridge_installed:
                logging.getLogger().addHandler(TaskLogHandler())
                logger.info("✅ 已启用任务日志桥接到SSE")
        except Exception as e:
            logger.warning(f"⚠️ 启用日志桥接失败: {e}")
        
    except Exception as e:
        logger.error(f"❌ 服务启动失败: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """关闭时清理资源"""
    logger.info("🔄 正在关闭Gauz文档Agent API服务...")
    
    # 清理未完成的任务
    for task_id, task_info in generation_tasks.items():
        if task_info["status"] in ["pending", "running"]:
            task_info["status"] = "cancelled"
            task_info["updated_at"] = datetime.now()
    
    logger.info("✅ 服务关闭完成")

# ===== 核心API接口 =====

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "Gauz文档Agent API",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/logs/{task_id}/stream")
async def stream_task_logs(task_id: str):
    """实时推送任务日志流（Server-Sent Events）"""
    
    # 检查任务是否存在
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    async def log_generator():
        """日志生成器"""
        log_queue = None
        try:
            # 订阅日志
            log_queue = await log_manager.subscribe_logs(task_id)
            
            # 首先发送历史日志
            historical_logs = log_manager.get_logs(task_id)
            for log_entry in historical_logs:
                data = json.dumps(log_entry, ensure_ascii=False)
                yield f"data: {data}\n\n"
            
            # 发送当前任务状态
            task_status_log = {
                "timestamp": datetime.now().isoformat(),
                "type": "status",
                "message": f"当前任务状态: {generation_tasks[task_id]['status']}",
                "task_status": generation_tasks[task_id]['status'],
                "progress": generation_tasks[task_id].get('progress', ''),
            }
            data = json.dumps(task_status_log, ensure_ascii=False)
            yield f"data: {data}\n\n"
            
            # 实时推送新日志
            while True:
                try:
                    # 等待新的日志条目，设置超时防止连接挂起
                    log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                    data = json.dumps(log_entry, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    
                    # 仅在任务真正完成/失败，或收到显式完成信号时结束
                    task_status = generation_tasks.get(task_id, {}).get('status')
                    if task_status in ['completed', 'failed'] or log_entry.get('step') == '任务完成' or log_entry.get('type') == 'success':
                        await asyncio.sleep(1)
                        end_log = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "stream_end",
                            "message": "日志流结束"
                        }
                        data = json.dumps(end_log, ensure_ascii=False)
                        yield f"data: {data}\n\n"
                        break
                        
                except asyncio.TimeoutError:
                    # 发送心跳，保持连接活跃
                    heartbeat = {
                        "timestamp": datetime.now().isoformat(),
                        "type": "heartbeat",
                        "message": "连接正常"
                    }
                    data = json.dumps(heartbeat, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    # 心跳时也检查任务状态，避免因错误日志未触发完成而悬挂
                    task_status = generation_tasks.get(task_id, {}).get('status')
                    if task_status in ['completed', 'failed']:
                        end_log = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "stream_end",
                            "message": "日志流结束"
                        }
                        data = json.dumps(end_log, ensure_ascii=False)
                        yield f"data: {data}\n\n"
                        break
                    
        except Exception as e:
            # 发送错误信息
            error_log = {
                "timestamp": datetime.now().isoformat(),
                "type": "stream_error",
                "message": f"日志流异常: {str(e)}"
            }
            data = json.dumps(error_log, ensure_ascii=False)
            yield f"data: {data}\n\n"
            
        finally:
            # 清理订阅
            if log_queue:
                log_manager.unsubscribe_logs(task_id, log_queue)
    
    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        }
    )

@app.get("/logs/{task_id}")
async def get_task_logs(task_id: str):
    """获取任务的历史日志"""
    
    # 检查任务是否存在
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    logs = log_manager.get_logs(task_id)
    
    return {
        "task_id": task_id,
        "task_status": generation_tasks[task_id]["status"],
        "log_count": len(logs),
        "logs": logs,
        "last_updated": generation_tasks[task_id]["updated_at"].isoformat()
    }

@app.get("/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统状态"""
    if not pipeline:
        raise HTTPException(status_code=503, detail="系统未初始化")
    
    active_tasks = sum(1 for task in generation_tasks.values() 
                      if task["status"] in ["pending", "running"])
    
    # 计算运行时间（简化版本）
    uptime = "运行中"
    
    # 检查MinIO状态
    minio_client = get_minio_client()
    minio_status = "available" if minio_client.is_available() else "unavailable"
    
    return SystemStatus(
        service="Gauz文档Agent API",
        status="running",
        version="1.0.0",
        active_tasks=active_tasks,
        total_tasks=len(generation_tasks),
        concurrency_settings=pipeline.get_concurrency_settings(),
        uptime=uptime,
        minio_status=minio_status
    )

@app.post("/set_concurrency")
async def set_concurrency(settings: ConcurrencySettings):
    """设置并发参数"""
    if not pipeline:
        raise HTTPException(status_code=503, detail="系统未初始化")
    
    try:
        pipeline.set_concurrency(
            orchestrator_workers=settings.orchestrator_workers,
            react_workers=settings.react_workers,
            content_workers=settings.content_workers,
            rate_delay=settings.rate_delay
        )
        
        logger.info(f"✅ 并发设置已更新: {settings.dict()}")
        
        return {
            "status": "success",
            "message": "并发设置已更新",
            "current_settings": pipeline.get_concurrency_settings()
        }
        
    except Exception as e:
        logger.error(f"❌ 设置并发参数失败: {e}")
        raise HTTPException(status_code=500, detail=f"设置失败: {str(e)}")

# @app.post("/generate_document", response_model=DocumentGenerationResponse)
# async def generate_document(request: DocumentGenerationRequest, background_tasks: BackgroundTasks):
#     """
#     生成文档接口 - 异步处理
    
#     提交文档生成任务，返回任务ID。可通过任务ID查询进度和下载结果。
#     """
#     if not pipeline:
#         raise HTTPException(status_code=503, detail="系统未初始化")
    
#     # 生成任务ID
#     task_id = str(uuid.uuid4())
    
#     # 创建任务记录
#     task_info = {
#         "task_id": task_id,
#         "status": "pending",
#         "progress": "任务已提交，等待处理",
#         "created_at": datetime.now(),
#         "updated_at": datetime.now(),
#         "request": request.dict(),
#         "result": None,
#         "error": None
#     }
    
#     generation_tasks[task_id] = task_info
    
#     # 添加后台任务
#     background_tasks.add_task(run_document_generation, task_id, request)
    
#     logger.info(f"📝 新的文档生成任务: {task_id} - {request.query}")
    
#     return DocumentGenerationResponse(
#         task_id=task_id,
#         status="pending",
#         message=f"文档生成任务已提交，任务ID: {task_id}",
#         files=None
    # )

@app.post("/generate_document", response_model=DocumentGenerationResponse)
async def generate_document_full(request: OneClickGenerationRequest, background_tasks: BackgroundTasks):
    """
    一键式完整工作流接口（结构→检索→成文→评审→再生→合并） - 异步处理
    """
    # 生成任务ID
    task_id = str(uuid.uuid4())

    # 创建任务记录
    task_info = {
        "task_id": task_id,
        "status": "pending",
        "progress": "任务已提交，等待处理",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "request": request.dict(),
        "result": None,
        "error": None
    }
    generation_tasks[task_id] = task_info

    # 添加后台任务
    background_tasks.add_task(run_one_click_generation, task_id, request)

    logger.info(f"📝 新的完整工作流任务: {task_id} - {request.query}")

    return DocumentGenerationResponse(
        task_id=task_id,
        status="pending",
        message=f"完整工作流任务已提交，任务ID: {task_id}",
        files=None
    )

@app.post("/generate_document/stream")
async def generate_document_stream(request: OneClickGenerationRequest):
    """
    以SSE实时推送日志的文档生成接口（完整工作流）。
    - 提交后立即创建任务并启动后台执行
    - 同一HTTP连接中以Server-Sent Events推送历史与实时日志，直至任务完成
    """
    task_id = str(uuid.uuid4())
    task_info = {
        "task_id": task_id,
        "status": "pending",
        "progress": "任务已提交，等待处理",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "request": request.dict(),
        "result": None,
        "error": None
    }
    generation_tasks[task_id] = task_info

    async def event_generator():
        log_queue = None
        # 为本任务安装任务级日志处理器，捕获所有logger输出（跨线程），并加入活动集合避免重复
        root_logger = logging.getLogger()
        task_handler = TaskScopedHandler(task_id)
        root_logger.addHandler(task_handler)
        _active_sse_tasks.add(task_id)
        # 记录SSE选项（当前仅支持verbose，通过查询参数传递）
        try:
            from fastapi import Request as _FastAPIRequest  # 避免顶部导入冲突
        except Exception:
            _FastAPIRequest = None
        try:
            # 读取查询参数 verbose=true/false
            # 运行时从fastapi的request对象取（若前端传递了）
            # 若获取失败，则默认False
            verbose_flag = False
            if hasattr(request, '__dict__') and 'query' in request.__dict__:
                # 这是Pydantic模型，不包含query params
                pass
            # 通过全局app依赖注入的方式不可用，这里采用环境默认False
            _task_stream_options[task_id] = { 'verbose': verbose_flag }
        except Exception:
            _task_stream_options[task_id] = { 'verbose': False }
        try:
            # 订阅日志
            log_queue = await log_manager.subscribe_logs(task_id)

            # 启动后台完整工作流
            asyncio.create_task(run_one_click_generation(task_id, request))

            # 首帧：初始化事件
            init_evt = {
                "type": "init",
                "message": "任务已创建，开始推送日志",
                "task_id": task_id,
                "query": request.query,
                "project_name": request.project_name
            }
            yield f"data: {json.dumps(init_evt, ensure_ascii=False)}\n\n"

            # 推送历史日志（如果有）
            historical_logs = log_manager.get_logs(task_id)
            for log_entry in historical_logs:
                yield f"data: {json.dumps(log_entry, ensure_ascii=False)}\n\n"

            # 实时日志
            while True:
                try:
                    log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(log_entry, ensure_ascii=False)}\n\n"
                    if log_entry.get('type') in ['success', 'error'] or log_entry.get('step') == '任务完成':
                        await asyncio.sleep(1)
                        end_evt = {"type": "stream_end", "message": "日志流结束"}
                        yield f"data: {json.dumps(end_evt, ensure_ascii=False)}\n\n"
                        break
                except asyncio.TimeoutError:
                    heartbeat = {
                        "timestamp": datetime.now().isoformat(),
                        "type": "heartbeat",
                        "message": "连接正常"
                    }
                    yield f"data: {json.dumps(heartbeat, ensure_ascii=False)}\n\n"
        finally:
            if log_queue:
                log_manager.unsubscribe_logs(task_id, log_queue)
            try:
                root_logger.removeHandler(task_handler)
            except Exception:
                pass
            try:
                _active_sse_tasks.discard(task_id)
            except Exception:
                pass
            try:
                _task_stream_options.pop(task_id, None)
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        }
    )

@app.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in generation_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_info = generation_tasks[task_id]
    
    return TaskStatus(
        task_id=task_info["task_id"],
        status=task_info["status"],
        progress=task_info["progress"],
        created_at=task_info["created_at"],
        updated_at=task_info["updated_at"],
        request=task_info.get("request"),
        result=task_info["result"],
        error=task_info["error"]
    )

@app.get("/tasks")
async def list_tasks(limit: int = 20, status_filter: Optional[str] = None):
    """获取任务列表"""
    tasks = list(generation_tasks.values())
    
    # 状态过滤
    if status_filter:
        tasks = [task for task in tasks if task["status"] == status_filter]
    
    # 按时间排序，最新的在前
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    
    # 限制数量
    tasks = tasks[:limit]
    
    return {
        "total": len(generation_tasks),
        "filtered": len(tasks),
        "tasks": tasks
    }

@app.get("/download/{file_id}")
async def download_file(file_id: str):
    """下载生成的文件"""
    if file_id not in file_storage:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    file_path = file_storage[file_id]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件已被删除")
    
    filename = os.path.basename(file_path)
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )

# ===== 后台任务函数 =====

async def run_document_generation(task_id: str, request: DocumentGenerationRequest):
    """后台执行文档生成任务"""
    task_info = generation_tasks[task_id]
    # 将当前线程绑定到任务，用于日志桥接
    try:
        _thread_task_map[threading.get_ident()] = task_id
    except Exception:
        pass
    
    try:
        # 推送开始日志
        log_manager.add_log(task_id, {
            "type": "info",
            "message": "文档生成任务已启动",
            "progress": 0,
            "step": "任务初始化",
            "query": request.query,
            "project_name": request.project_name
        })
        
        # 更新状态为运行中
        task_info["status"] = "running"
        task_info["progress"] = "正在生成文档结构..."
        task_info["updated_at"] = datetime.now()
        
        # 推送状态更新
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "正在初始化文档生成流水线...",
            "progress": 5,
            "step": "流水线初始化"
        })
        
        logger.info(f"🚀 开始执行文档生成任务: {task_id}")
        
        # 创建任务专用输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"api_outputs/{task_id}_{timestamp}"
        
        # 推送目录创建日志
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": f"创建输出目录: {output_dir}",
            "progress": 10,
            "step": "目录创建",
            "output_dir": output_dir
        })
        
        # 推送文档生成开始
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "开始执行多Agent文档生成流水线...",
            "progress": 15,
            "step": "多Agent协作"
        })
        
        # 在新的线程中运行同步代码（API模式，跳过质量评估）
        loop = asyncio.get_event_loop()
        result_files = await loop.run_in_executor(
            None,
            _wrapped_generate_without_eval,
            task_id,
            request.query,
            request.project_name,
            output_dir
        )
        
        # 推送文档生成完成
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "文档内容生成完成，正在处理文件...",
            "progress": 70,
            "step": "文件处理",
            "generated_files": list(result_files.keys())
        })
        
        # 生成本地文件下载链接
        file_links = {}
        for file_type, file_path in result_files.items():
            if file_type != 'output_directory' and os.path.exists(file_path):
                file_id = str(uuid.uuid4())
                file_storage[file_id] = file_path
                file_links[file_type] = f"/download/{file_id}"
        
        # 上传文件到MinIO
        task_info["progress"] = "正在上传文件到MinIO..."
        task_info["updated_at"] = datetime.now()
        
        # 推送MinIO上传开始
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "开始上传文件到云存储(MinIO)...",
            "progress": 80,
            "step": "云存储上传"
        })
        
        minio_urls = {}
        try:
            logger.info(f"📤 开始上传文件到MinIO: {task_id}")
            minio_urls = upload_document_files(result_files, task_id)
            if minio_urls:
                logger.info(f"✅ MinIO上传成功: {len(minio_urls)} 个文件")
                log_manager.add_log(task_id, {
                    "type": "success",
                    "message": f"云存储上传成功，共上传 {len(minio_urls)} 个文件",
                    "progress": 90,
                    "step": "上传完成",
                    "minio_files": len(minio_urls)
                })
            else:
                logger.warning(f"⚠️ MinIO上传失败，仅提供本地下载")
                log_manager.add_log(task_id, {
                    "type": "warning",
                    "message": "云存储上传失败，仅提供本地下载",
                    "progress": 85,
                    "step": "上传失败"
                })
        except Exception as e:
            logger.error(f"❌ MinIO上传异常: {e}")
            log_manager.add_log(task_id, {
                "type": "error",
                "message": f"云存储上传异常: {str(e)}",
                "progress": 85,
                "step": "上传异常",
                "error": str(e)
            })
        
        # 更新任务状态为完成
        task_info["status"] = "completed"
        task_info["progress"] = "文档生成和上传完成"
        task_info["result"] = {
            "files": file_links,
            "minio_urls": minio_urls,
            "output_directory": result_files.get("output_directory"),
            "generation_time": datetime.now().isoformat(),
            "storage_info": {
                "local_files": len(file_links),
                "minio_files": len(minio_urls),
                "total_size_mb": sum(
                    os.path.getsize(file_path) / (1024 * 1024) 
                    for file_path in result_files.values() 
                    if file_path != result_files.get("output_directory") and os.path.exists(file_path)
                )
            }
        }
        task_info["updated_at"] = datetime.now()
        
        # 推送任务完成日志
        log_manager.add_log(task_id, {
            "type": "success",
            "message": "✅ 文档生成任务完成！",
            "progress": 100,
            "step": "任务完成",
            "result": {
                "minio_urls": minio_urls,
                "local_files": file_links,
                "storage_info": task_info["result"]["storage_info"]
            }
        })
        
        logger.info(f"✅ 文档生成任务完成: {task_id}")
        
    except Exception as e:
        # 推送错误日志
        log_manager.add_log(task_id, {
            "type": "error",
            "message": f"❌ 文档生成任务失败: {str(e)}",
            "progress": 0,
            "step": "任务失败",
            "error": str(e)
        })
        
        # 更新任务状态为失败
        task_info["status"] = "failed"
        task_info["progress"] = f"生成失败: {str(e)}"
        task_info["error"] = str(e)
        task_info["updated_at"] = datetime.now()
        
        logger.error(f"❌ 文档生成任务失败: {task_id} - {e}")
    finally:
        # 任务完成后清理日志订阅者（但保留日志1小时）
        try:
            _thread_task_map.pop(threading.get_ident(), None)
        except Exception:
            pass
        log_manager.cleanup_task_logs(task_id)


async def run_one_click_generation(task_id: str, request: OneClickGenerationRequest):
    """后台执行一键工作流任务（包含评审/再生/合并）"""
    task_info = generation_tasks[task_id]
    # 将当前线程绑定到任务，用于日志桥接
    try:
        _thread_task_map[threading.get_ident()] = task_id
    except Exception:
        pass
    try:
        # 将stdout/stderr tee到任务SSE
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = _StdIOTee(original_stdout, 'stdout')
        sys.stderr = _StdIOTee(original_stderr, 'stderr')
        # 启动日志
        log_manager.add_log(task_id, {
            "type": "info",
            "message": "完整工作流任务已启动",
            "progress": 0,
            "step": "任务初始化",
            "query": request.query,
            "project_name": request.project_name,
            "enable_review_and_regeneration": request.enable_review_and_regeneration,
        })

        task_info["status"] = "running"
        task_info["progress"] = "正在执行完整工作流..."
        task_info["updated_at"] = datetime.now()

        # 创建输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"api_outputs/{task_id}_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)

        log_manager.add_log(task_id, {
            "type": "progress",
            "message": f"创建输出目录: {output_dir}",
            "progress": 10,
            "step": "目录创建",
            "output_dir": output_dir
        })

        # 执行一键工作流（同步转线程）
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _wrapped_one_click,
            task_id,
            request.query,
            request.project_name,
            output_dir,
            request.enable_review_and_regeneration,
        )

        # 整理产物
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "工作流完成，正在处理产物...",
            "progress": 75,
            "step": "文件处理",
        })

        # 归集主要文件
        files_to_publish: Dict[str, str] = {}
        try:
            final_md = result.get("final_document")
            if final_md and os.path.exists(final_md):
                files_to_publish["final_markdown"] = final_md

            stages = result.get("stages", {})
            # 结构/检索/成文
            if stages.get("structure_and_guides", {}).get("file"):
                files_to_publish["step1_guide_json"] = stages["structure_and_guides"]["file"]
            if stages.get("retrieval_enrichment", {}).get("file"):
                files_to_publish["step2_enriched_json"] = stages["retrieval_enrichment"]["file"]
            if stages.get("content_generation", {}).get("json"):
                files_to_publish["generated_json"] = stages["content_generation"]["json"]
            if stages.get("content_generation", {}).get("markdown"):
                files_to_publish["generated_markdown"] = stages["content_generation"]["markdown"]
            # 评审
            if stages.get("quality_review", {}).get("issues_file"):
                files_to_publish["quality_issues_json"] = stages["quality_review"]["issues_file"]
            # 再生/合并
            if stages.get("regeneration", {}).get("file"):
                files_to_publish["regenerated_sections_json"] = stages["regeneration"]["file"]
            if stages.get("merge_and_render", {}).get("merged_json"):
                files_to_publish["merged_json"] = stages["merge_and_render"]["merged_json"]
            if stages.get("merge_and_render", {}).get("merged_markdown"):
                files_to_publish["merged_markdown"] = stages["merge_and_render"]["merged_markdown"]
            if stages.get("merge_and_render", {}).get("summary"):
                files_to_publish["merge_summary_md"] = stages["merge_and_render"]["summary"]
        except Exception:
            pass

        # 生成本地下载链接
        file_links = {}
        for file_type, file_path in files_to_publish.items():
            if os.path.exists(file_path):
                file_id = str(uuid.uuid4())
                file_storage[file_id] = file_path
                file_links[file_type] = f"/download/{file_id}"

        # 上传到MinIO
        task_info["progress"] = "正在上传文件到MinIO..."
        task_info["updated_at"] = datetime.now()
        log_manager.add_log(task_id, {
            "type": "progress",
            "message": "开始上传文件到云存储(MinIO)...",
            "progress": 85,
            "step": "云存储上传"
        })

        minio_urls = upload_document_files(files_to_publish, task_id)

        # 完成
        task_info["status"] = "completed"
        task_info["progress"] = "完整工作流完成"
        task_info["result"] = {
            "files": file_links,
            "minio_urls": minio_urls,
            "output_directory": result.get("output_directory"),
            "stages": result.get("stages"),
            "final_document": result.get("final_document"),
        }
        task_info["updated_at"] = datetime.now()

        log_manager.add_log(task_id, {
            "type": "success",
            "message": "✅ 完整工作流任务完成！",
            "progress": 100,
            "step": "任务完成",
            "result": {
                "minio_urls": minio_urls,
                "local_files": file_links,
                "final_document": result.get("final_document"),
            }
        })

    except Exception as e:
        log_manager.add_log(task_id, {
            "type": "error",
            "message": f"❌ 完整工作流任务失败: {str(e)}",
            "progress": 0,
            "step": "任务失败",
            "error": str(e)
        })
        task_info["status"] = "failed"
        task_info["progress"] = f"生成失败: {str(e)}"
        task_info["error"] = str(e)
        task_info["updated_at"] = datetime.now()
        logger.error(f"❌ 完整工作流任务失败: {task_id} - {e}")
    finally:
        try:
            _thread_task_map.pop(threading.get_ident(), None)
        except Exception:
            pass
        # 恢复stdout/stderr
        try:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
        except Exception:
            pass
        log_manager.cleanup_task_logs(task_id)

# ===== 字段搜索接口 =====

class FieldSearchRequest(BaseModel):
    """字段搜索请求模型"""
    query: str = Field(..., description="搜索查询文本", min_length=1, max_length=1000)
    project_name: str = Field(..., description="项目名称", min_length=1, max_length=100)
    search_type: str = Field(default="hybrid", description="搜索类型（hybrid/vector/bm25）")
    initial_top_k: int = Field(default=20, ge=1, le=100, description="初步检索返回的结果数量")
    final_top_k: int = Field(default=10, ge=1, le=50, description="重排序后最终返回的结果数量")
    chunk_type: Optional[str] = Field(default=None, description="指定搜索的字段类型：page_text/detailed_description/engineering_details/None")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "地理位置",
                "project_name": "医灵古庙",
                "search_type": "hybrid",
                "initial_top_k": 20,
                "final_top_k": 10,
                "chunk_type": "page_text"
            }
        }

class FieldSearchResponse(BaseModel):
    """字段搜索响应模型"""
    success: bool = Field(..., description="搜索是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="搜索结果数据")
    search_params: Dict[str, Any] = Field(..., description="搜索参数")
    processing_time: float = Field(..., description="处理时间（秒）")

# @app.post("/api/v1/search_by_field", response_model=FieldSearchResponse)
# async def search_by_field(request: FieldSearchRequest):
#     """
#     按字段类型分开召回搜索接口
    
#     支持按字段类型分开召回文本和图片内容，支持重排序
#     """
#     start_time = time.time()
    
#     try:
#         logger.info(f"🔍 字段搜索请求: {request.query} (项目: {request.project_name}, 字段类型: {request.chunk_type})")
        
#         # 验证字段类型
#         valid_chunk_types = ["page_text", "detailed_description", "engineering_details", None]
#         if request.chunk_type not in valid_chunk_types:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"无效的字段类型: {request.chunk_type}。有效类型: {valid_chunk_types}"
#             )
        
#         # 根据字段类型构造不同的搜索策略
#         search_strategy = {
#             "text_search": {
#                 "chunk_type": "page_text",
#                 "description": "页面文本内容搜索"
#             },
#             "image_search": {
#                 "chunk_type": "detailed_description", 
#                 "description": "图片详细描述搜索"
#             },
#             "engineering_search": {
#                 "chunk_type": "engineering_details",
#                 "description": "工程技术细节搜索"
#             }
#         }
        
#         # 根据chunk_type确定搜索策略
#         if request.chunk_type == "page_text":
#             current_strategy = search_strategy["text_search"]
#         elif request.chunk_type == "detailed_description":
#             current_strategy = search_strategy["image_search"]
#         elif request.chunk_type == "engineering_details":
#             current_strategy = search_strategy["engineering_search"]
#         else:
#             # 如果未指定字段类型，返回所有类型的搜索结果
#             current_strategy = None
        
#         # 模拟搜索结果（实际实现中这里应该调用真实的RAG检索服务）
#         mock_results = {
#             "page_text_results": [],
#             "detailed_description_results": [],
#             "engineering_details_results": [],
#             "search_metadata": {
#                 "query": request.query,
#                 "project_name": request.project_name,
#                 "search_type": request.search_type,
#                 "initial_top_k": request.initial_top_k,
#                 "final_top_k": request.final_top_k,
#                 "chunk_type": request.chunk_type,
#                 "strategy": current_strategy["description"] if current_strategy else "全字段搜索"
#             }
#         }
        
#         # 根据字段类型生成相应的模拟数据
#         if request.chunk_type == "page_text" or request.chunk_type is None:
#             mock_results["page_text_results"] = [
#                 {
#                     "page_number": 1,
#                     "content": f"关于{request.query}的详细文本描述...",
#                     "similarity": 0.95,
#                     "rerank_score": 0.92,
#                     "images": ["image1.jpg", "image2.jpg"]
#                 },
#                 {
#                     "page_number": 2,
#                     "content": f"{request.query}相关的历史背景信息...",
#                     "similarity": 0.88,
#                     "rerank_score": 0.85,
#                     "images": ["image3.jpg"]
#                 }
#             ]
        
#         if request.chunk_type == "detailed_description" or request.chunk_type is None:
#             mock_results["detailed_description_results"] = [
#                 {
#                     "image_url": "image1.jpg",
#                     "detailed_description": f"图片展示了{request.query}的详细特征...",
#                     "similarity": 0.93,
#                     "rerank_score": 0.90,
#                     "page_number": 1
#                 },
#                 {
#                     "image_url": "image2.jpg", 
#                     "detailed_description": f"该图片描述了{request.query}的具体细节...",
#                     "similarity": 0.87,
#                     "rerank_score": 0.84,
#                     "page_number": 1
#                 }
#             ]
        
#         if request.chunk_type == "engineering_details" or request.chunk_type is None:
#             mock_results["engineering_details_results"] = [
#                 {
#                     "image_url": "image1.jpg",
#                     "engineering_details": f"{request.query}的工程技术参数和规格...",
#                     "similarity": 0.91,
#                     "rerank_score": 0.89,
#                     "page_number": 1
#                 }
#             ]
        
#         processing_time = time.time() - start_time
        
#         logger.info(f"✅ 字段搜索成功: 耗时 {processing_time:.2f}s")
        
#         return FieldSearchResponse(
#             success=True,
#             message="字段搜索成功",
#             data=mock_results,
#             search_params={
#                 "query": request.query,
#                 "project_name": request.project_name,
#                 "search_type": request.search_type,
#                 "initial_top_k": request.initial_top_k,
#                 "final_top_k": request.final_top_k,
#                 "chunk_type": request.chunk_type
#             },
#             processing_time=processing_time
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         processing_time = time.time() - start_time
#         logger.error(f"❌ 字段搜索失败: {e}")
        
#         return FieldSearchResponse(
#             success=False,
#             message=f"字段搜索失败: {str(e)}",
#             data=None,
#             search_params={
#                 "query": request.query,
#                 "project_name": request.project_name,
#                 "search_type": request.search_type,
#                 "initial_top_k": request.initial_top_k,
#                 "final_top_k": request.final_top_k,
#                 "chunk_type": request.chunk_type
#             },
#             processing_time=processing_time
#         )

# ===== 启动服务器 =====

def start_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """启动FastAPI服务器"""
    print("🚀 启动Gauz文档Agent API服务器...")
    print(f"📊 服务地址: http://{host}:{port}")
    print(f"📖 API文档: http://{host}:{port}/docs")
    print(f"📚 ReDoc文档: http://{host}:{port}/redoc")
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Gauz文档Agent API服务器")
    parser.add_argument("--host", default="0.0.0.0", help="服务器主机地址")
    parser.add_argument("--port", type=int, default=8002, help="服务器端口")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    
    args = parser.parse_args()
    start_server(args.host, args.port, args.reload)