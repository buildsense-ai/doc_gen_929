"""
Web 搜索客户端
用于调用外部 Web 搜索 API 获取实时信息
"""

import requests
import os
import json
import logging
from typing import Dict, List, Optional, Any
import time

class WebSearchClient:
    """Web 搜索客户端"""
    
    def __init__(self, base_url: str = "http://43.139.19.144:8005"):
        self.base_url = base_url.rstrip('/')
        self.search_endpoint = f"{self.base_url}/search"
        self.logger = logging.getLogger(__name__)
        
        # 默认搜索引擎配置
        self.default_engines = ["serp"]
        self.max_retries = 3
        self.timeout = 30
        
    def search(self, query: str, engines: List[str] = None, max_results: int = 10) -> Optional[Dict[str, Any]]:
        """
        执行 Web 搜索
        
        Args:
            query: 搜索查询词
            engines: 搜索引擎列表，默认使用 ["serp"]
            max_results: 最大结果数量
            
        Returns:
            搜索结果字典，失败时返回 None
        """
        if not query or not query.strip():
            self.logger.error("搜索查询不能为空")
            return None
            
        engines = engines or self.default_engines
        
        request_data = {
            "query": query.strip(),
            "engines": engines
        }
        
        self.logger.info(f"🌐 Web搜索: {query} (引擎: {engines})")
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                
                response = requests.post(
                    self.search_endpoint,
                    json=request_data,
                    timeout=self.timeout,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'ReactAgent-WebSearch/1.0'
                    }
                )
                
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    result = response.json()
                    result_count = len(result.get('items', []))
                    
                    self.logger.info(f"✅ Web搜索成功: 获得 {result_count} 条结果, 耗时 {response_time:.2f}s")
                    
                    # 限制结果数量
                    if result_count > max_results:
                        result['items'] = result['items'][:max_results]
                        result['count'] = max_results
                        self.logger.debug(f"🔄 结果数量限制为 {max_results} 条")
                    
                    return result
                    
                else:
                    self.logger.error(f"❌ Web搜索失败: HTTP {response.status_code} - {response.text}")
                    
            except requests.exceptions.Timeout:
                self.logger.warning(f"⏱️ Web搜索超时 (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                    
            except requests.exceptions.ConnectionError:
                self.logger.error(f"🔌 Web搜索连接失败 (尝试 {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"❌ Web搜索请求异常: {e}")
                break
                
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ Web搜索响应解析失败: {e}")
                break
                
            except Exception as e:
                self.logger.error(f"❌ Web搜索未知错误: {e}")
                break
        
        return None
    
    def check_service_status(self) -> Dict[str, Any]:
        """检查 Web 搜索服务状态"""
        try:
            # 允许通过环境变量跳过健康检查，避免浪费一次查询
            skip = os.getenv("WEB_SEARCH_SKIP_HEALTH_CHECK", os.getenv("SKIP_HEALTH_CHECK", "false")).lower() == "true"
            if skip:
                self.logger.info("🔄 已跳过Web搜索健康检查（配置）")
                return {
                    'status': 'running',
                    'service': 'Web Search API',
                    'endpoint': self.search_endpoint,
                    'skipped': True
                }

            # 尝试一个简单的搜索来检查服务状态
            test_result = self.search("test", max_results=1)
            if test_result:
                return {
                    'status': 'running',
                    'service': 'Web Search API',
                    'endpoint': self.search_endpoint
                }
            else:
                return {
                    'status': 'error',
                    'service': 'Web Search API',
                    'endpoint': self.search_endpoint,
                    'message': 'Service not responding'
                }
        except Exception as e:
            return {
                'status': 'error',
                'service': 'Web Search API',
                'endpoint': self.search_endpoint,
                'message': str(e)
            }
    
    def format_search_results(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        格式化搜索结果为统一格式
        
        Args:
            search_results: 原始搜索结果
            
        Returns:
            格式化后的结果列表
        """
        if not search_results or 'items' not in search_results:
            return []
        
        formatted_results = []
        
        for item in search_results.get('items', []):
            formatted_item = {
                'content': item.get('content', ''),
                'source': f"Web搜索 - {item.get('title', 'Unknown')}",
                'type': 'web_text',
                'url': item.get('link', ''),
                'title': item.get('title', ''),
                'engine': item.get('engine', 'unknown'),
                'score': 1.0,  # Web搜索结果默认高分
                'content_length': item.get('contentLength', 0)
            }
            
            # 过滤掉内容过短的结果
            if len(formatted_item['content']) >= 50:
                formatted_results.append(formatted_item)
        
        return formatted_results

def get_web_search_client() -> WebSearchClient:
    """获取 Web 搜索客户端实例"""
    return WebSearchClient()
