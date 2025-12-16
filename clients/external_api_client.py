#!/usr/bin/env python3
"""
外部API客户端

调用远程API服务，提供模板搜索和文档搜索功能
"""

import json
import time
import logging
import sys
import os
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

# 加载环境变量
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

@dataclass
class TemplateSearchRequest:
    """模板搜索请求"""
    query: str

@dataclass 
class DocumentSearchRequest:
    """文档搜索请求"""
    query_text: str
    project_name: str = "default"
    top_k: int = 5
    content_type: str = "all"

class ExternalAPIClient:
    """外部API客户端"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # API服务器配置
        self.template_api_url = os.getenv("TEMPLATE_API_URL", "http://43.139.19.144:8003")
        self.rag_api_url = os.getenv("RAG_API_URL", "http://43.139.19.144:1234")
        self.timeout = int(os.getenv("API_TIMEOUT", "60"))
        self.skip_health_check = os.getenv("SKIP_HEALTH_CHECK", "false").lower() == "true"
        
        # 服务可用性标记
        self.template_available = False
        self.document_available = False
        
        # 初始化并检查服务状态
        if self.skip_health_check:
            self.template_available = True
            self.document_available = True
            self.logger.info("🔄 已跳过健康检查，假设所有服务可用")
        else:
            self._check_service_availability()
        
        self.logger.info(f"ExternalAPIClient 初始化完成")
        self.logger.info(f"模板搜索服务: {self.template_api_url} - {'可用' if self.template_available else '不可用'}")
        self.logger.info(f"RAG检索服务: {self.rag_api_url} - {'可用' if self.document_available else '不可用'}")
    
    def _check_service_availability(self):
        """检查服务可用性"""
        try:
            # 同步方式检查服务状态
            import requests
            
            # 检查模板搜索服务
            try:
                response = requests.options(f"{self.template_api_url}/template_search", timeout=5)
                if response.status_code in [200, 405, 404]:
                    self.template_available = True
                    self.logger.info("✅ 模板搜索服务可达")
            except Exception as e:
                self.logger.warning(f"⚠️ 模板搜索服务检查失败: {e}")
                # 即使检查失败，也假设服务可用，在实际调用时再处理错误
                self.template_available = True
                self.logger.info("🔄 假设模板搜索服务可用，将在调用时验证")
            
            # 检查RAG检索服务（使用轻量级POST请求）
            try:
                test_data = {
                    "query": "health_check",
                    "project_id": "test",
                    "top_k": 1,
                    "use_refine": False,
                    "use_graph_expansion": False
                }
                response = requests.post(
                    f"{self.rag_api_url}/search", 
                    json=test_data,
                    timeout=10
                )
                if response.status_code == 200:
                    self.document_available = True
                    self.logger.info("✅ RAG检索服务可达")
                else:
                    self.logger.warning(f"⚠️ RAG检索服务响应异常: {response.status_code}")
                    self.document_available = True
                    self.logger.info("🔄 假设RAG检索服务可用，将在调用时验证")
            except Exception as e:
                self.logger.warning(f"⚠️ RAG检索服务检查失败: {e}")
                # 即使检查失败，也假设服务可用
                self.document_available = True
                self.logger.info("🔄 假设RAG检索服务可用，将在调用时验证")
                
        except ImportError:
            self.logger.error("❌ 缺少requests库，无法检查服务状态")
            # 如果没有requests库，直接假设服务可用
            self.template_available = True
            self.document_available = True
            self.logger.info("🔄 跳过服务检查，假设服务可用")
    
    async def _make_api_request(self, base_url: str, endpoint: str, data: dict, max_retries: int = 3) -> Optional[dict]:
        """
        发送API请求
        
        Args:
            base_url: API基础URL
            endpoint: API端点
            data: 请求数据
            max_retries: 最大重试次数
            
        Returns:
            Optional[dict]: API响应，失败时返回None
        """
        url = f"{base_url}{endpoint}"
        self.logger.debug(f"🔗 请求URL: {url}")
        self.logger.debug(f"📦 请求数据: {data}")
        
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=data) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            error_text = await response.text()
                            self.logger.error(f"❌ API请求失败 (URL: {url}, 状态码: {response.status}): {error_text}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1 * (attempt + 1))  # 指数退避
                            continue
                            
            except asyncio.TimeoutError:
                self.logger.error(f"❌ API请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                self.logger.error(f"❌ API请求异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
        
        return None
    
    def check_service_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """检查服务状态"""
        if force_refresh:
            self._check_service_availability()
            
        return {
            "service": "外部API客户端",
            "status": "running" if (self.template_available or self.document_available) else "degraded",
            "version": "3.0.0-api",
            "template_api_url": self.template_api_url,
            "rag_api_url": self.rag_api_url,
            "tools": {
                "template_search": {
                    "available": self.template_available,
                    "endpoint": "/template_search"
                },
                "document_search": {
                    "available": self.document_available,
                    "endpoint": "/search"
                }
            },
            "mode": "api_client"
        }
    
    def search_top3_templates(self, query: str, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
        """
        搜索前3个推荐模板（同步版本，用于非异步环境）
        
        Args:
            query: 搜索查询
            max_retries: 最大重试次数
            
        Returns:
            Optional[List[Dict[str, Any]]]: 
                成功时返回包含3个模板的列表，每个模板包含：
                - template_id: 模板ID
                - template_name: 模板名称
                - description: 模板描述
                - score: 相关性分数
                失败时返回 None
        """
        if not self.template_available:
            self.logger.error("❌ 模板搜索服务不可用")
            return None
        
        try:
            # 检查是否已经在事件循环中
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在运行中的事件循环，使用 run_coroutine_threadsafe 或者提示使用异步版本
                self.logger.warning("⚠️ 检测到运行中的事件循环，请使用 search_top3_templates_async() 方法")
                return None
        except RuntimeError:
            pass
        
        # 使用同步方式调用异步函数
        return asyncio.run(self._search_top3_templates_async(query, max_retries))
    
    async def search_top3_templates_async(self, query: str, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
        """
        搜索前3个推荐模板（异步版本，用于FastAPI等异步环境）
        
        Args:
            query: 搜索查询
            max_retries: 最大重试次数
            
        Returns:
            Optional[List[Dict[str, Any]]]: 
                成功时返回包含3个模板的列表，每个模板包含：
                - template_id: 模板ID
                - template_name: 模板名称
                - description: 模板描述
                - score: 相关性分数
                失败时返回 None
        """
        if not self.template_available:
            self.logger.error("❌ 模板搜索服务不可用")
            return None
        
        return await self._search_top3_templates_async(query, max_retries)
    
    async def _search_top3_templates_async(self, query: str, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
        """异步搜索前3个推荐模板"""
        try:
            self.logger.info(f"🔍 API搜索前3个推荐模板: {query}")
            start_time = time.time()
            
            # 构造请求数据
            request_data = {"query": query, "top_k": 3}
            
            # 调用API
            response = await self._make_api_request(self.template_api_url, "/search_top3_templates", request_data, max_retries)
            
            if response is None:
                self.logger.error("❌ 搜索前3个模板API调用失败")
                return None
            
            # 检查响应格式
            if response.get("success"):
                templates = response.get("data", [])
                
                if not templates or not isinstance(templates, list):
                    self.logger.info(f"📭 未找到推荐模板")
                    return None
                
                response_time = time.time() - start_time
                self.logger.info(f"✅ 搜索前3个模板成功: 耗时 {response_time:.2f}s, 找到 {len(templates)} 个模板")
                return templates
            else:
                self.logger.error(f"❌ API返回失败: {response.get('message', '未知错误')}")
                return None
            
        except Exception as e:
            self.logger.error(f"❌ 搜索前3个模板失败: {e}")
            return None
    
    def template_search(self, query: str, max_retries: int = 3) -> Optional[Any]:
        """
        模板搜索
        
        Args:
            query: 搜索查询
            max_retries: 最大重试次数
            
        Returns:
            Optional[Any]:
                - 新接口：{"content": 模板内容字符串, "template_id": 可选ID, "raw": 原始响应}
                - 兼容旧接口：{"content": 模板内容字符串, "template_id": None, "raw": 原始响应}
                - 失败时返回 None
        """
        if not self.template_available:
            self.logger.error("❌ 模板搜索服务不可用")
            return None
        
        # 使用同步方式调用异步函数
        return asyncio.run(self._template_search_async(query, max_retries))
    
    async def _template_search_async(self, query: str, max_retries: int = 3) -> Optional[Any]:
        """异步模板搜索"""
        try:
            self.logger.info(f"🔍 API模板搜索: {query}")
            start_time = time.time()
            
            # 构造请求数据
            request_data = {"query": query}
            
            # 调用API
            response = await self._make_api_request(self.template_api_url, "/template_search", request_data, max_retries)
            
            if response is None:
                self.logger.error("❌ 模板搜索API调用失败")
                return None
            
            # 检查响应格式并提取模板内容
            if response.get("success"):
                # 新的API响应格式: {"success": true, "data": "...", "template_id": "...", "message": "..."}
                template_content = response.get("data", "")
                template_id = response.get("template_id")
                
                # 检查是否真的找到了模板（而不是"未找到匹配模板"的消息）
                if "未找到" in template_content or "没有找到" in template_content or "建议尝试" in template_content:
                    response_time = time.time() - start_time
                    self.logger.info(f"📭 模板搜索未找到匹配结果: {template_content}")
                    return None
                
                response_time = time.time() - start_time
                self.logger.info(f"✅ 模板搜索成功: 耗时 {response_time:.2f}s, 内容长度 {len(template_content)} 字符, 模板ID: {template_id}")
                return {"content": template_content, "template_id": template_id, "raw": response}
            else:
                # 旧的API响应格式: {"template_content": "..."}
                template_content = response.get("template_content", "")
                
                if not template_content:
                    response_time = time.time() - start_time
                    self.logger.info(f"📭 模板搜索未返回内容")
                    return None
                
                response_time = time.time() - start_time
                self.logger.info(f"✅ 模板搜索成功: 耗时 {response_time:.2f}s, 内容长度 {len(template_content)} 字符")
                return {"content": template_content, "template_id": None, "raw": response}
            
        except Exception as e:
            self.logger.error(f"❌ 模板搜索失败: {e}")
            return None
    
    def get_template_by_id(self, guide_id: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        根据模板ID获取模板
        
        Args:
            guide_id: 模板ID
            max_retries: 最大重试次数
            
        Returns:
            Optional[Dict[str, Any]]: 模板内容，失败时返回None
        """
        if not self.template_available:
            self.logger.error("❌ 模板服务不可用")
            return None
        
        # 使用同步方式调用异步函数
        return asyncio.run(self._get_template_by_id_async(guide_id, max_retries))
    
    async def _get_template_by_id_async(self, guide_id: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """异步根据ID获取模板"""
        try:
            self.logger.info(f"🔍 根据ID获取模板: {guide_id}")
            start_time = time.time()
            
            url = f"{self.template_api_url}/template/{guide_id}"
            
            for attempt in range(max_retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=self.timeout)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                result = await response.json()
                                response_time = time.time() - start_time
                                
                                if result.get("success"):
                                    template_content = result.get("data", "")
                                    self.logger.info(f"✅ 获取模板成功: 耗时 {response_time:.2f}s, 模板ID: {guide_id}")
                                    return {"content": template_content, "template_id": guide_id, "raw": result}
                                else:
                                    self.logger.error(f"❌ 获取模板失败: {result.get('message', '未知错误')}")
                                    return None
                            elif response.status == 404:
                                self.logger.error(f"❌ 模板不存在: {guide_id}")
                                return None
                            else:
                                error_text = await response.text()
                                self.logger.error(f"❌ 获取模板失败 (状态码: {response.status}): {error_text}")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(1 * (attempt + 1))
                                continue
                                
                except asyncio.TimeoutError:
                    self.logger.error(f"❌ 获取模板超时 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
                except Exception as e:
                    self.logger.error(f"❌ 获取模板异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取模板失败: {e}")
            return None
    
    def document_search(self, query: str, project_name: str) -> Optional[Dict[str, List]]:
        """
        RAG检索搜索（三级并行检索 + Bundle聚合）
        
        使用新的Bundle架构进行检索：
        - 并行检索三个层级：Conversations、Facts、Topics
        - 构建关系图并找出连通分量
        - 返回多个Bundles（每个Bundle包含相关的conversations, facts, topics）
        
        Args:
            query: 搜索查询
            project_name: 项目名称（作为project_id）
            
        Returns:
            Optional[Dict[str, List]]: 包含bundles、short_term_memory、recent_turns的搜索结果，失败时返回None
        """
        if not self.document_available:
            self.logger.error("❌ RAG检索服务不可用")
            return None
        
        # 尝试获取现有事件循环，如果没有则创建新的
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，使用同步requests库代替
                import requests
                return self._document_search_sync(query, project_name)
            else:
                return loop.run_until_complete(self._document_search_async(query, project_name))
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(self._document_search_async(query, project_name))
    
    def _document_search_sync(self, query: str, project_name: str, 
                             max_retries: int = 3) -> Optional[Dict[str, List]]:
        """同步RAG检索搜索（使用requests库）"""
        try:
            import requests
            
            self.logger.info(f"📄 RAG检索搜索(同步): {query} (项目: {project_name})")
            start_time = time.time()
            
            # 构造请求数据
            request_data = {
                "query": query,
                "project_id": project_name,
                "top_k": 20,
                "use_refine": False,
                "use_graph_expansion": False
            }
            
            url = f"{self.rag_api_url}/search"
            self.logger.debug(f"🔗 请求URL: {url}")
            self.logger.debug(f"📦 请求数据: {request_data}")
            
            # 发送POST请求
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=request_data, timeout=self.timeout)
                    
                    if response.status_code == 200:
                        result = response.json()
                        response_time = time.time() - start_time
                        
                        bundles = result.get("bundles", [])
                        total_bundles = result.get("total_bundles", 0)
                        
                        self.logger.info(f"✅ RAG检索成功: 耗时 {response_time:.2f}s, 获得 {total_bundles} 个Bundles")
                        return result
                    else:
                        error_text = response.text
                        self.logger.error(f"❌ API请求失败 (URL: {url}, 状态码: {response.status_code}): {error_text}")
                        if attempt < max_retries - 1:
                            time.sleep(1 * (attempt + 1))
                        continue
                        
                except requests.exceptions.Timeout:
                    self.logger.error(f"❌ API请求超时 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))
                except Exception as e:
                    self.logger.error(f"❌ API请求异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))
            
            self.logger.error("❌ RAG检索API调用失败（所有重试已用尽）")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ RAG检索失败: {e}")
            return None
    
    async def _document_search_async(self, query: str, project_name: str, 
                                   max_retries: int = 3) -> Optional[Dict[str, List]]:
        """异步RAG检索搜索（使用三级并行检索 + Bundle聚合）"""
        try:
            self.logger.info(f"📄 RAG检索搜索(异步): {query} (项目: {project_name})")
            start_time = time.time()
            
            # 构造请求数据 - 使用新API格式
            request_data = {
                "query": query,
                "project_id": project_name,  # 使用project_id而不是project_name
                "top_k": 20,
                "use_refine": False,
                "use_graph_expansion": False
            }
            
            # 调用RAG检索API（新端点：/search）
            response = await self._make_api_request(self.rag_api_url, "/search", request_data, max_retries)
            
            if response is None:
                self.logger.error("❌ RAG检索API调用失败")
                return None
            
            response_time = time.time() - start_time
            
            # 新API返回格式包含 bundles, short_term_memory, recent_turns等
            bundles = response.get("bundles", [])
            total_bundles = response.get("total_bundles", 0)
            
            self.logger.info(f"✅ RAG检索成功: 耗时 {response_time:.2f}s, 获得 {total_bundles} 个Bundles")
            
            # 返回完整响应供后续处理
            return response
            
        except Exception as e:
            self.logger.error(f"❌ RAG检索失败: {e}")
            return None
    


    def get_service_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "active_requests": 0,  # API调用无本地并发统计
            "total_requests": 0,
            "available_template_tools": 1 if self.template_available else 0,
            "available_rag_tools": 1 if self.document_available else 0,  # 现在有1个RAG工具
            "mode": "api_client",
            "template_api_url": self.template_api_url,
            "rag_api_url": self.rag_api_url
        }
    
    def close(self):
        """关闭客户端"""
        self.logger.info("ExternalAPIClient 关闭（API客户端无需特殊清理）")

# 单例模式的全局客户端实例
_global_external_client = None

def get_external_api_client() -> ExternalAPIClient:
    """获取全局外部API客户端实例"""
    global _global_external_client
    if _global_external_client is None:
        _global_external_client = ExternalAPIClient()
    return _global_external_client