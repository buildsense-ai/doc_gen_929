#!/usr/bin/env python3
"""
简化的Writer Agent - 只使用RAG检索
移除Web搜索和多维度查询，专注于单次RAG调用
"""

import logging
from typing import Dict, Any, List, Optional

from clients.external_api_client import get_external_api_client


class SimpleWriterAgent:
    """
    简化的Writer Agent
    
    职责：
    1. 根据任务描述和当前摘要构造查询
    2. 调用RAG API检索资料
    3. 返回检索到的文本、图片、表格
    """
    
    def __init__(self, llm_client=None, project_name: str = "项目文档"):
        """
        初始化Writer Agent
        
        Args:
            llm_client: LLM客户端（保留参数以保持接口一致性，但不使用）
            project_name: 项目名称，用于RAG检索
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.external_api = get_external_api_client()
        self.project_name = project_name
        
        self.logger.info(f"SimpleWriterAgent 初始化完成，项目: {project_name}")
    
    def retrieve_for_task(
        self, 
        task_description: Dict[str, str], 
        current_summary: str,
        project_name: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        为任务检索资料
        
        Args:
            task_description: 任务描述字典，包含 'title' 和 'how_to_write'
            current_summary: 当前累积摘要
            project_name: 项目名称（可选，覆盖初始化时的项目名）
        
        Returns:
            字典包含:
                - retrieved_text: 文本检索结果列表
                - retrieved_image: 图片检索结果列表
                - retrieved_table: 表格检索结果列表
        """
        title = task_description.get('title', '')
        how_to_write = task_description.get('how_to_write', '')
        
        # 构造查询文本
        query_parts = []
        
        # 如果有前文摘要，加入上下文
        if current_summary:
            query_parts.append(f"[前文摘要: {current_summary[:200]}]")
        
        # 添加任务标题和写作指导
        query_parts.append(f"{title}: {how_to_write}")
        
        query = " ".join(query_parts)
        
        self.logger.info(f"构造检索查询: {query[:100]}...")
        
        # 调用RAG API
        project = project_name or self.project_name
        try:
            results = self.external_api.document_search(query, project)
            
            if not results:
                self.logger.warning(f"RAG检索未返回结果: {title}")
                return {
                    "retrieved_text": [],
                    "retrieved_image": [],
                    "retrieved_table": []
                }
            
            # 解析返回的混合内容
            parsed_results = self._parse_rag_results(results)
            
            self.logger.info(
                f"检索完成: 文本={len(parsed_results['retrieved_text'])}, "
                f"图片={len(parsed_results['retrieved_image'])}, "
                f"表格={len(parsed_results['retrieved_table'])}"
            )
            
            return parsed_results
            
        except Exception as e:
            self.logger.error(f"RAG检索失败: {e}", exc_info=True)
            return {
                "retrieved_text": [],
                "retrieved_image": [],
                "retrieved_table": []
            }
    
    def _parse_rag_results(self, results: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        解析RAG API返回的结果
        
        Args:
            results: RAG API返回的原始结果
        
        Returns:
            解析后的结果字典
        """
        retrieved_text = []
        retrieved_image = []
        retrieved_table = []
        
        # 获取结果数据
        data = results.get('data', {})
        result_list = data.get('results', [])
        
        if not result_list:
            self.logger.warning("RAG结果中没有找到 'results' 字段")
            return {
                "retrieved_text": [],
                "retrieved_image": [],
                "retrieved_table": []
            }
        
        # 解析每个结果项
        for idx, item in enumerate(result_list):
            # 提取文本内容
            content = item.get('content', '')
            if content:
                text_entry = {
                    'content': content,
                    'source': item.get('source', f'文档第{item.get("page_number", idx+1)}页'),
                    'page_number': item.get('page_number', idx + 1),
                    'relevance_score': item.get('similarity', 0.0)
                }
                retrieved_text.append(text_entry)
            
            # 提取图片
            images = item.get('images', [])
            if images:
                for img in images:
                    if isinstance(img, str):
                        image_entry = {
                            'image_path': img,
                            'page_number': item.get('page_number', idx + 1),
                            'caption': f"来自{item.get('source', '文档')}"
                        }
                    elif isinstance(img, dict):
                        image_entry = {
                            'image_path': img.get('path', img.get('url', '')),
                            'page_number': item.get('page_number', idx + 1),
                            'caption': img.get('caption', f"来自{item.get('source', '文档')}")
                        }
                    else:
                        continue
                    
                    if image_entry['image_path']:
                        retrieved_image.append(image_entry)
            
            # 提取表格
            tables = item.get('tables', [])
            if tables:
                for tbl in tables:
                    if isinstance(tbl, str):
                        table_entry = {
                            'table_path': tbl,
                            'page_number': item.get('page_number', idx + 1),
                            'caption': f"来自{item.get('source', '文档')}"
                        }
                    elif isinstance(tbl, dict):
                        table_entry = {
                            'table_path': tbl.get('path', tbl.get('data', '')),
                            'page_number': item.get('page_number', idx + 1),
                            'caption': tbl.get('caption', f"来自{item.get('source', '文档')}")
                        }
                    else:
                        continue
                    
                    if table_entry['table_path']:
                        retrieved_table.append(table_entry)
        
        return {
            "retrieved_text": retrieved_text,
            "retrieved_image": retrieved_image,
            "retrieved_table": retrieved_table
        }

