#!/usr/bin/env python3
"""
简化的Editor Agent - 单次内容生成
移除质量评估循环和改进迭代，专注于一次性生成
"""

import logging
from typing import Dict, Any, List

# 使用现有的prompt模板
CONTENT_GENERATION_PROMPT = """
请严格扮演一位专业的报告撰写人，根据以下信息为一份将提交给政府主管部门和项目委托方的正式报告撰写其中一个章节。

【章节子标题】：{subtitle}

【本章写作目标与角色指引】：
{how_to_write}

【前文摘要】：
{current_summary}

【核心参考资料】：
{retrieved_text_content}

请根据上述信息撰写本章节内容，特别注意：
1. 结合【前文摘要】理解整体文档脉络，确保内容衔接自然
2. 仔细分析【核心参考资料】，提取与本章节相关的关键信息
3. 严格遵循【本章写作目标与角色指引】的要求

---
**撰写要求与风格指引：**

1.  **专业角色与语境**:
    * **身份定位**: 你是持证的专业评估师，你的文字将成为官方报告的一部分。
    * **写作目的**: 报告的核心是为项目审批提供清晰、可靠、专业的决策依据。
    * **语言风格**: 语言必须专业、客观、严谨，但同时要保证清晰、易读，结论必须明确、直接。

2.  **内容与结构 (关键策略)**:
    * **[核心策略] 信息筛选与职责聚焦**:
        * **第一步：明确本章核心职责**: 严格依据【本章写作目标与角色指引】，确定本章需要回答的唯一核心问题。
        * **第二步：筛选核心信息**: 只挑选出与本章核心职责直接相关的内容作为写作重点。
        * **第三步：聚焦撰写**: 严格围绕筛选出的核心信息展开论述，确保每一段话都在为本章写作目标服务。
    * **数据使用**: 优先使用【核心参考资料】中提供的直接数据（如距离、高度、年代等）。
    * **结构化表达**: 采用清晰的层次结构，如"一、"、"（一）"、"1."来组织内容。

3.  **格式规范 (严格遵守)**:
    * **纯文本**: 全文使用纯文本格式，绝不包含任何Markdown标记（如`**`、`*`、`#`等）。
    * **段落**: 段落之间用一个空行分隔。
    * **序号**: 列表或子标题统一使用"（一）"、"1."、"（1）"等纯文本序号。
    * **字数控制**: 正文内容控制在800-1200字之间。

---
**重要提示**:
* 请直接生成正文内容，不要在开头或结尾添加任何额外说明或标题。
* 最终输出的内容应该是一份可以直接嵌入正式报告的、成熟的章节正文。
* 全文使用纯文本格式，绝不包含任何Markdown标记。
* 严禁输出任何形式的小节标题或编号（如一、{subtitle}等），只写正文段落。
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

