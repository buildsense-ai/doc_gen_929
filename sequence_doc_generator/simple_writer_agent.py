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
        解析RAG API返回的结果（Bundle格式）
        
        Args:
            results: RAG API返回的原始结果（包含bundles, short_term_memory, recent_turns）
        
        Returns:
            解析后的结果字典
        """
        retrieved_text = []
        retrieved_image = []
        retrieved_table = []
        
        # 新API返回格式包含bundles
        bundles = results.get('bundles', [])
        
        if not bundles:
            self.logger.warning("RAG结果中没有找到 'bundles' 字段")
            return {
                "retrieved_text": [],
                "retrieved_image": [],
                "retrieved_table": []
            }
        
        # 解析每个Bundle
        for bundle_idx, bundle in enumerate(bundles):
            bundle_id = bundle.get('bundle_id', bundle_idx)
            
            # 解析conversations（对话内容 -> 文本）
            conversations = bundle.get('conversations', [])
            for conv in conversations:
                text_content = conv.get('text', '')
                if text_content:
                    text_entry = {
                        'content': text_content,
                        'source': f'Bundle {bundle_id} - Conversation {conv.get("conversation_id", "")}',
                        'page_number': f'Bundle {bundle_id}',
                        'relevance_score': conv.get('score', 0.0),
                        'metadata': conv.get('metadata', {})
                    }
                    retrieved_text.append(text_entry)
            
            # 解析facts（事实内容 -> 文本 + 可能的图片）
            facts = bundle.get('facts', [])
            for fact in facts:
                fact_content = fact.get('content', '')
                if fact_content:
                    text_entry = {
                        'content': fact_content,
                        'source': f'Bundle {bundle_id} - Fact {fact.get("fact_id", "")}',
                        'page_number': f'Bundle {bundle_id}',
                        'relevance_score': fact.get('score', 0.0),
                        'metadata': fact.get('metadata', {})
                    }
                    retrieved_text.append(text_entry)
                
                # 如果fact包含图片
                image_url = fact.get('image_url', '')
                if image_url:
                    image_entry = {
                        'image_path': image_url,
                        'page_number': f'Bundle {bundle_id}',
                        'caption': fact_content[:100] if fact_content else f'Fact {fact.get("fact_id", "")}'
                    }
                    retrieved_image.append(image_entry)
            
            # 解析topics（主题内容 -> 文本）
            topics = bundle.get('topics', [])
            for topic in topics:
                topic_title = topic.get('title', '')
                topic_summary = topic.get('summary', '')
                if topic_title or topic_summary:
                    text_entry = {
                        'content': f"【主题：{topic_title}】\n{topic_summary}",
                        'source': f'Bundle {bundle_id} - Topic {topic.get("topic_id", "")}',
                        'page_number': f'Bundle {bundle_id}',
                        'relevance_score': topic.get('score', 0.0)
                    }
                    retrieved_text.append(text_entry)
        
        # 同时解析recent_turns中的对话（如果有）
        recent_turns = results.get('recent_turns', {})
        recent_conversations = recent_turns.get('conversations', [])
        for conv in recent_conversations:
            text_content = conv.get('text', '')
            if text_content:
                text_entry = {
                    'content': text_content,
                    'source': f'Recent - Conversation {conv.get("conversation_id", "")}',
                    'page_number': 'Recent',
                    'relevance_score': conv.get('score', 0.0),
                    'metadata': conv.get('metadata', {})
                }
                retrieved_text.append(text_entry)
        
        return {
            "retrieved_text": retrieved_text,
            "retrieved_image": retrieved_image,
            "retrieved_table": retrieved_table
        }

