#!/usr/bin/env python3
"""
简化的Editor Agent - 单次内容生成
移除质量评估循环和改进迭代，专注于一次性生成
"""

import logging
from typing import Dict, Any, List

# 使用现有的prompt模板
CONTENT_GENERATION_PROMPT = """
你是一位专业的写作者，你的任务是：基于【写作指引】+【前文摘要】+【参考资料】撰写一个章节正文。

【章节标题】：{subtitle}

【写作指引（重点参考）】：
{how_to_write}

【前文摘要】：
{current_summary}

【核心参考资料】：
{retrieved_text_content}

输出要求：
1) 只输出“章节正文”，不要输出任何额外说明（例如“以下是正文”）。
2) 语言风格与结构严格遵循【写作指引】。
3) 如引用关键事实/数据，尽量保留原文中的数值与表述，不要编造。
4）全文使用纯文本格式，绝不包含任何Markdown标记。
5）严禁输出任何形式的小节标题或编号（如一、{subtitle}等），只写正文段落。
"""


class SimpleEditorAgent:
    """
    简化的Editor Agent
    
    职责：
    1. 根据任务描述、检索信息和当前摘要构造prompt
    2. 调用LLM一次性生成内容
    3. 返回生成的内容和字数
    """
    
    def __init__(self, llm_client):
        """
        初始化Editor Agent
        
        Args:
            llm_client: LLM客户端，用于内容生成
        """
        self.llm = llm_client
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        self.logger.info("SimpleEditorAgent 初始化完成")
    
    def generate_content(
        self,
        task_description: Dict[str, str],
        retrieved_info: Dict[str, List[Dict[str, Any]]],
        current_summary: str
    ) -> Dict[str, Any]:
        """
        生成章节内容
        
        Args:
            task_description: 任务描述字典，包含 'title' 和 'how_to_write'
            retrieved_info: Writer Agent返回的检索信息
            current_summary: 当前累积摘要
        
        Returns:
            字典包含:
                - content: 生成的章节内容
                - word_count: 字数
        """
        title = task_description.get('title', '')
        how_to_write = task_description.get('how_to_write', '')
        
        self.logger.info(f"开始生成内容: {title}")
        
        try:
            # 构造prompt
            prompt = self._build_generation_prompt(
                title=title,
                how_to_write=how_to_write,
                retrieved_text=retrieved_info.get('retrieved_text', []),
                current_summary=current_summary
            )
            
            # 调用LLM生成内容
            content = self.llm.generate(prompt)
            
            # 清理内容（移除可能的markdown标记）
            content = self._clean_content(content)
            
            word_count = len(content)
            
            self.logger.info(f"内容生成完成: {title}, 字数: {word_count}")
            
            return {
                "content": content,
                "word_count": word_count
            }
            
        except Exception as e:
            self.logger.error(f"内容生成失败: {e}", exc_info=True)
            # 返回空内容而不是抛出异常
            return {
                "content": f"[生成失败] {title}章节内容生成时发生错误。",
                "word_count": 0
            }
    
    def _build_generation_prompt(
        self,
        title: str,
        how_to_write: str,
        retrieved_text: List[Dict[str, Any]],
        current_summary: str
    ) -> str:
        """
        构造内容生成的prompt
        
        Args:
            title: 章节标题
            how_to_write: 写作指导
            retrieved_text: 检索到的文本内容列表
            current_summary: 当前累积摘要
        
        Returns:
            构造好的prompt字符串
        """
        # 提取并格式化检索到的文本内容
        retrieved_text_content = self._format_retrieved_text(retrieved_text)
        
        # 格式化当前摘要
        summary_text = current_summary if current_summary else "本章是文档的第一章"
        
        # 使用prompt模板
        prompt = CONTENT_GENERATION_PROMPT.format(
            subtitle=title,
            how_to_write=how_to_write,
            current_summary=summary_text,
            retrieved_text_content=retrieved_text_content
        )
        
        return prompt
    
    def _format_retrieved_text(self, retrieved_text: List[Dict[str, Any]]) -> str:
        """
        格式化检索到的文本内容
        
        Args:
            retrieved_text: 检索到的文本内容列表
        
        Returns:
            格式化后的文本字符串
        """
        if not retrieved_text:
            return "暂无参考资料"
        
        formatted_parts = []
        
        for idx, item in enumerate(retrieved_text, 1):
            content = item.get('content', '')
            source = item.get('source', '未知来源')
            
            if content:
                formatted_parts.append(f"[资料{idx} - {source}]\n{content}\n")
        
        if not formatted_parts:
            return "暂无参考资料"
        
        return "\n".join(formatted_parts)
    
    def _clean_content(self, content: str) -> str:
        """
        清理生成的内容，移除markdown标记
        
        Args:
            content: 原始生成的内容
        
        Returns:
            清理后的内容
        """
        # 移除markdown粗体标记
        content = content.replace('**', '')
        content = content.replace('__', '')
        
        # 移除markdown标题标记
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            # 移除以#开头的标题行
            if line.strip().startswith('#'):
                # 保留标题文本但去掉#号
                cleaned_line = line.strip().lstrip('#').strip()
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)
            else:
                cleaned_lines.append(line)
        
        content = '\n'.join(cleaned_lines)
        
        # 移除markdown斜体标记
        content = content.replace('*', '')
        content = content.replace('_', '')
        
        return content.strip()

