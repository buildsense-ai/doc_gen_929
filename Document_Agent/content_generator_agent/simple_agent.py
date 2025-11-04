#!/usr/bin/env python3
"""
简化版内容生成代理 - 只包含JSON文档生成功能

这个版本移除了对复杂数据结构的依赖，专注于JSON到文档的生成。
"""

from typing import Dict, Any, List, Tuple, Optional
import json
import logging
import datetime
import re
import time

# 导入 prompt 模板
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Document_Agent.prompts import CONTENT_GENERATION_PROMPT

class SimpleContentGeneratorAgent:
    """
    简化版内容生成代理
    
    专注于从JSON生成内容的功能
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.quality_threshold = 0.7
        self.max_improvement_attempts = 2
        
    def generate_content_from_json(self, subtitle: str, how_to_write: str, 
                                   retrieved_text: List[Dict], retrieved_image: List[Dict], 
                                   retrieved_table: List[Dict], retrieved_web: List[Dict] = None) -> Dict[str, Any]:
        """
        根据JSON字段生成内容 (V5 - 支持分离的文本、图片、表格、Web搜索数据)
        
        新流程：基于retrieved_text和retrieved_web生成内容，然后在章节后面插入表格和图片
        
        Args:
            subtitle: 章节标题
            how_to_write: 写作指导
            retrieved_text: 文本检索结果列表
            retrieved_image: 图片检索结果列表  
            retrieved_table: 表格检索结果列表
            retrieved_web: Web搜索结果列表
        """
        
        self.logger.info(f"开始生成内容: {subtitle}")
        start_time = time.time()
        
        try:
            # 1. 处理文本、图片和Web搜索数据，用于内容生成
            text_content = self._extract_text_content(retrieved_text)
            image_content = self._extract_image_content(retrieved_image)
            web_content = self._extract_web_content(retrieved_web or [])
            combined_content = self._combine_all_content(text_content, image_content, web_content)
            
            # 2. 生成初始内容（基于文本和图片描述数据）
            content = self._generate_content_from_json_section(
                subtitle=subtitle,
                how_to_write=how_to_write,
                retrieved_text_content=combined_content,
                feedback=None
            )
            
            final_score, final_feedback = 0.0, ""
            
            # 3. 质量控制与改进循环
            for attempt in range(self.max_improvement_attempts + 1):
                # 3.1. 评估当前内容质量并获取具体反馈
                current_score, feedback = self._evaluate_content_quality(
                    content, how_to_write, combined_content
                )
                
                final_score, final_feedback = current_score, feedback
                
                # 3.2. 检查是否达到质量标准（70分）
                if current_score >= self.quality_threshold:
                    self.logger.info(f"内容质量达标 (分数: {current_score:.2f})，无需改进。")
                    break # 质量达标，跳出循环
                
                # 3.3. 如果未达标且还有改进机会，则根据反馈重新生成
                if attempt < self.max_improvement_attempts:
                    self.logger.warning(
                        f"第 {attempt + 1} 次尝试质量不达标 (分数: {current_score:.2f})，"
                        f"根据反馈重新生成..."
                    )
                    # 根据评估反馈重新生成内容
                    content = self._generate_content_from_json_section(
                        subtitle=subtitle,
                        how_to_write=how_to_write,
                        retrieved_text_content=combined_content,
                        feedback=feedback
                    )
                else:
                    self.logger.error(
                        f"达到最大改进次数 ({self.max_improvement_attempts}) 后，"
                        f"质量仍不达标 (最终分数: {current_score:.2f})。"
                    )

            # 4. 清理最终内容
            content = self._clean_content(content, subtitle)
            
            # 5. 不在生成阶段追加表格和图片，统一由渲染阶段处理，避免重复注入
            
            generation_time = time.time() - start_time
            
            result = {
                'content': content,
                'quality_score': final_score,
                'word_count': len(content),
                'generation_time': f"{generation_time:.2f}s",
                'feedback': final_feedback,
                'subtitle': subtitle
            }
            
            self.logger.info(f"生成完成: {subtitle} ({result['word_count']}字, 最终分数: {final_score:.3f})")
            if result['content']:
                self.logger.info("章节内容：\n%s", result['content'])
            
            return result
            
        except Exception as e:
            self.logger.exception(f"生成内容时发生严重错误: {e}")
            return {
                'content': f"[生成失败: {str(e)}]",
                'quality_score': 0.0,
                'word_count': 0,
                'generation_time': "0.00s",
                'feedback': f"生成失败: {str(e)}",
                'subtitle': subtitle
            }
    
    def _generate_content_from_json_section(self, subtitle: str, 
                                              how_to_write: str, retrieved_text_content: str, 
                                              feedback: Optional[str] = None) -> str:
        """
        根据JSON信息生成内容 (V4 - 基于文本内容生成)
        
        Args:
            subtitle: 章节标题
            how_to_write: 写作指导
            retrieved_text_content: 处理后的文本内容
            feedback: 评估反馈（如果是重新生成）
        """
        # 使用导入的 prompt 模板
        prompt = CONTENT_GENERATION_PROMPT.format(
            subtitle=subtitle,
            how_to_write=how_to_write,
            retrieved_text_content=retrieved_text_content,
            feedback=feedback or "无特殊要求，按照标准流程撰写"
        )
        
        try:
            response = self.llm.generate(prompt)
            return response.strip()
        except Exception as e:
            self.logger.error(f"LLM生成内容失败: {e}")
            return f"[内容生成失败: {str(e)}]"
    
    def _evaluate_content_quality(self, content: str, how_to_write: str, 
                                    retrieved_text_content: str) -> Tuple[float, str]:
        """
        评估内容质量并返回具体反馈 (V5 - 简化为字数评估)
        
        Returns:
            Tuple[float, str]: (评分0-1, 具体反馈信息)
        """
        
        # --- 字数评估 ---
        content_length = len(content)
        
        if content_length < 300:
            return (0.1, f"内容过短（当前{content_length}字），需要补充更多具体内容和分析，至少300字。")
        
        if content.startswith('[') and content.endswith(']'):
            return (0.0, "生成失败或包含错误信息，需要重新生成。")
        
        # 字数合格，直接通过
        return (1.0, f"内容字数合格（{content_length}字），质量良好。")

        # --- 注释掉的AI深度评估逻辑 ---
        
#         evaluator_prompt = f"""
# 你是一位负责审核报告的资深主编，标准极高。你的任务是为以下【待评估内容】进行全面的质量评估，并提供具体的改进建议。

# **评估维度与标准**:
# 1.  **风格与专业性**: 内容是否是专业、务实的报告风格，而非学术探讨？
# 2.  **结构与清晰度**: 结构是否清晰？关键部分是否有明确的总结？
# 3.  **内容聚焦度**: 内容是否紧扣主题，没有过多无关细节？
# 4.  **资料利用度**: 是否充分、准确地利用了参考资料？
# 5.  **资料无关利用**: 是否利用了与本章无关的资料？

# ---
# 【本章写作指导】：
# {how_to_write}

# 【核心参考资料】：
# {retrieved_text_content}

# 【待评估内容】：
# {content}
# ---

# **【你的任务】**
# 请根据上述标准，仔细审查【待评估内容】，并完成以下两项任务：
# 1.  **综合评分**: 给出一个0到100之间的整数分数。
# 2.  **具体反馈**: 如果内容存在问题，请提供详细、具体、可操作的改进建议。如果内容质量合格，则说明"内容质量良好，无需改进"。

# **请严格按照以下JSON格式返回你的评估结果：**
# ```json
# {{
#   "score": <0-100之间的整数>,
#   "feedback": "<详细的改进建议或评价>"
# }}
# ```

# 注意：
# - 反馈要具体、可操作，指出需要修改的具体内容和方向
# - 不要只说有问题，要说明如何改进
# - 如果内容好，要明确说明好在哪里
# """
        
#         try:
#             response_text = self.llm.generate(evaluator_prompt).strip()
#             # 确保只提取JSON部分
#             json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
#             if not json_match:
#                 raise json.JSONDecodeError("未在LLM响应中找到有效的JSON对象", response_text, 0)
            
#             eval_result = json.loads(json_match.group(0))
            
#             score_int = eval_result.get("score", 0)
#             feedback = eval_result.get("feedback", "评估结果解析异常")
            
#             score_float = max(0.0, min(1.0, float(score_int) / 100.0))
            
#             return (score_float, feedback)
            
#         except json.JSONDecodeError as e:
#             self.logger.error(f"LLM评估返回的JSON格式错误: {e}. Response: '{response_text}'")
#             return (0.2, "评估返回格式错误，需要重新生成内容")
#         except Exception as e:
#             self.logger.error(f"LLM评估内容时发生未知错误: {e}")
#             return (0.2, "评估过程异常，需要重新生成内容")
    
    def _clean_content(self, content: str, subtitle: str) -> str:
        """
        清理内容格式，并移除可能重复的标题。
        """
        # 核心改动：检查并移除重复的子标题
        # .strip()用于去除首尾空格，以防万一
        if content.strip().startswith(subtitle):
            # 如果内容以子标题开头，则切掉这部分
            content = content.strip()[len(subtitle):].lstrip()

        # --- 以下是您原有的清理逻辑，保持不变 ---
        # 使用非贪婪匹配来避免错误替换
        content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # 移除粗体
        content = re.sub(r'\*(.*?)\*', r'\1', content)    # 移除斜体
        content = re.sub(r'#{1,6}\s+', '', content)         # 移除标题标记
        content = re.sub(r'```[\s\S]*?```', '', content) # 移除代码块
        
        content = re.sub(r'\n{3,}', '\n\n', content)      # 多个换行变成两个
        content = re.sub(r'[ \t]+\n', '\n', content)      # 移除行尾空格
        
        return content.strip()
    
    def _extract_text_content(self, retrieved_text: List[Dict]) -> str:
        """
        从retrieved_text列表中提取文本内容
        
        Args:
            retrieved_text: 文本检索结果列表
            
        Returns:
            str: 合并后的文本内容
        """
        if not retrieved_text:
            return "未检索到相关文本资料。"
        
        text_parts = []
        for i, text_item in enumerate(retrieved_text, 1):
            content = text_item.get('content', str(text_item))
            source = text_item.get('source', '未知来源')
            text_parts.append(f"[文本资料{i}] 来源: {source}\n内容: {content}")
        
        return "\n\n".join(text_parts)
    
    def _extract_image_content(self, retrieved_image: List[Dict]) -> str:
        """
        从retrieved_image列表中提取图片描述内容
        
        Args:
            retrieved_image: 图片检索结果列表
            
        Returns:
            str: 合并后的图片描述内容
        """
        if not retrieved_image:
            return "未检索到相关图片资料。"
        
        image_parts = []
        for i, image_item in enumerate(retrieved_image, 1):
            content = image_item.get('content', image_item.get('description', f'图片{i}'))
            source = image_item.get('source', '未知来源')
            image_parts.append(f"[图片资料{i}] 来源: {source}\n描述: {content}")
        
        return "\n\n".join(image_parts)
    
    def _combine_text_and_image_content(self, text_content: str, image_content: str) -> str:
        """
        合并文本内容和图片描述内容
        
        Args:
            text_content: 文本内容
            image_content: 图片描述内容
            
        Returns:
            str: 合并后的内容
        """
        combined_parts = []
        
        if text_content and text_content != "未检索到相关文本资料。":
            combined_parts.append(text_content)
        
        if image_content and image_content != "未检索到相关图片资料。":
            combined_parts.append(image_content)
        
        if not combined_parts:
            return "未检索到相关资料。"
        
        return "\n\n".join(combined_parts)
    
    def _extract_web_content(self, retrieved_web: List[Dict]) -> str:
        """
        从retrieved_web列表中提取Web搜索内容
        """
        if not retrieved_web:
            return "未检索到相关Web资料。"
        
        web_contents = []
        for i, web_item in enumerate(retrieved_web, 1):
            content = web_item.get('content', '')
            title = web_item.get('title', '')
            url = web_item.get('url', '')
            
            if content.strip():
                web_entry = f"Web资料{i}"
                if title:
                    web_entry += f" - {title}"
                if url:
                    web_entry += f" ({url})"
                web_entry += f": {content.strip()}"
                web_contents.append(web_entry)
        
        return "\n".join(web_contents) if web_contents else "未检索到相关Web资料。"

    def _combine_all_content(self, text_content: str, image_content: str, web_content: str) -> str:
        """
        合并文本内容、图片描述内容和Web搜索内容
        """
        combined_parts = []
        
        if text_content and text_content != "未检索到相关文本资料。":
            combined_parts.append(text_content)
        
        if image_content and image_content != "未检索到相关图片资料。":
            combined_parts.append(image_content)
            
        if web_content and web_content != "未检索到相关Web资料。":
            combined_parts.append(web_content)
        
        if not combined_parts:
            return "未检索到相关资料。"
        
        return "\n\n".join(combined_parts)
    
    # def _append_tables_and_images(self, content: str, retrieved_table: List[Dict], 
    #                             retrieved_image: List[Dict]) -> str:
    #     """
    #     在生成的章节内容后面插入表格和图片
        
    #     Args:
    #         content: 生成的章节内容
    #         retrieved_table: 表格检索结果列表
    #         retrieved_image: 图片检索结果列表
            
    #     Returns:
    #         str: 包含表格和图片的完整内容
    #     """
    #     final_content = content
        
    #     # 添加表格 - 使用三级标题
    #     if retrieved_table:
    #         final_content += "\n\n### 相关表格资料\n"
    #         for i, table_item in enumerate(retrieved_table, 1):
    #             table_content = table_item.get('content', str(table_item))
    #             table_source = table_item.get('source', '未知来源')
    #             final_content += f"\n**表格{i}** (来源: {table_source})\n\n{table_content}\n"
        
    #     # 添加图片 - 使用三级标题和markdown图片语法，并去重
    #     if retrieved_image:
    #         final_content += "\n\n### 相关图片资料\n"
            
    #         # 根据URL去重图片
    #         seen_urls = set()
    #         unique_images = []
    #         for image_item in retrieved_image:
    #             image_path = image_item.get('path', '无路径')
    #             if image_path and image_path != '无路径' and image_path not in seen_urls:
    #                 seen_urls.add(image_path)
    #                 unique_images.append(image_item)
    #             elif image_path == '无路径':  # 保留没有路径的图片项
    #                 unique_images.append(image_item)
            
    #         for i, image_item in enumerate(unique_images, 1):
    #             image_desc = image_item.get('content', image_item.get('description', f'检索到的相关图片 {i}'))
    #             image_path = image_item.get('path', '无路径')
    #             image_source = image_item.get('source', '未知来源')
                
    #             # 限制图片描述长度到100字符以内
    #             if len(image_desc) > 100:
    #                 image_desc = image_desc[:97] + "..."
                
    #             # 使用标准markdown图片语法
    #             if image_path and image_path != '无路径':
    #                 final_content += f"\n![{image_desc}]({image_path})\n*图片来源: {image_source}*\n"
    #             else:
    #                 final_content += f"\n**图片{i}** (来源: {image_source})  \n描述: {image_desc}  \n*路径未提供*\n"
        
    #     return final_content
