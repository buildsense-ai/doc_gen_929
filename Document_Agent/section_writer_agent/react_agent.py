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
from clients.web_search_client import get_web_search_client
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
        
        # Web搜索客户端
        self.web_search_client = get_web_search_client()
        
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
        
        # 检查Web搜索服务状态（支持跳过）
        try:
            web_status = self.web_search_client.check_service_status()
            if web_status.get('status') == 'running':
                if web_status.get('skipped'):
                    self.colored_logger.info("✅ Web搜索服务假定可用（已跳过健康检查）")
                else:
                    self.colored_logger.info(f"✅ Web搜索服务连接正常: {web_status.get('service', '')}")
            else:
                self.colored_logger.warning(f"⚠️ Web搜索服务状态异常: {web_status}")
        except Exception as e:
            self.colored_logger.error(f"❌ Web搜索服务连接检查失败: {e}")

    def set_max_workers(self, max_workers: int):
        """动态设置最大线程数"""
        self.max_workers = max_workers
        self.concurrency_manager.set_max_workers('react_agent', max_workers)
        self.colored_logger.info(f"ReactAgent 线程数已更新为: {max_workers}")

    def get_max_workers(self) -> int:
        """获取当前最大线程数"""
        return self.max_workers

    def process_report_guide(self, report_guide_data: Dict[str, Any], project_name: str = "医灵古庙") -> Dict[str, Any]:
        """处理完整的报告指南 - 主入口 (并行处理顶层，递归处理所有层级)"""
        self.colored_logger.logger.info(f"🤖 ReAct开始并行处理报告指南... (项目: {project_name}, 线程数: {self.max_workers})")
        result_data = json.loads(json.dumps(report_guide_data))
        self.current_project_name = project_name  # 存储项目名称供后续使用

        # 并行仅用于顶层sections，子层级在各自任务中递归串行处理，降低任务调度开销
        tasks = []
        for part in result_data.get('report_guide', []):
            part_context = {'title': part.get('title', ''), 'goal': part.get('goal', '')}
            for section in part.get('sections', []):
                tasks.append((section, part_context, [part_context.get('title', '')]))

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_payload = {
                executor.submit(self._process_node_recursive, section, part_context, breadcrumb): (section, part_context)
                for section, part_context, breadcrumb in tasks
            }
            for future in concurrent.futures.as_completed(future_to_payload):
                try:
                    future.result()
                except Exception as exc:
                    section, _ = future_to_payload[future]
                    error_message = f"章节 '{section.get('subtitle')}' 在并行处理中发生错误: {exc}"
                    self.colored_logger.error(error_message)
                    section['retrieved_data'] = error_message

        self.colored_logger.logger.info("\n✅ 所有章节并行处理完成！")
        return result_data

    def _process_node_recursive(self, node: Dict[str, Any], part_context: Dict[str, str], breadcrumb: List[str]) -> None:
        """对单个节点执行ReAct，并递归处理其子节点。"""
        result = self._process_section_with_react(node, part_context)
        if isinstance(result, dict) and all(k in result for k in ['retrieved_text', 'retrieved_image', 'retrieved_table']):
            node['retrieved_text'] = result['retrieved_text']
            node['retrieved_image'] = result['retrieved_image']
            node['retrieved_table'] = result['retrieved_table']
            # 添加Web搜索结果处理
            if 'retrieved_web' in result:
                node['retrieved_web'] = result['retrieved_web']
        else:
            node['retrieved_data'] = result

        # 递归处理子节点
        for child in node.get('subsections', []) or []:
            self._process_node_recursive(child, part_context, breadcrumb + [node.get('subtitle', '')])

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
        """ReAct的核心循环 - 多维度并行查询模式"""
        state.iteration = 1
        self.colored_logger.iteration(state.iteration, 1)
        
        # 生成多维度查询计划
        multi_queries = self._generate_multi_dimensional_queries(section_context, state)
        if not multi_queries:
            self.colored_logger.thought("未能生成有效的多维度查询计划，提前结束。")
            return self._synthesize_retrieved_results(section_context, state)

        self.colored_logger.thought(f"生成了 {len(multi_queries)} 个维度的查询计划")
        
        # 并行执行多个RAG查询
        all_results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(multi_queries), 3)) as executor:
            future_to_query = {
                executor.submit(self._execute_single_query, query_info, section_context, state): query_info
                for query_info in multi_queries
            }
            
            for future in concurrent.futures.as_completed(future_to_query):
                query_info = future_to_query[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    self.colored_logger.observation(f"维度'{query_info['dimension']}'检索完成: {len(results)}条结果")
                except Exception as exc:
                    self.colored_logger.error(f"维度'{query_info['dimension']}'查询失败: {exc}")
        
        # 合并所有RAG结果
        state.retrieved_results.extend(all_results)
        
        self.colored_logger.reflection(f"RAG多维度查询完成: 总计{len(all_results)}条结果")
        
        # 必定执行Web搜索补充：分析RAG结果缺口后进行针对性Web搜索
        self.colored_logger.thought(f"🤔 分析RAG检索结果，识别信息缺口...")
        web_results = self._perform_intelligent_web_search(section_context, all_results)
        if web_results:
            all_results.extend(web_results)
            state.retrieved_results.extend(web_results)
            self.colored_logger.observation(f"🌐 智能Web搜索补充: 新增 {len(web_results)} 条结果")
        else:
            self.colored_logger.warning("🌐 Web搜索未返回结果")
                
        return self._synthesize_retrieved_results(section_context, state)

    def _generate_multi_dimensional_queries(self, section_context: Dict[str, str], state: ReActState) -> List[Dict[str, str]]:
        """生成多维度查询计划"""
        # 获取项目名称，用于生成更精准的查询
        project_name = getattr(self, 'current_project_name', '')
        
        prompt = f"""
你是专业的报告编制专家，需要为特定项目的报告章节制定精准的资料检索计划。

【项目信息】: {project_name}
【目标章节】: {section_context['subtitle']}
【写作要求】: {section_context['how_to_write']}

【核心任务】: 深度分析写作要求，识别完成该章节写作的必备资料类型，生成精准的检索查询。

【分析步骤】:
1. 从写作要求中提取关键信息要素（数据、政策、标准、案例等）
2. 结合项目特点确定检索的业务领域和范围
3. 针对每类必备资料设计最有效的检索词组

【查询生成原则】:
1. 【紧扣写作要求】: 查询必须直接服务于写作要求中的具体内容
2. 【项目特定性】: 结合项目名称中的关键信息（行业、地域、类型）
3. 【资料导向】: 重点检索能直接用于写作的具体资料
4. 【精准简洁】: 每个查询2-4个核心关键词，避免宽泛概念

【输出要求】: 严格返回JSON数组，包含2-3个最关键的检索维度:
[
  {{"dimension": "资料类型描述", "query": "精准查询词组", "priority": "high/medium/low"}},
  {{"dimension": "资料类型描述", "query": "精准查询词组", "priority": "high/medium/low"}}
]

【示例参考】:
- 政策类资料: "职业教育法 实施细则" 
- 标准类资料: "中职学校 建设标准"
- 数据类资料: "清远市 教育统计"
- 案例类资料: "职业教育基地 建设案例"
"""
        
        try:
            response_str = self.client.generate(prompt)
            # 提取JSON数组
            import re
            json_match = re.search(r'\[.*?\]', response_str, re.DOTALL)
            if json_match:
                queries = json.loads(json_match.group(0))
                # 验证格式
                valid_queries = []
                for q in queries:
                    if isinstance(q, dict) and all(k in q for k in ['dimension', 'query', 'priority']):
                        valid_queries.append(q)
                
                self.colored_logger.debug(f"🎯 生成多维度查询: {[q['dimension'] for q in valid_queries]}")
                return valid_queries
            else:
                self.colored_logger.error("未能从LLM响应中提取有效的JSON数组")
                return []
        except Exception as e:
            self.colored_logger.error(f"生成多维度查询失败: {e}")
            return []

    def _execute_single_query(self, query_info: Dict[str, str], section_context: Dict[str, str], state: ReActState) -> List[Dict]:
        """执行单个维度的查询"""
        query = query_info['query']
        dimension = query_info['dimension']
        
        self.colored_logger.input_tool(f"🔍 {dimension} | Query: {query}")
        
        # 记录查询尝试
        state.attempted_queries.append(f"{dimension}:{query}")
        
        # 执行查询
        results = self._observe_section_results(query, section_context, state)
        
        # 为结果添加维度标记
        for result in results:
            result['dimension'] = dimension
            result['priority'] = query_info.get('priority', 'medium')
        
        return results

    def _perform_intelligent_web_search(self, section_context: Dict[str, str], rag_results: List[Dict]) -> List[Dict[str, Any]]:
        """基于RAG结果分析进行智能Web搜索"""
        try:
            # 分析RAG结果的内容缺口
            web_query = self._analyze_rag_gaps_and_generate_query(section_context, rag_results)
            if not web_query:
                self.colored_logger.warning("❌ 未能生成Web搜索查询，跳过Web搜索补充")
                return []
            
            self.colored_logger.input_tool(f"🌐 智能Web搜索 | Query: {web_query}")
            
            # 执行Web搜索
            search_results = self.web_search_client.search(
                query=web_query,
                engines=["serp"],
                max_results=5
            )
            
            if not search_results:
                self.colored_logger.warning("🌐 Web搜索未返回结果")
                return []
            
            # 格式化Web搜索结果
            formatted_results = self.web_search_client.format_search_results(search_results)
            
            # 为Web搜索结果添加标记
            for result in formatted_results:
                result['dimension'] = 'web_intelligent'
                result['priority'] = 'medium'  # Web搜索作为补充，优先级中等
                result['type'] = 'web_text'
            
            return formatted_results
            
        except Exception as e:
            self.colored_logger.error(f"❌ 智能Web搜索失败: {e}")
            return []

    def _analyze_rag_gaps_and_generate_query(self, section_context: Dict[str, str], rag_results: List[Dict]) -> Optional[str]:
        """分析RAG结果缺口并生成Web搜索查询"""
        
        # 安全地处理RAG结果内容
        def safe_content_summary(results):
            if not results:
                return "无检索结果"
            
            content_snippets = []
            for result in results[:3]:  # 只分析前3个结果
                content = result.get('content', '')
                if isinstance(content, str) and content.strip():
                    content_snippets.append(content[:80])  # 取前80字符
            
            return " | ".join(content_snippets) if content_snippets else "检索结果为空"
        
        rag_summary = safe_content_summary(rag_results)
        
        # 获取项目名称，用于生成更精准的查询
        project_name = getattr(self, 'current_project_name', '')
        
        prompt = f"""
你是专业的报告编制专家，需要为当前报告章节生成精准的Web搜索查询。

【项目名称】: {project_name}
【目标章节】: {section_context['subtitle']}
【写作要求】: {section_context['how_to_write']}
【RAG已有内容】: {rag_summary}

【核心任务】: 基于RAG检索结果的不足，生成1个精准的Web搜索查询来补充关键信息

【查询生成原则】:
1. 【主题聚焦】: 紧扣项目名称和章节主题，提取核心业务领域关键词
2. 【内容互补】: 重点补充RAG缺失的信息（政策法规、标准规范、案例参考、最新数据）
3. 【精准简洁】: 查询词控制在3-6个核心词汇，避免冗长拼接
4. 【时效优先】: 优先获取最新的行业信息和政策动态

【输出要求】: 
- 只返回搜索查询词，用空格分隔
- 长度限制：3-6个关键词
- 必须贴合项目主题和章节内容
- 不要任何解释或其他内容

【查询构建逻辑】:
1. 从项目名称中提取行业/领域关键词
2. 结合章节要求确定信息类型（政策/标准/数据/案例）
3. 生成简洁有效的搜索词组合
"""
        
        try:
            response = self.client.generate(prompt)
            # 提取并清理查询词
            web_query = response.strip().replace('\n', ' ').replace('\r', ' ')
            web_query = ' '.join(web_query.split())  # 移除多余空格
            
            # 移除可能的引号和其他标点符号
            web_query = web_query.replace('"', '').replace("'", '').replace('，', ' ').replace('、', ' ')
            web_query = ' '.join(web_query.split())  # 再次清理空格
            
            # 限制查询词数量（3-6个词）
            query_words = web_query.split()
            if len(query_words) > 6:
                web_query = ' '.join(query_words[:6])
            
            # 确保查询长度合理
            if len(web_query) > 50:
                web_query = web_query[:50].rsplit(' ', 1)[0]
            
            if web_query and len(web_query.split()) >= 2:
                self.colored_logger.debug(f"🎯 智能生成Web查询: {web_query}")
                return web_query
            else:
                self.colored_logger.warning(f"LLM生成的查询不符合要求: '{response}' -> '{web_query}'，跳过Web搜索")
                return None
                
        except Exception as e:
            self.colored_logger.error(f"分析RAG缺口失败: {e}，跳过Web搜索")
            return None

    def _perform_web_search_supplement(self, section_context: Dict[str, str], multi_queries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """执行Web搜索补充"""
        try:
            # 生成Web搜索查询
            web_query = self._generate_web_search_query(section_context, multi_queries)
            if not web_query:
                return []
            
            self.colored_logger.input_tool(f"🌐 Web搜索补充 | Query: {web_query}")
            
            # 执行Web搜索
            search_results = self.web_search_client.search(
                query=web_query,
                engines=["serp"],
                max_results=5  # 限制Web搜索结果数量
            )
            
            if not search_results:
                self.colored_logger.warning("🌐 Web搜索未返回结果")
                return []
            
            # 格式化Web搜索结果
            formatted_results = self.web_search_client.format_search_results(search_results)
            
            # 为Web搜索结果添加维度标记
            for result in formatted_results:
                result['dimension'] = 'web_supplement'
                result['priority'] = 'medium'  # Web搜索结果作为补充，优先级中等
            
            return formatted_results
            
        except Exception as e:
            self.colored_logger.error(f"❌ Web搜索补充失败: {e}")
            return []
    
    def _generate_web_search_query(self, section_context: Dict[str, str], multi_queries: List[Dict[str, str]]) -> Optional[str]:
        """生成Web搜索查询词"""
        try:
            # 提取章节标题的关键信息
            subtitle = section_context.get('subtitle', '')
            
            # 构建Web搜索查询
            # 优先使用最重要的维度查询
            primary_queries = [q['query'] for q in multi_queries if q.get('priority') == 'high']
            if not primary_queries:
                primary_queries = [q['query'] for q in multi_queries[:1]]  # 取第一个查询
            
            if primary_queries:
                # 结合章节标题和主要查询构建Web搜索词
                web_query = f"{primary_queries[0]} {subtitle}".strip()
                # 清理查询词，移除特殊字符
                web_query = ' '.join(web_query.split())
                return web_query[:100]  # 限制查询长度
            
            return None
            
        except Exception as e:
            self.colored_logger.error(f"❌ 生成Web搜索查询失败: {e}")
            return None

    def _deduplicate_results(self, results: List[Dict], result_type: str) -> List[Dict]:
        """智能去重处理"""
        if not results:
            return results
        
        # 根据不同类型采用不同的去重策略
        if result_type == 'text':
            return self._deduplicate_text_results(results)
        elif result_type == 'image':
            return self._deduplicate_image_results(results)
        elif result_type == 'table':
            return self._deduplicate_table_results(results)
        elif result_type == 'web_text':
            return self._deduplicate_web_results(results)
        else:
            return results
    
    def _deduplicate_text_results(self, results: List[Dict]) -> List[Dict]:
        """文本结果去重：基于内容相似度和页码"""
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_pages = set()
        seen_content_hashes = set()
        
        # 按质量分数排序，优先保留高质量结果
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        for result in sorted_results:
            page_num = result.get('page_number', '')
            content = result.get('content', '')
            
            # 生成内容hash用于去重
            content_hash = hash(content[:200])  # 使用前200字符生成hash
            
            # 去重逻辑：
            # 1. 相同页码的内容只保留一个（质量最高的）
            # 2. 内容高度相似的只保留一个
            if page_num not in seen_pages and content_hash not in seen_content_hashes:
                deduplicated.append(result)
                if page_num:
                    seen_pages.add(page_num)
                seen_content_hashes.add(content_hash)
                
                # 限制每种类型的最大结果数
                if len(deduplicated) >= 8:  # 文本结果最多保留8条
                    break
        
        self.colored_logger.debug(f"📝 文本去重: {len(results)} -> {len(deduplicated)}")
        return deduplicated
    
    def _deduplicate_image_results(self, results: List[Dict]) -> List[Dict]:
        """图片结果去重：基于路径和页码"""
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_paths = set()
        seen_pages = set()
        
        # 按质量分数排序
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        for result in sorted_results:
            path = result.get('path', '')
            page_num = result.get('page_number', '')
            
            # 图片去重：相同路径或相同页码的图片只保留一个
            path_key = path.strip() if path else f"page_{page_num}"
            
            if path_key not in seen_paths:
                deduplicated.append(result)
                seen_paths.add(path_key)
                
                # 限制图片结果数量
                if len(deduplicated) >= 6:  # 图片结果最多保留6条
                    break
        
        self.colored_logger.debug(f"🖼️ 图片去重: {len(results)} -> {len(deduplicated)}")
        return deduplicated
    
    def _deduplicate_table_results(self, results: List[Dict]) -> List[Dict]:
        """表格结果去重：基于页码和内容"""
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_pages = set()
        
        # 按质量分数排序
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        for result in sorted_results:
            page_num = result.get('page_number', '')
            
            # 表格去重：相同页码的表格只保留一个
            if page_num not in seen_pages:
                deduplicated.append(result)
                if page_num:
                    seen_pages.add(page_num)
                
                # 限制表格结果数量
                if len(deduplicated) >= 4:  # 表格结果最多保留4条
                    break
        
        self.colored_logger.debug(f"📋 表格去重: {len(results)} -> {len(deduplicated)}")
        return deduplicated
    
    def _deduplicate_web_results(self, results: List[Dict]) -> List[Dict]:
        """Web搜索结果去重：基于URL和内容相似度"""
        if len(results) <= 1:
            return results
        
        deduplicated = []
        seen_urls = set()
        seen_content_hashes = set()
        
        # 按质量分数排序
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        for result in sorted_results:
            url = result.get('url', '')
            content = result.get('content', '')
            
            # 生成内容hash用于去重
            content_hash = hash(content[:300])  # 使用前300字符生成hash
            
            # Web结果去重：相同URL或相似内容只保留一个
            url_key = url.strip() if url else f"content_{content_hash}"
            
            if url_key not in seen_urls and content_hash not in seen_content_hashes:
                deduplicated.append(result)
                if url:
                    seen_urls.add(url_key)
                seen_content_hashes.add(content_hash)
                
                # 限制Web搜索结果数量
                if len(deduplicated) >= 3:  # Web搜索结果最多保留3条
                    break
        
        self.colored_logger.debug(f"🌐 Web结果去重: {len(results)} -> {len(deduplicated)}")
        return deduplicated

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

    def _observe_section_results(self, query: str, section_context: Dict[str, str], state: ReActState = None) -> List[Dict]:
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
            
            # 多维度查询模式：直接使用传入的精准查询词组
            combined_query = query.strip()
            
            # 记录查询信息
            self.colored_logger.debug(f"🔍 执行查询: '{combined_query}'")
            
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
            
            # 记录成功的查询
            if self.has_smart_control:
                self.concurrency_manager.record_api_request(
                    agent_name='react_agent',
                    success=True,
                    response_time=api_response_time
                )
            self.react_stats['successful_queries'] += 1
            
            return all_results
            
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
            return []
    


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

    def _evaluate_overall_rag_quality(self, all_results: List[Dict], section_context: Dict[str, str]) -> float:
        """对所有RAG结果进行整体质量评估"""
        if not all_results: 
            return 0.0
        
        # 安全地处理内容，确保转换为字符串
        def safe_content_str(result):
            content = result.get('content', result)
            if isinstance(content, (list, dict)):
                return str(content)[:150]
            return str(content)[:150]
        
        # 统计不同类型的结果
        text_count = len([r for r in all_results if r.get('type') == 'text'])
        image_count = len([r for r in all_results if r.get('type') == 'image'])
        table_count = len([r for r in all_results if r.get('type') == 'table'])
        
        evaluation_prompt = f"""
评估以下RAG检索结果对章节写作的整体适用性：

【目标章节】: {section_context['subtitle']}
【写作指导】: {section_context['how_to_write']}
【检索结果统计】: 文本{text_count}条, 图片{image_count}条, 表格{table_count}条, 总计{len(all_results)}条
【结果样本】: {chr(10).join(f"- {safe_content_str(r)}..." for r in all_results[:5])}

【评估要求】: 
1. 综合考虑结果的数量、质量、相关性和完整性
2. 评估是否能支撑该章节的写作需求
3. 只返回一个0.0到1.0的小数评分，不要其他内容

评分标准：
- 0.8-1.0: 结果丰富且高度相关，完全支撑写作
- 0.6-0.8: 结果较好，基本支撑写作需求
- 0.4-0.6: 结果一般，部分支撑写作
- 0.0-0.4: 结果不足或相关性差
"""
        try:
            response = self.client.generate(evaluation_prompt)
            score_match = re.search(r'0?\.\d+|[01]', response)
            quality_score = max(0.0, min(1.0, float(score_match.group()))) if score_match else 0.2
            self.colored_logger.debug(f"📊 整体RAG质量评估: {quality_score:.3f}")
            return quality_score
        except Exception as e:
            self.colored_logger.error(f"整体质量评估失败: {e}")
            return 0.1

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
        retrieved_web = []  # 新增Web搜索结果分组
        
        for result in state.retrieved_results:
            result_type = result.get('type', 'text')
            if result_type == 'text':
                retrieved_text.append(result)
            elif result_type == 'image':
                retrieved_image.append(result)
            elif result_type == 'table':
                retrieved_table.append(result)
            elif result_type == 'web_text':
                retrieved_web.append(result)
            else:
                # 默认归类为文本
                retrieved_text.append(result)
        
        # 添加调试日志，显示分组结果
        self.colored_logger.debug(f"📊 分组结果: 文本{len(retrieved_text)}条, 图片{len(retrieved_image)}条, 表格{len(retrieved_table)}条, Web{len(retrieved_web)}条")
        
        # 显示图片结果的详细信息
        for i, img in enumerate(retrieved_image):
            self.colored_logger.debug(f"📸 图片{i+1}: 路径={img.get('path', 'N/A')}, 页数={img.get('page_number', 'N/A')}, 描述={img.get('description', 'N/A')[:50]}...")
        
        # 多维度查询模式：进行智能去重处理
        retrieved_text = self._deduplicate_results(retrieved_text, 'text')
        retrieved_image = self._deduplicate_results(retrieved_image, 'image') 
        retrieved_table = self._deduplicate_results(retrieved_table, 'table')
        retrieved_web = self._deduplicate_results(retrieved_web, 'web_text')
        
        self.colored_logger.debug(f"📊 去重后结果: 文本{len(retrieved_text)}条, 图片{len(retrieved_image)}条, 表格{len(retrieved_table)}条, Web{len(retrieved_web)}条")
        
        # 分段搜索结果统计
        self.colored_logger.observation(f"📊 最终结果统计: 文本{len(retrieved_text)}条, "
                                      f"图片{len(retrieved_image)}条, "
                                      f"表格{len(retrieved_table)}条, "
                                      f"Web{len(retrieved_web)}条")

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

        # 处理Web搜索结果
        final_web_results = []
        for web_result in retrieved_web:
            final_web_results.append({
                'content': web_result.get('content', ''),
                'source': web_result.get('source', 'Web搜索'),
                'type': 'web_text',
                'url': web_result.get('url', ''),
                'title': web_result.get('title', ''),
                'score': web_result.get('score', 1.0)
            })

        return {
            'retrieved_text': final_text_results,
            'retrieved_image': final_image_results,
            'retrieved_table': final_table_results,
            'retrieved_web': final_web_results
        }
