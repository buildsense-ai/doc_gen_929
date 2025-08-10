"""
编排代理 - 智能速率控制增强版

功能：
1. 基于用户查询生成文档结构
2. 为每个章节添加写作指导

特点：
- 两阶段生成模式
- 支持并发处理
- 集成智能速率控制系统
"""

import json
import sys
import os
import time
import logging
import concurrent.futures
import re
from typing import Dict, Any, List, Optional

# 确保可以导入其他模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from config.settings import get_concurrency_manager, SmartConcurrencyManager
from clients.external_api_client import get_external_api_client

class EnhancedOrchestratorAgent:
    """编排代理 - 集成智能速率控制系统"""

    def __init__(self, llm_client, concurrency_manager: Optional[SmartConcurrencyManager] = None):
        # self.rag = rag_agent  # 已移除，现在使用外部API
        self.llm_client = llm_client
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 外部API客户端
        self.external_api = get_external_api_client()
        
        # 智能并发管理器
        self.concurrency_manager = concurrency_manager or get_concurrency_manager()
        self.max_workers = self.concurrency_manager.get_max_workers('orchestrator_agent')
        
        # 智能速率控制器
        self.rate_limiter = self.concurrency_manager.get_rate_limiter('orchestrator_agent')
        self.has_smart_control = self.concurrency_manager.has_smart_rate_control('orchestrator_agent')
        
        # 进度追踪
        self.processed_sections = 0
        
        # 性能统计
        self.orchestration_stats = {
            'total_api_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'total_processing_time': 0.0,
            'structure_generation_time': 0.0,
            'guide_generation_time': 0.0,
            'template_search_calls': 0,
            'template_search_success': 0
        }
        
        status_msg = f"智能速率控制: {'已启用' if self.has_smart_control else '传统模式'}"
        self.logger.info(f"EnhancedOrchestratorAgent 初始化完成，并发线程数: {self.max_workers}, {status_msg}")
        
        # 检查外部API服务状态
        try:
            api_status = self.external_api.check_service_status()
            if api_status.get('status') == 'running':
                self.logger.info(f"✅ 外部API服务连接正常: {api_status.get('service', '')} v{api_status.get('version', '')}")
            else:
                self.logger.warning(f"⚠️ 外部API服务状态异常: {api_status}")
        except Exception as e:
            self.logger.error(f"❌ 外部API服务连接检查失败: {e}")

    def set_max_workers(self, max_workers: int):
        """动态设置最大线程数"""
        self.max_workers = max_workers
        self.concurrency_manager.set_max_workers('orchestrator_agent', max_workers)
        self.logger.info(f"OrchestratorAgent 线程数已更新为: {max_workers}")

    def get_max_workers(self) -> int:
        """获取当前最大线程数"""
        return self.max_workers

    def query_existing_template(self, user_description: str) -> Optional[Dict[str, Any]]:
        """
        查询是否存在现有的文档模板 - 使用外部API
        
        Args:
            user_description: 用户查询描述
            
        Returns:
            Optional[Dict[str, Any]]: 如果找到有效模板则返回模板结构，否则返回None
        """
        self.logger.info("🔍 开始查询现有文档模板 (使用外部API)...")
        
        try:
            # 智能速率控制
            if self.has_smart_control:
                delay = self.rate_limiter.get_delay()
                if delay > 0:
                    self.logger.debug(f"智能延迟: {delay:.2f}秒")
                    time.sleep(delay)
            
            # 构建模板查询语句
            template_query = f"文档模板 结构 {user_description}"
            
            # 记录API调用
            api_start_time = time.time()
            self.orchestration_stats['template_search_calls'] += 1
            
            # 使用外部API查询模板
            template_content = self.external_api.template_search(template_query)
            
            api_response_time = time.time() - api_start_time
            
            if not template_content:
                self.logger.info("📭 外部API未找到相关模板")
                if self.has_smart_control:
                    self.concurrency_manager.record_api_request(
                        agent_name='orchestrator_agent',
                        success=False,
                        response_time=api_response_time,
                        error_type='no_results'
                    )
                return None
            
            # 记录成功的API调用
            if self.has_smart_control:
                self.concurrency_manager.record_api_request(
                    agent_name='orchestrator_agent',
                    success=True,
                    response_time=api_response_time
                )
            self.orchestration_stats['template_search_success'] += 1
            
            self.logger.info(f"📬 外部API返回模板内容，长度: {len(template_content)} 字符")
            
            # 尝试解析模板内容为文档结构
            template = self._extract_template_from_api_response(template_content)
            if template:
                # 验证模板结构
                try:
                    self._validate_document_structure(template)
                    self.logger.info("✅ 找到有效的文档结构模板！")
                    return template
                except ValueError as e:
                    self.logger.warning(f"⚠️ 模板结构验证失败: {e}")
                return None
            
            self.logger.info("📭 外部API返回的内容不是有效的文档结构模板")
            return None
            
        except Exception as e:
            # 记录失败的API调用
            api_response_time = time.time() - api_start_time if 'api_start_time' in locals() else 0
            if self.has_smart_control:
                error_type = self._classify_orchestrator_error(str(e))
                self.concurrency_manager.record_api_request(
                    agent_name='orchestrator_agent',
                    success=False,
                    response_time=api_response_time,
                    error_type=error_type
                )
            
            self.logger.error(f"❌ 查询模板时发生错误: {e}")
            return None

    def _extract_template_from_api_response(self, template_content: str) -> Optional[Dict[str, Any]]:
        """
        从外部API响应中提取文档结构模板
        
        Args:
            template_content: 外部API返回的模板内容
            
        Returns:
            Optional[Dict[str, Any]]: 提取的模板结构，如果无效则返回None
        """
        try:
            self.logger.info(f"正在解析外部API返回的模板内容，长度: {len(template_content)} 字符")
            
            # 首先尝试直接解析为JSON
            if template_content.strip().startswith('{'):
                try:
                    template = json.loads(template_content)
                    if isinstance(template, dict) and 'report_guide' in template:
                        self.logger.info(f"✅ 成功解析模板（直接JSON），包含 {len(template['report_guide'])} 个部分")
                        return template
                except json.JSONDecodeError:
                    pass
            
            # 外部API返回格式可能包含说明文字，需要特殊处理
            # 查找Python字典格式的内容
            import re
            
            # 方法1: 寻找以{'report_guide'开头的字典
            dict_pattern = r"(\{'report_guide'.*?\})"
            match = re.search(dict_pattern, template_content, re.DOTALL)
            if match:
                dict_content = match.group(1)
                try:
                    # 使用ast.literal_eval来安全解析Python字典格式
                    import ast
                    template = ast.literal_eval(dict_content)
                    if isinstance(template, dict) and 'report_guide' in template:
                        self.logger.info(f"✅ 成功解析模板（Python字典格式），包含 {len(template['report_guide'])} 个部分")
                        return template
                except (ValueError, SyntaxError) as e:
                    self.logger.warning(f"Python字典解析失败: {e}")
            
            # 方法2: 查找完整的字典结构
            brace_pattern = r"(\{[^{}]*'report_guide'[^{}]*\[[^\[\]]*\{[^{}]*\}[^\[\]]*\][^{}]*\})"
            match = re.search(brace_pattern, template_content, re.DOTALL)
            if match:
                dict_content = match.group(1)
                try:
                    import ast
                    template = ast.literal_eval(dict_content)
                    if isinstance(template, dict) and 'report_guide' in template:
                        self.logger.info(f"✅ 成功解析模板（完整字典格式），包含 {len(template['report_guide'])} 个部分")
                        return template
                except (ValueError, SyntaxError) as e:
                    self.logger.warning(f"完整字典解析失败: {e}")
            
            # 方法3: 更宽松的字典提取（处理嵌套结构）
            try:
                # 寻找第一个{到最后一个}的内容
                start_idx = template_content.find("{")
                if start_idx != -1:
                    # 找到匹配的}
                    brace_count = 0
                    end_idx = start_idx
                    for i in range(start_idx, len(template_content)):
                        if template_content[i] == '{':
                            brace_count += 1
                        elif template_content[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i
                                break
                    
                    if brace_count == 0:
                        dict_content = template_content[start_idx:end_idx + 1]
                        import ast
                        template = ast.literal_eval(dict_content)
                        if isinstance(template, dict) and 'report_guide' in template:
                            self.logger.info(f"✅ 成功解析模板（宽松提取），包含 {len(template['report_guide'])} 个部分")
                            return template
            except Exception as e:
                self.logger.warning(f"宽松提取失败: {e}")
            
            # 方法4: 尝试使用原有的智能JSON提取
            try:
                json_content = self._extract_json_from_response(template_content)
                template = json.loads(json_content)
                if 'report_guide' in template:
                    self.logger.info(f"✅ 成功提取模板（智能提取），包含 {len(template['report_guide'])} 个部分")
                    return template
            except (ValueError, json.JSONDecodeError) as e:
                self.logger.warning(f"智能JSON提取失败: {e}")
            
            # 输出更详细的调试信息
            self.logger.warning(f"所有解析方法都失败，内容前500字符: {template_content[:500]}")
            self.logger.info("❌ 未能从外部API响应中提取有效的文档模板")
            return None
            
        except Exception as e:
            self.logger.error(f"解析外部API模板时发生错误: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _extract_template_from_result(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从RAG检索结果中提取文档结构模板
        
        Args:
            result: RAG检索结果
            
        Returns:
            Optional[Dict[str, Any]]: 提取的模板结构，如果无效则返回None
        """
        try:
            # 获取内容字段
            content = result.get('content', '')
            if not content:
                return None
            
            self.logger.info(f"正在处理RAG返回内容，长度: {len(content)} 字符")
            
            # 尝试解析content为Python字典（如果它是字符串形式的字典）
            if isinstance(content, str):
                # 首先尝试用ast.literal_eval解析Python字典格式
                try:
                    import ast
                    parsed_content = ast.literal_eval(content)
                    self.logger.info(f"✅ 成功用ast.literal_eval解析内容")
                    
                    # 检查是否有final_answer结构
                    if isinstance(parsed_content, dict) and 'final_answer' in parsed_content:
                        final_answer = parsed_content['final_answer']
                        if isinstance(final_answer, dict) and 'retrieved_text' in final_answer:
                            retrieved_text = final_answer['retrieved_text']
                            self.logger.info(f"找到retrieved_text，长度: {len(retrieved_text)} 字符")
                            
                            # retrieved_text可能是一个JSON字符串，需要再次解析
                            if isinstance(retrieved_text, str):
                                # 处理Python字典字符串格式（单引号转双引号）
                                try:
                                    # 尝试用eval解析Python字典格式
                                    import ast
                                    template = ast.literal_eval(retrieved_text)
                                    if isinstance(template, dict) and 'report_guide' in template:
                                        self.logger.info(f"✅ 成功提取模板，包含 {len(template['report_guide'])} 个部分")
                                        return template
                                except (ValueError, SyntaxError) as e:
                                    self.logger.warning(f"ast.literal_eval 解析失败: {e}")
                                
                                # 如果ast失败，尝试手动转换单引号为双引号后用JSON解析
                                try:
                                    # 简单的单引号转双引号（可能不完美，但对于大多数情况有效）
                                    json_text = retrieved_text.replace("'", '"')
                                    template = json.loads(json_text)
                                    if isinstance(template, dict) and 'report_guide' in template:
                                        self.logger.info(f"✅ 成功提取模板（转换后），包含 {len(template['report_guide'])} 个部分")
                                        return template
                                except json.JSONDecodeError as e:
                                    self.logger.warning(f"JSON转换解析失败: {e}")
                            
                            # 如果retrieved_text已经是字典
                            elif isinstance(retrieved_text, dict) and 'report_guide' in retrieved_text:
                                self.logger.info(f"✅ 成功提取模板（直接字典），包含 {len(retrieved_text['report_guide'])} 个部分")
                                return retrieved_text
                        
                    # 检查是否直接包含report_guide
                    elif isinstance(parsed_content, dict) and 'report_guide' in parsed_content:
                        self.logger.info(f"✅ 成功提取模板（直接），包含 {len(parsed_content['report_guide'])} 个部分")
                        return parsed_content
                        
                except (ValueError, SyntaxError) as e:
                    self.logger.warning(f"ast.literal_eval解析失败: {e}")
                    # 如果ast解析失败，尝试JSON解析
                    try:
                        parsed_content = json.loads(content)
                        self.logger.info(f"✅ 成功用json.loads解析内容")
                        
                        # 检查是否有final_answer结构
                        if isinstance(parsed_content, dict) and 'final_answer' in parsed_content:
                            final_answer = parsed_content['final_answer']
                            if isinstance(final_answer, dict) and 'retrieved_text' in final_answer:
                                retrieved_text = final_answer['retrieved_text']
                                self.logger.info(f"找到retrieved_text，长度: {len(retrieved_text)} 字符")
                                
                                # retrieved_text可能是一个JSON字符串，需要再次解析
                                if isinstance(retrieved_text, str):
                                    # 处理Python字典字符串格式（单引号转双引号）
                                    try:
                                        # 尝试用eval解析Python字典格式
                                        import ast
                                        template = ast.literal_eval(retrieved_text)
                                        if isinstance(template, dict) and 'report_guide' in template:
                                            self.logger.info(f"✅ 成功提取模板，包含 {len(template['report_guide'])} 个部分")
                                            return template
                                    except (ValueError, SyntaxError) as e:
                                        self.logger.warning(f"ast.literal_eval 解析失败: {e}")
                                    
                                    # 如果ast失败，尝试手动转换单引号为双引号后用JSON解析
                                    try:
                                        # 简单的单引号转双引号（可能不完美，但对于大多数情况有效）
                                        json_text = retrieved_text.replace("'", '"')
                                        template = json.loads(json_text)
                                        if isinstance(template, dict) and 'report_guide' in template:
                                            self.logger.info(f"✅ 成功提取模板（转换后），包含 {len(template['report_guide'])} 个部分")
                                            return template
                                    except json.JSONDecodeError as e:
                                        self.logger.warning(f"JSON转换解析失败: {e}")
                                
                                # 如果retrieved_text已经是字典
                                elif isinstance(retrieved_text, dict) and 'report_guide' in retrieved_text:
                                    self.logger.info(f"✅ 成功提取模板（直接字典），包含 {len(retrieved_text['report_guide'])} 个部分")
                                    return retrieved_text
                            
                        # 检查是否直接包含report_guide
                        elif isinstance(parsed_content, dict) and 'report_guide' in parsed_content:
                            self.logger.info(f"✅ 成功提取模板（直接），包含 {len(parsed_content['report_guide'])} 个部分")
                            return parsed_content
                    except json.JSONDecodeError:
                        # 如果JSON解析也失败，尝试其他方法
                        pass
            
            # 使用原有的智能JSON提取作为后备方案
            try:
                json_content = self._extract_json_from_response(content)
                template = json.loads(json_content)
                if 'report_guide' in template:
                    self.logger.info(f"✅ 成功提取模板（智能提取），包含 {len(template['report_guide'])} 个部分")
                    return template
            except (ValueError, json.JSONDecodeError) as e:
                self.logger.warning(f"智能JSON提取失败: {e}")
            
            self.logger.info("❌ 未能从RAG结果中提取有效的文档模板")
            return None
            
        except Exception as e:
            self.logger.error(f"提取模板时发生错误: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def generate_document_structure(self, user_description: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        生成文档基础结构 - 智能速率控制增强版
        
        Args:
            user_description: 用户对文档的描述和要求
            max_retries: 最大重试次数
            
        Returns:
            Dict: 包含title, subtitle, goal等字段的基础结构
            
        Raises:
            Exception: 当所有重试都失败时抛出异常
        """
        
        self.logger.info(f"开始生成文档基础结构（智能速率控制增强版）... (最大重试: {max_retries}次)")
        structure_start_time = time.time()
        
        base_prompt = """
你是一个资深的专业文档结构设计专家。

用户需求：{user_description}

请为用户设计一个完整、专业的文档结构。你需要：
1. 判断最适合的文档类型
2. 设计合理的章节层级
3. 确定每个章节和子章节的目标

要求：
- 结构完整、逻辑清晰
- 体现项目特点和专业性
- 章节设置要实用
- 标题和子标题越多越好，尽可能详细和全面
- 每个主要章节应包含多个子章节，覆盖所有相关方面
- 必须按照指定的JSON格式返回
- 返回纯文本格式，不要使用markdown语法

请严格按照以下JSON格式返回：

{{
  "report_guide": [
    {{
      "title": "第一部分 章节标题",
      "goal": "这个章节在整个文档中的作用和价值",
      "sections": [
        {{
          "subtitle": "一、子章节标题"
        }},
        {{
          "subtitle": "二、另一个子章节标题"
        }}
      ]
    }},
    {{
      "title": "第二部分 另一个章节标题",
      "goal": "另一个章节的目标",
      "sections": [
        {{
          "subtitle": "一、子章节标题"
        }}
      ]
    }}
  ]
}}

注意：
- 只返回JSON格式，不要其他解释
- 不要包含how_to_write字段
- title使用"第X部分"格式
- subtitle使用"一、二、三、"格式
- 专注于结构设计，不要写作指导内容
"""
        
        for attempt in range(max_retries):
            try:
                # 智能速率控制
                if self.has_smart_control:
                    delay = self.rate_limiter.get_delay()
                    if delay > 0:
                        self.logger.debug(f"智能延迟: {delay:.2f}秒")
                        time.sleep(delay)
                
                # 构建prompt，重试时强调格式要求
                prompt = base_prompt.format(user_description=user_description)
                if attempt > 0:
                    prompt += f"\n\n⚠️ 重要提醒 (第{attempt + 1}次尝试)：请确保只返回纯JSON格式，不要包含任何说明文字或markdown标记！"
                
                self.logger.info(f"🔄 第{attempt + 1}次尝试生成文档结构...")
                
                # 记录API调用
                api_start_time = time.time()
                self.orchestration_stats['total_api_calls'] += 1
                
                # 调用LLM
                response = self.llm_client.generate(prompt)
                
                api_response_time = time.time() - api_start_time
                
                # 验证响应不为空
                if not response or not response.strip():
                    raise ValueError(f"API返回空内容")
                
                # 智能提取JSON内容
                json_content = self._extract_json_from_response(response)
                
                # 解析JSON
                structure = json.loads(json_content)
                
                # 验证结构完整性
                self._validate_document_structure(structure)
                
                # 记录成功
                self.orchestration_stats['successful_calls'] += 1
                if self.has_smart_control:
                    self.concurrency_manager.record_api_request(
                        agent_name='orchestrator_agent',
                        success=True,
                        response_time=api_response_time
                    )
                
                # 成功！
                sections_count = sum(len(part.get('sections', [])) for part in structure.get('report_guide', []))
                self.orchestration_stats['structure_generation_time'] = time.time() - structure_start_time
                
                self.logger.info(f"✅ 文档基础结构生成成功 (尝试 {attempt + 1}/{max_retries})")
                self.logger.info(f"📊 生成了 {len(structure.get('report_guide', []))} 个主要部分，{sections_count} 个子章节")
                return structure
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # 记录失败
                self.orchestration_stats['failed_calls'] += 1
                if self.has_smart_control:
                    error_type = self._classify_orchestrator_error(str(e))
                    self.concurrency_manager.record_api_request(
                        agent_name='orchestrator_agent',
                        success=False,
                        response_time=api_response_time if 'api_response_time' in locals() else 0,
                        error_type=error_type
                    )
                
                error_msg = f"第{attempt + 1}次尝试失败: {str(e)}"
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 递增等待时间: 2s, 4s, 6s
                    self.logger.warning(f"⚠️  {error_msg}")
                    self.logger.info(f"⏱️  等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    # 所有重试都失败了
                    self.logger.error(f"❌ 文档结构生成失败: {max_retries} 次重试全部失败")
                    self.logger.error(f"最后一次错误: {error_msg}")
                    if 'response' in locals():
                        self.logger.error(f"最后一次响应内容: {repr(response[:200])}...")
                    raise Exception(f"文档结构生成失败，{max_retries}次重试全部失败: {e}")
            
            except Exception as e:
                # 记录其他错误
                self.orchestration_stats['failed_calls'] += 1
                if self.has_smart_control:
                    self.concurrency_manager.record_api_request(
                        agent_name='orchestrator_agent',
                        success=False,
                        response_time=api_response_time if 'api_response_time' in locals() else 0,
                        error_type='unknown'
                    )
                
                # 其他未预期的错误
                self.logger.error(f"🚨 意外错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise Exception(f"文档结构生成遇到意外错误: {e}")
                time.sleep(2)
                continue
        
        # 理论上不会到达这里，但为了类型安全
        raise Exception("文档结构生成失败：未知错误")
    
    def _classify_orchestrator_error(self, error_message: str) -> str:
        """智能错误分类 - 编排Agent专用"""
        error_msg = error_message.lower()
        
        if 'rate limit' in error_msg or '429' in error_msg:
            return 'rate_limit'
        elif 'timeout' in error_msg:
            return 'timeout'
        elif 'json' in error_msg or 'format' in error_msg:
            return 'client_error'  # JSON格式错误视为客户端错误
        elif 'network' in error_msg or 'connection' in error_msg:
            return 'network'
        elif '5' in error_msg[:2]:  # 5xx errors
            return 'server_error'
        elif '4' in error_msg[:2]:  # 4xx errors
            return 'client_error'
        else:
            return 'unknown'

    def _extract_json_from_response(self, response: str) -> str:
        """
        从API响应中智能提取JSON内容
        
        Args:
            response: API原始响应
            
        Returns:
            str: 提取的JSON字符串
            
        Raises:
            ValueError: 当无法找到有效JSON时
        """
        if not response or not response.strip():
            raise ValueError("响应内容为空")
        
        # 先尝试直接解析（处理纯JSON响应）
        cleaned = response.strip()
        if cleaned.startswith('{') and cleaned.endswith('}'):
            return cleaned
        
        # 使用正则提取JSON内容
        import re
        
        # 方法1: 寻找大括号包围的内容
        json_pattern = r'(\{.*\})'
        match = re.search(json_pattern, response, re.DOTALL)
        if match:
            json_content = match.group(1).strip()
            # 简单验证是否像JSON
            if json_content.count('{') >= json_content.count('}') and '"report_guide"' in json_content:
                return json_content
        
        # 方法2: 寻找markdown代码块中的JSON
        markdown_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(markdown_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # 方法3: 行级扫描，寻找以{开头的行
        lines = response.split('\n')
        json_started = False
        json_lines = []
        brace_count = 0
        
        for line in lines:
            if not json_started and line.strip().startswith('{'):
                json_started = True
                json_lines.append(line)
                brace_count += line.count('{') - line.count('}')
            elif json_started:
                json_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0:
                    break
        
        if json_lines:
            potential_json = '\n'.join(json_lines).strip()
            if potential_json and '"report_guide"' in potential_json:
                return potential_json
        
        # 所有方法都失败了
        raise ValueError(f"无法从响应中提取有效JSON内容。响应前200字符: {response[:200]}...")

    def _validate_document_structure(self, structure: Dict[str, Any]) -> None:
        """
        验证文档结构的完整性
        
        Args:
            structure: 解析后的JSON结构
            
        Raises:
            ValueError: 当结构不完整时
        """
        if not isinstance(structure, dict):
            raise ValueError("结构必须是字典类型")
        
        if 'report_guide' not in structure:
            raise ValueError("缺少 'report_guide' 字段")
        
        report_guide = structure['report_guide']
        if not isinstance(report_guide, list) or len(report_guide) == 0:
            raise ValueError("'report_guide' 必须是非空列表")
        
        for i, part in enumerate(report_guide):
            if not isinstance(part, dict):
                raise ValueError(f"第{i+1}个部分必须是字典类型")
            
            if 'title' not in part or not part['title']:
                raise ValueError(f"第{i+1}个部分缺少标题")
            
            if 'sections' not in part or not isinstance(part['sections'], list) or len(part['sections']) == 0:
                raise ValueError(f"第{i+1}个部分缺少章节或章节为空")
            
            for j, section in enumerate(part['sections']):
                if not isinstance(section, dict) or 'subtitle' not in section or not section['subtitle']:
                    raise ValueError(f"第{i+1}个部分的第{j+1}个章节格式错误")
        
        self.logger.debug(f"✅ 文档结构验证通过: {len(report_guide)} 个部分")

    def add_writing_guides(self, structure: Dict[str, Any], user_description: str) -> Dict[str, Any]:
        """
        第二个函数：基于第一个函数生成的结构，为每个subtitle添加how_to_write字段
        优化版：按大章节分组，支持多线程并行处理，使用统一的并发管理
        
        Args:
            structure: 第一个函数生成的基础结构
            user_description: 用户描述
            
        Returns:
            Dict: 包含完整how_to_write字段的最终结构
        """
        
        self.logger.info("开始为每个子章节添加写作指导（优化版：按章节分组并行处理）...")
        
        # 深拷贝结构避免修改原始数据
        complete_guide = json.loads(json.dumps(structure))
        
        # 重置进度计数器
        self.processed_sections = 0
        total_sections = len(complete_guide.get('report_guide', []))
        
        print(f"📊 即将并行处理 {total_sections} 个大章节，并发线程数：{self.max_workers}")
        print(f"🔄 开始并行处理...")
        
        # 使用线程池并行处理各个大章节
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有章节处理任务
            future_to_section = {}
            for i, section in enumerate(complete_guide.get('report_guide', [])):
                section_title = section.get('title', f'第{i+1}章节')
                subsections_count = len(section.get('sections', []))
                
                print(f"📤 提交第{i + 1}个章节任务：{section_title} ({subsections_count}个子章节)")
                
                future = executor.submit(
                    self._process_section_writing_guides,
                    section,
                    user_description,
                    i + 1,
                    total_sections
                )
                future_to_section[future] = i
            
            print(f"✅ 已提交所有 {total_sections} 个章节任务，开始并行处理...")
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(future_to_section):
                section_index = future_to_section[future]
                try:
                    processed_section = future.result()
                    complete_guide['report_guide'][section_index] = processed_section
                    
                    with self.concurrency_manager.get_lock('orchestrator_agent'):
                        self.processed_sections += 1
                        section_title = processed_section.get('title', f'第{section_index + 1}章节')
                        progress_msg = f"✅ 完成第{section_index + 1}个章节的写作指导生成：{section_title} ({self.processed_sections}/{total_sections})"
                        self.logger.info(progress_msg)
                        print(progress_msg)  # 同时输出到控制台确保可见
                        
                except Exception as e:
                    error_msg = f"❌ 第{section_index + 1}个章节处理失败: {e}"
                    self.logger.error(error_msg)
                    print(error_msg)  # 同时输出到控制台
                    # 使用默认的写作指导
                    self._add_default_writing_guides(complete_guide['report_guide'][section_index])
        
        final_msg = "🎉 所有写作指导添加完成"
        self.logger.info(final_msg)
        print(final_msg)
        return complete_guide

    def _process_section_writing_guides(self, section: Dict[str, Any], user_description: str, 
                                      section_num: int, total_sections: int) -> Dict[str, Any]:
        """
        处理单个大章节的所有子章节写作指导
        优化：一次API调用处理整个章节的所有子章节
        
        Args:
            section: 章节信息
            user_description: 用户描述
            section_num: 章节编号
            total_sections: 总章节数
            
        Returns:
            Dict: 处理完成的章节数据
        """
        
        section_title = section.get('title', '')
        section_goal = section.get('goal', '')
        subsections = section.get('sections', [])
        
        start_msg = f"🔄 [线程{section_num}] 开始处理：{section_title} ({len(subsections)}个子章节)"
        self.logger.info(start_msg)
        print(start_msg)  # 同时输出到控制台
        
        # 构建包含所有子章节的提示词
        subtitles_list = []
        for i, subsection in enumerate(subsections):
            subtitles_list.append(f"{i+1}. {subsection.get('subtitle', '')}")
        
        subtitles_text = "\n".join(subtitles_list)
        
        prompt = f"""
你是一个专业文档写作指导专家。

项目背景：{user_description}

当前章节信息：
- 章节标题：{section_title}
- 章节目标：{section_goal}

当前章节包含以下子章节：
{subtitles_text}

请为这个章节下的每个子章节提供简洁、实用的写作指导。对于每个子章节，告诉作者：
1. 核心内容要点
2. 关键信息要求  
3. 写作注意事项

要求：
- 内容精炼，重点突出
- 针对性强，贴合项目特点
- 每个子章节的写作指导控制在100-200字内

请严格按照以下JSON格式返回：

{{
  "writing_guides": [
    {{
      "subtitle": "一、第一个子章节标题",
      "how_to_write": "详细的写作指导内容..."
    }},
    {{
      "subtitle": "二、第二个子章节标题", 
      "how_to_write": "详细的写作指导内容..."
    }}
  ]
}}

注意：
- 只返回JSON格式，不要其他解释
- 返回纯文本格式，不要使用markdown语法
- 确保每个子章节都有对应的写作指导
- 子章节标题要与输入完全一致
"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                attempt_msg = f"📡 [线程{section_num}] 第{attempt + 1}次尝试API调用..."
                self.logger.info(attempt_msg)
                print(attempt_msg)
                
                response = self.llm_client.generate(prompt)
                guides_data = json.loads(response.strip())
                
                # 将生成的写作指导应用到原始结构中
                guides_dict = {}
                for guide in guides_data.get('writing_guides', []):
                    guides_dict[guide.get('subtitle', '')] = guide.get('how_to_write', '')
                
                # 更新section中的子章节
                updated_count = 0
                for subsection in section.get('sections', []):
                    subtitle = subsection.get('subtitle', '')
                    if subtitle in guides_dict:
                        subsection['how_to_write'] = guides_dict[subtitle]
                        updated_count += 1
                    else:
                        # 如果没有找到对应的写作指导，使用默认内容
                        subsection['how_to_write'] = f"请围绕'{subtitle}'主题，结合项目实际情况详细描述相关内容。确保内容专业、准确、完整，符合该章节在整个文档中的作用和要求。"
                
                success_msg = f"✅ [线程{section_num}] 成功生成 {updated_count}/{len(subsections)} 个子章节的写作指导"
                self.logger.info(success_msg)
                print(success_msg)
                return section
                
            except json.JSONDecodeError as e:
                error_msg = f"⚠️ [线程{section_num}] JSON解析失败 (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                print(error_msg)
                if attempt == max_retries - 1:
                    final_error_msg = f"❌ [线程{section_num}] JSON解析最终失败，使用默认写作指导"
                    self.logger.error(final_error_msg)
                    print(final_error_msg)
                    self._add_default_writing_guides(section)
                    return section
                time.sleep(1)  # 等待1秒后重试
                
            except Exception as e:
                error_msg = f"⚠️ [线程{section_num}] 生成失败 (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                print(error_msg)
                if attempt == max_retries - 1:
                    final_error_msg = f"❌ [线程{section_num}] 生成最终失败，使用默认写作指导"
                    self.logger.error(final_error_msg)
                    print(final_error_msg)
                    self._add_default_writing_guides(section)
                    return section
                time.sleep(2)  # 等待2秒后重试
        
        # 如果所有重试都失败，返回带默认写作指导的section
        self._add_default_writing_guides(section)
        return section

    def _add_default_writing_guides(self, section: Dict[str, Any]):
        """
        为章节添加默认的写作指导
        
        Args:
            section: 章节数据
        """
        for subsection in section.get('sections', []):
            if 'how_to_write' not in subsection:
                subtitle = subsection.get('subtitle', '')
                subsection['how_to_write'] = f"请围绕'{subtitle}'主题，结合项目实际情况详细描述相关内容。确保内容专业、准确、完整，符合该章节在整个文档中的作用和要求。"

    def _generate_single_how_to_write(self, subtitle: str, section_title: str, 
                                    section_goal: str, user_description: str) -> str:
        """
        为单个子章节生成how_to_write指导 (已废弃，保留为兼容性)
        
        Args:
            subtitle: 子章节标题
            section_title: 所属章节标题
            section_goal: 章节目标
            user_description: 用户描述
            
        Returns:
            str: 详细的写作指导
        """
        
        self.logger.warning("使用废弃的单个子章节生成方法，建议使用新的批量生成方法")
        
        prompt = f"""
你是一个专业文档写作指导专家。

项目背景：{user_description}

当前章节信息：
- 章节标题：{section_title}
- 章节目标：{section_goal}
- 当前子章节：{subtitle}

请为这个具体的子章节提供简洁、实用的写作指导。告诉作者：
1. 核心内容要点
2. 关键信息要求
3. 写作注意事项

要求：
- 内容精炼，重点突出
- 针对性强，贴合项目特点
- 控制在150-250字内
- 返回纯文本格式，不要使用markdown语法或特殊符号

直接返回写作指导内容，不要前缀说明。
"""
        
        try:
            response = self.llm_client.generate(prompt)
            return response.strip()
        except Exception as e:
            self.logger.warning(f"生成子章节写作指导失败: {e}")
            return f"请围绕'{subtitle}'主题，结合项目实际情况详细描述相关内容。确保内容专业、准确、完整，符合该章节在整个文档中的作用和要求。"

    def _check_template_completeness(self, template: Dict[str, Any]) -> bool:
        """
        检查模板是否包含完整的写作指导
        
        Args:
            template: 模板结构
            
        Returns:
            bool: 是否包含完整的写作指导
        """
        report_guide = template.get('report_guide', [])
        total_sections = 0
        sections_with_guides = 0
        
        for part in report_guide:
            sections = part.get('sections', [])
            for section in sections:
                total_sections += 1
                if 'how_to_write' in section and section['how_to_write'].strip():
                    sections_with_guides += 1
        
        completion_rate = sections_with_guides / total_sections if total_sections > 0 else 0
        self.logger.info(f"📊 模板写作指导完整度: {completion_rate*100:.1f}% ({sections_with_guides}/{total_sections})")
        
        return sections_with_guides == total_sections

    def generate_complete_guide(self, user_description: str) -> Dict[str, Any]:
        """
        完整流程：查询模板 -> 生成基础结构 -> 添加写作指导
        新增：优先查询现有模板，如果找到完整模板则直接返回，无需额外处理
        
        Args:
            user_description: 用户描述
            
        Returns:
            Dict: 完整的文档编写指导JSON
        """
        
        self.logger.info("🚀 开始生成完整的文档编写指导...")
        
        # 🆕 新增步骤：查询现有模板
        existing_template = self.query_existing_template(user_description)
        
        if existing_template:
            self.logger.info("📋 找到现有模板，检查完整性...")
            
            # 检查模板是否包含完整的写作指导
            if self._check_template_completeness(existing_template):
                self.logger.info("🎉 模板包含完整写作指导，直接返回模板！")
                print("📋 ✅ 找到完整模板，直接使用！（无需额外生成写作指导）")
                return existing_template
            else:
                self.logger.info("📝 模板缺少部分写作指导，需要补充生成")
                print("📋 ⚠️ 找到模板但写作指导不完整，开始补充...")
                structure = existing_template
        else:
            self.logger.info("🔧 未找到现有模板，开始生成新的文档结构")
            print("🔧 未找到现有模板，开始生成新的文档结构...")
            
            # 第一步：生成基础结构（原有流程）
            structure = self.generate_document_structure(user_description)
        
        # 第二步：添加写作指导（仅当模板不完整或使用新生成结构时执行）
        self.logger.info("📝 开始添加写作指导...")
        complete_guide = self.add_writing_guides(structure, user_description)
        
        self.logger.info("🎉 完整的文档编写指导生成完成")
        return complete_guide 