"""
ReAct Agent - 智能速率控制增强版

此版本将并行处理逻辑封装在Agent内部，调用方只需调用一个方法即可处理整个报告。
集成智能速率控制系统，实现更高效的检索和处理。
"""

import json
import logging
import re
import requests
import sys
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import concurrent.futures

# 添加项目路径以导入相关模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 移除SimpleRAGClient导入
from clients.external_api_client import get_external_api_client
from config.settings import get_concurrency_manager, SmartConcurrencyManager

# ==============================================================================
# 1. 数据结构与辅助类
# ==============================================================================

class SectionInfo:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

@dataclass
class ReActState:
    iteration: int = 0
    attempted_queries: List[str] = field(default_factory=list)
    retrieved_results: List[Dict] = field(default_factory=list)
    quality_scores: List[float] = field(default_factory=list)
    processed_pages: set = field(default_factory=set)  # 跟踪已处理的页数

class ColoredLogger:
    COLORS = {
        'RESET': '\033[0m', 'BLUE': '\033[94m', 'GREEN': '\033[92m', 
        'YELLOW': '\033[93m', 'RED': '\033[91m', 'PURPLE': '\033[95m', 
        'CYAN': '\033[96m', 'WHITE': '\033[97m',
    }
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _colorize(self, text: str, color: str) -> str:
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['RESET']}"
    
    def info(self, message: str): self.logger.info(message)
    def error(self, message: str): self.logger.error(message)
    def warning(self, message: str): self.logger.warning(message)
    def debug(self, message: str): self.logger.debug(message)
    def thought(self, content: str): self.logger.info(self._colorize(f"💭 Thought: {content}", 'BLUE'))
    def input_tool(self, content: str): self.logger.info(self._colorize(f"🔧 Input: {content}", 'GREEN'))
    def observation(self, content: str): self.logger.info(self._colorize(f"👁️ Observation: {content}", 'YELLOW'))
    def reflection(self, content: str): self.logger.info(self._colorize(f"🤔 Reflection: {content}", 'CYAN'))
    def section_start(self, title: str): self.logger.info(self._colorize(f"\n📝 开始处理章节: {title}", 'PURPLE'))
    def section_complete(self, title: str, iterations: int, quality: float): self.logger.info(self._colorize(f"✅ 章节'{title}'完成 | 迭代{iterations}次 | 最终质量: {quality:.2f}", 'WHITE'))
    def iteration(self, current: int, total: int): self.logger.info(self._colorize(f"🔄 [Iteration {current}/{total}]", 'CYAN'))

# ==============================================================================
# 2. 核心Agent类
# ==============================================================================

class EnhancedReactAgent:
    def __init__(self, client: Any, concurrency_manager: SmartConcurrencyManager = None):
        self.client = client
        self.colored_logger = ColoredLogger(__name__)
        self.max_iterations = 3
        self.quality_threshold = 0.7
        
        # 使用外部API进行文档检索
        
        # 外部API客户端
        self.external_api = get_external_api_client()
        
        # 智能并发管理器
        self.concurrency_manager = concurrency_manager or get_concurrency_manager()
        self.max_workers = self.concurrency_manager.get_max_workers('react_agent')
        
        # 智能速率控制器
        self.rate_limiter = self.concurrency_manager.get_rate_limiter('react_agent')
        self.has_smart_control = self.concurrency_manager.has_smart_rate_control('react_agent')
        
        # 性能统计
        self.react_stats = {
            'total_sections_processed': 0,
            'total_external_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'total_processing_time': 0.0,
            'avg_quality_score': 0.0
        }
        
        self.query_strategies = {
            'direct': "直接使用核心关键词搜索", 
            'contextual': "结合写作指导上下文的详细查询", 
            'semantic': "搜索与主题相关的语义概念", 
            'specific': "搜索具体的案例、数据或技术标准",
            'alternative': "使用同义词和相关概念进行发散搜索"
        }
        
        status_msg = f"智能速率控制: {'已启用' if self.has_smart_control else '传统模式'}"
        self.colored_logger.info(f"EnhancedReactAgent 初始化完成，并发线程数: {self.max_workers}, {status_msg}")
        
        # 检查外部API服务状态
        try:
            api_status = self.external_api.check_service_status()
            if api_status.get('status') == 'running':
                self.colored_logger.info(f"✅ 外部API服务连接正常: {api_status.get('service', '')} v{api_status.get('version', '')}")
            else:
                self.colored_logger.warning(f"⚠️ 外部API服务状态异常: {api_status}，将使用本地RAG作为备用")
        except Exception as e:
            self.colored_logger.error(f"❌ 外部API服务连接检查失败: {e}，将使用本地RAG作为备用")

    def set_max_workers(self, max_workers: int):
        """动态设置最大线程数"""
        self.max_workers = max_workers
        self.concurrency_manager.set_max_workers('react_agent', max_workers)
        self.colored_logger.info(f"ReactAgent 线程数已更新为: {max_workers}")

    def get_max_workers(self) -> int:
        """获取当前最大线程数"""
        return self.max_workers

    def process_report_guide(self, report_guide_data: Dict[str, Any], project_name: str = "医灵古庙") -> Dict[str, Any]:
        """处理完整的报告指南 - 主入口 (并行处理)"""
        self.colored_logger.logger.info(f"🤖 ReAct开始并行处理报告指南... (项目: {project_name}, 线程数: {self.max_workers})")
        result_data = json.loads(json.dumps(report_guide_data))
        self.current_project_name = project_name  # 存储项目名称供后续使用
        
        tasks = []
        for part in result_data.get('report_guide', []):
            part_context = {'title': part.get('title', ''), 'goal': part.get('goal', '')}
            for section in part.get('sections', []):
                tasks.append((section, part_context))

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_section = {
                executor.submit(self._process_section_with_react, section, part_context): section
                for section, part_context in tasks
            }
            for future in concurrent.futures.as_completed(future_to_section):
                section = future_to_section[future]
                try:
                    # 获取处理结果
                    result = future.result()
                    
                    # 检查结果类型，如果是字典则分别存储三个字段，否则存储为retrieved_data
                    if isinstance(result, dict) and all(key in result for key in ['retrieved_text', 'retrieved_image', 'retrieved_table']):
                        section['retrieved_text'] = result['retrieved_text']
                        section['retrieved_image'] = result['retrieved_image'] 
                        section['retrieved_table'] = result['retrieved_table']
                    else:
                        # 向后兼容：如果返回字符串，则存储为retrieved_data
                        section['retrieved_data'] = result
                except Exception as exc:
                    error_message = f"章节 '{section.get('subtitle')}' 在并行处理中发生错误: {exc}"
                    self.colored_logger.error(error_message)
                    section['retrieved_data'] = error_message
        
        self.colored_logger.logger.info("\n✅ 所有章节并行处理完成！")
        return result_data

    def _process_section_with_react(self, section_data: dict, part_context: dict) -> str:
        """为单个章节启动并管理ReAct处理流程。"""
        subtitle = section_data.get('subtitle', '')
        self.colored_logger.section_start(subtitle)
        state = ReActState()
        section_context = {
            'subtitle': subtitle, 'how_to_write': section_data.get('how_to_write', ''),
            'part_title': part_context.get('title', ''), 'part_goal': part_context.get('goal', '')
        }
        retrieved_content = self._react_loop_for_section(section_context, state)
        self.colored_logger.section_complete(subtitle, state.iteration, max(state.quality_scores) if state.quality_scores else 0)
        return retrieved_content

    def _react_loop_for_section(self, section_context: Dict[str, str], state: ReActState) -> str:
        """ReAct的核心循环 - 分段搜索模式，每个subtitle只搜索一次"""
        # 分段搜索模式：每个subtitle只进行一次搜索
        state.iteration = 1
        self.colored_logger.iteration(state.iteration, 1)  # 显示1/1
        
        action_plan = self._reason_and_act_for_section(section_context, state)
        if not action_plan or not action_plan.get('keywords'):
            self.colored_logger.thought("未能生成有效的行动计划，提前结束。")
            return self._synthesize_retrieved_results(section_context, state)

        reasoning, query, strategy = (action_plan.get('analysis'), action_plan.get('keywords'), action_plan.get('strategy'))
        state.attempted_queries.append(f"{strategy}:{query}")
        self.colored_logger.thought(reasoning)
        self.colored_logger.input_tool(f"外部API搜索 | Strategy: {strategy} | Query: {query}")
        
        results, quality_score = self._observe_section_results(query, section_context, state)
        state.retrieved_results.extend(results)
        state.quality_scores.append(quality_score)
        self.colored_logger.observation(f"检索到 {len(results)} 条结果, 评估质量分: {quality_score:.2f}")
        
        # 分段搜索模式：不进行质量反思，直接返回结果
        self.colored_logger.reflection(f"分段搜索模式：单次搜索完成，质量分: {quality_score:.2f}")
                
        return self._synthesize_retrieved_results(section_context, state)

    def _reason_and_act_for_section(self, section_context: Dict[str, str], state: ReActState) -> Optional[Dict[str, str]]:
        """合并推理和行动阶段"""
        used_strategies = {q.split(':')[0] for q in state.attempted_queries if ':' in q}
        available_strategies = {k: v for k, v in self.query_strategies.items() if k not in used_strategies} or self.query_strategies
        prompt = f"""
作为一名专业的信息检索分析师，为报告章节制定检索计划。
【目标章节】: {section_context['subtitle']}
【写作指导】: {section_context['how_to_write']}
【历史尝试】: 已尝试查询: {state.attempted_queries[-3:]}, 历史质量: {state.quality_scores[-3:]}
【可用策略】: {json.dumps(available_strategies, ensure_ascii=False)}
【任务】: 1.分析现状。2.选择一个最佳策略。3.生成3-5个关键词。
【输出格式】: 必须严格返回以下JSON格式:
{{
  "analysis": "简要分析（100字内）",
  "strategy": "选择的策略名称",
  "keywords": "用逗号分隔的关键词"
}}"""
        try:
            response_str = self.client.generate(prompt)
            match = re.search(r'\{.*\}', response_str, re.DOTALL)
            action_plan = json.loads(match.group(0))
            if all(k in action_plan for k in ['analysis', 'strategy', 'keywords']):
                return action_plan
            self.colored_logger.error(f"LLM返回的JSON格式不完整: {action_plan}")
            return None
        except Exception as e:
            self.colored_logger.error(f"推理与行动阶段出错: {e}")
            return None

    def _observe_section_results(self, query: str, section_context: Dict[str, str], state: ReActState = None) -> Tuple[List[Dict], float]:
        """观察阶段（使用外部API进行文档搜索）"""
        query_start_time = time.time()
        
        try:
            # 智能速率控制
            if self.has_smart_control:
                delay = self.rate_limiter.get_delay()
                if delay > 0:
                    time.sleep(delay)
            
            # 使用外部API进行文档搜索
            all_results = []
            
            # 记录外部API查询开始
            self.react_stats['total_external_queries'] += 1
            
            # 执行外部API文档搜索
            api_start_time = time.time()
            keywords = [k.strip() for k in query.replace('，', ',').split(',') if k.strip()]
            combined_query = " ".join(keywords[:3])
            
            # 使用混合内容搜索API
            search_results = self.external_api.document_search(
                query=combined_query,
                project_name=getattr(self, 'current_project_name', '医灵古庙')
            )
            
            api_response_time = time.time() - api_start_time
            
            if search_results:
                # 处理混合内容搜索API返回结果
                all_results = []
                
                # 获取搜索结果数组
                results_data = search_results.get('data', {}).get('results', [])
                self.colored_logger.debug(f"🔍 混合内容搜索结果数量: {len(results_data)}")
                
                for item in results_data:
                    page_number = item.get('page_number', 'N/A')
                    content = item.get('content', '')
                    images = item.get('images', [])
                    similarity = item.get('similarity', 0.0)
                    rerank_score = item.get('rerank_score', 0.0)
                    mixed_score = item.get('mixed_score', 0.0)
                    source_type = item.get('source_type', 'unknown')
                    
                    self.colored_logger.debug(f"📄 处理第{page_number}页，类型: {source_type}，混合分数: {mixed_score:.3f}")
                    
                    # 根据source_type确定内容类型
                    if source_type == 'page_text':
                        # 文本内容
                        all_results.append({
                            'content': f"{content}",
                            'source': f"第{page_number}页文本 (混合分数: {mixed_score:.3f})",
                            'type': 'text',
                            'score': mixed_score,
                            'page_number': page_number,
                            'similarity': similarity,
                            'rerank_score': rerank_score
                        })
                        
                        # 处理该页面包含的图片
                        for image_url in images:
                            clean_url = image_url.strip().strip('`').strip()
                            if clean_url:
                                all_results.append({
                                    'content': f"[第{page_number}页] 图片",
                                    'source': f"第{page_number}页图片 (混合分数: {mixed_score:.3f})",
                                    'type': 'image',
                                    'score': mixed_score,
                                    'page_number': page_number,
                                    'path': clean_url,
                                    'description': f"第{page_number}页图片"
                                })
                    
                    elif source_type == 'detailed_description':
                        # 图片描述内容
                        for image_url in images:
                            clean_url = image_url.strip().strip('`').strip()
                            if clean_url:
                                all_results.append({
                                    'content': f"图片描述: {content}",
                                    'source': f"第{page_number}页图片描述 (混合分数: {mixed_score:.3f})",
                                    'type': 'image',
                                    'score': mixed_score,
                                    'page_number': page_number,
                                    'path': clean_url,
                                    'description': content,
                                    'detailed_description': content,
                                    'similarity': similarity,
                                    'rerank_score': rerank_score
                                })
                    
                    else:
                        # 其他类型内容，作为通用处理
                        all_results.append({
                            'content': f"{content}",
                            'source': f"第{page_number}页{source_type} (混合分数: {mixed_score:.3f})",
                            'type': 'text',
                            'score': mixed_score,
                            'page_number': page_number,
                            'similarity': similarity,
                            'rerank_score': rerank_score
                        })

                
                # 分段搜索模式，不进行页数去重
                
                total_text = len([r for r in all_results if r.get('type') == 'text'])
                total_image = len([r for r in all_results if r.get('type') == 'image'])
                total_table = len([r for r in all_results if r.get('type') == 'table'])
                
                # 显示检索结果统计
                self.colored_logger.observation(f"✅ 混合内容搜索成功，获得 {len(all_results)} 条结果 "
                                              f"(文本:{total_text}, 图片:{total_image}, 表格:{total_table})")
            else:
                self.colored_logger.observation("📭 检索未返回结果")
                all_results = []
            
            # 质量评估
            quality_score = self._evaluate_section_results_quality(all_results, section_context, query)
            
            # 记录成功的查询
            if self.has_smart_control:
                self.concurrency_manager.record_api_request(
                    agent_name='react_agent',
                    success=True,
                    response_time=api_response_time
                )
            self.react_stats['successful_queries'] += 1
            
            return all_results, quality_score
            
        except Exception as e:
            # 记录失败的查询
            query_response_time = time.time() - query_start_time
            if self.has_smart_control:
                error_type = self._classify_react_error(str(e))
                self.concurrency_manager.record_api_request(
                    agent_name='react_agent',
                    success=False,
                    response_time=query_response_time,
                    error_type=error_type
                )
            self.react_stats['failed_queries'] += 1
            
            self.colored_logger.error(f"观察阶段失败: {e}")
            return [], 0.0
    


    def _classify_react_error(self, error_message: str) -> str:
        """智能错误分类 - ReAct Agent专用"""
        error_msg = error_message.lower()
        
        if 'rate limit' in error_msg or '429' in error_msg:
            return 'rate_limit'
        elif 'timeout' in error_msg:
            return 'timeout'
        elif 'network' in error_msg or 'connection' in error_msg:
            return 'network'
        elif 'rag' in error_msg or 'retrieval' in error_msg:
            return 'client_error'  # RAG检索错误视为客户端错误
        elif '5' in error_msg[:2]:  # 5xx errors
            return 'server_error'
        elif '4' in error_msg[:2]:  # 4xx errors
            return 'client_error'
        else:
            return 'unknown'

    def _evaluate_section_results_quality(self, results: List[Dict], section_context: Dict[str, str], query: str) -> float:
        """评估结果质量"""
        if not results: return 0.0
        
        # 安全地处理内容，确保转换为字符串
        def safe_content_str(result):
            content = result.get('content', result)
            if isinstance(content, (list, dict)):
                return str(content)[:150]
            return str(content)[:150]
        
        evaluation_prompt = f"""
评估以下检索结果对章节写作的适用性：
【目标章节】: {section_context['subtitle']}
【写作指导】: {section_context['how_to_write']}
【本次查询】: {query}
【检索结果】: {chr(10).join(f"- {safe_content_str(r)}..." for r in results[:3])}
【要求】: 综合评估后，只返回一个0.0到1.0的小数评分。"""
        try:
            response = self.client.generate(evaluation_prompt)
            score_match = re.search(r'0?\.\d+|[01]', response)
            return max(0.0, min(1.0, float(score_match.group()))) if score_match else 0.2
        except Exception: return 0.1

    def _reflect(self, state: ReActState, current_quality: float) -> bool:
        """反思阶段"""
        if current_quality >= self.quality_threshold:
            self.colored_logger.reflection(f"质量分 {current_quality:.2f} 达标, 停止。")
            return False
        if state.iteration >= self.max_iterations:
            self.colored_logger.reflection(f"达到最大迭代次数, 停止。")
            return False
        if len(state.quality_scores) >= 2 and all(s < 0.3 for s in state.quality_scores[-2:]):
            self.colored_logger.reflection("质量分持续过低, 提前停止。")
            return False
        return True

    def _synthesize_retrieved_results(self, section_context: Dict[str, str], state: ReActState) -> Dict[str, List]:
        """合成最终结果为三个分离的字段"""
        if not state.retrieved_results:
            return {
                'retrieved_text': [],
                'retrieved_image': [],
                'retrieved_table': []
            }
        
        # 按类型分组结果
        retrieved_text = []
        retrieved_image = []
        retrieved_table = []
        
        for result in state.retrieved_results:
            result_type = result.get('type', 'text')
            if result_type == 'text':
                retrieved_text.append(result)
            elif result_type == 'image':
                retrieved_image.append(result)
            elif result_type == 'table':
                retrieved_table.append(result)
            else:
                # 默认归类为文本
                retrieved_text.append(result)
        
        # 添加调试日志，显示分组结果
        self.colored_logger.debug(f"📊 分组结果: 文本{len(retrieved_text)}条, 图片{len(retrieved_image)}条, 表格{len(retrieved_table)}条")
        
        # 显示图片结果的详细信息
        for i, img in enumerate(retrieved_image):
            self.colored_logger.debug(f"📸 图片{i+1}: 路径={img.get('path', 'N/A')}, 页数={img.get('page_number', 'N/A')}, 描述={img.get('description', 'N/A')[:50]}...")
        
        # 分段搜索模式，不进行去重处理
        self.colored_logger.debug(f"📊 分段搜索结果: 文本{len(retrieved_text)}条, 图片{len(retrieved_image)}条, 表格{len(retrieved_table)}条")
        
        # 分段搜索结果统计
        self.colored_logger.observation(f"📊 最终结果统计: 文本{len(retrieved_text)}条, "
                                      f"图片{len(retrieved_image)}条, "
                                      f"表格{len(retrieved_table)}条")

        # 确保图片结果包含完整的路径和描述信息
        final_image_results = []
        for img_result in retrieved_image:
            # 保留所有重要的图片信息
            final_img = {
                'content': img_result.get('content', ''),
                'source': img_result.get('source', '外部API'),
                'type': 'image',
                'path': img_result.get('path', ''),
                'page_number': img_result.get('page_number', ''),
                'description': img_result.get('description', ''),
                'score': img_result.get('score', 1.0),
                # 保留详细描述和工程技术信息
                'detailed_description': img_result.get('detailed_description', ''),
                'engineering_details': img_result.get('engineering_details', '')
            }
            final_image_results.append(final_img)
            
            # 添加调试日志
            self.colored_logger.debug(f"📸 最终图片结果: 路径={final_img['path']}, 描述={final_img['description']}, 页数={final_img['page_number']}, 详细描述={final_img['detailed_description'][:50]}...")
        
        # 确保表格结果包含页数信息
        final_table_results = []
        for table_result in retrieved_table:
            final_table_results.append({
                'content': table_result.get('content', ''),
                'source': table_result.get('source', '外部API'),
                'type': 'table',
                'page_number': table_result.get('page_number', ''),
                'score': table_result.get('score', 1.0)
            })
        
        # 确保文本结果包含页数信息
        final_text_results = []
        for text_result in retrieved_text:
            final_text_results.append({
                'content': text_result.get('content', ''),
                'source': text_result.get('source', '外部API'),
                'type': 'text',
                'page_number': text_result.get('page_number', ''),
                'score': text_result.get('score', 1.0)
            })

        return {
            'retrieved_text': final_text_results,
            'retrieved_image': final_image_results,
            'retrieved_table': final_table_results
        }
