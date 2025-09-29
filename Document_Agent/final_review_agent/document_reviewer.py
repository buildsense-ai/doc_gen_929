"""
文档质量评估器 - 使用OpenRouter API进行冗余度分析

负责对生成的文档进行深度质量评估，识别不必要的冗余内容，
并提供优化建议。
"""

import json
import logging
import re
import time
from typing import Dict, Any, List, Optional
from openai import OpenAI
from dataclasses import dataclass, field
import os


@dataclass
class RedundancyAnalysis:
    """冗余分析结果数据结构"""
    total_unnecessary_redundancy_types: int = 0
    unnecessary_redundancies_analysis: List[Dict[str, Any]] = field(default_factory=list)
    overall_quality_score: float = 0.0
    improvement_suggestions: List[str] = field(default_factory=list)


class ColoredLogger:
    """彩色日志记录器"""
    COLORS = {
        'RESET': '\033[0m', 'BLUE': '\033[94m', 'GREEN': '\033[92m', 
        'YELLOW': '\033[93m', 'RED': '\033[91m', 'PURPLE': '\033[95m', 
        'CYAN': '\033[96m', 'WHITE': '\033[97m',
    }
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _colorize(self, text: str, color: str) -> str:
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['RESET']}"
    
    def info(self, message: str): 
        self.logger.info(message)
    
    def error(self, message: str): 
        self.logger.error(message)
    
    def warning(self, message: str): 
        self.logger.warning(message)
    
    def debug(self, message: str): 
        self.logger.debug(message)
    
    def analysis_start(self, title: str): 
        self.logger.info(self._colorize(f"\n🔍 开始文档质量分析: {title}", 'PURPLE'))
    
    def analysis_complete(self, title: str, score: float): 
        self.logger.info(self._colorize(f"✅ 文档'{title}'质量分析完成 | 质量评分: {score:.2f}", 'WHITE'))
    
    def redundancy_found(self, count: int): 
        self.logger.info(self._colorize(f"⚠️ 发现 {count} 类不必要的冗余内容", 'YELLOW'))
    
    def api_call(self, content: str): 
        self.logger.info(self._colorize(f"🤖 API调用: {content}", 'GREEN'))
    
    def api_response(self, content: str): 
        self.logger.info(self._colorize(f"📡 API响应: {content}", 'CYAN'))


class DocumentReviewer:
    """文档质量评估器"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化文档评估器
        
        Args:
            api_key: OpenRouter API密钥
        """
        # 优先使用显式传入，其次读取环境变量，避免硬编码泄露
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError("缺少 OPENROUTER_API_KEY，请在环境变量中配置或传入 api_key")
        self.colored_logger = ColoredLogger(__name__)
        
        # 初始化OpenAI客户端
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
        )
        
        # 冗余分析提示词模板
        self.redundancy_analysis_prompt = """
# 角色
你是一名专业的文档分析师和高级编辑，擅长识别文本中的逻辑结构、信息层级和冗余内容。

# 任务
你的核心任务是深度分析我提供的文档正文，严格按照以下标准，识别所有不必要的冗余表达，并针对每一个问题点所在的章节标题 (subtitle)，提出具体的修改建议。

# 评估范围限制（重要）
只评估“正文”段落，严格忽略以下所有非正文内容：
1) 任何“### 相关图片资料”标题及其后的图片描述/图片来源/图片Markdown（直到下一个二级标题`## `或文末）。
2) 任意 Markdown 图片语法行：包含 `![` 或 `](http` 的行。
3) 含有“图片描述:”或“图片来源:”开头的行。
4) 任何“### 相关表格资料”标题及其后的表格内容，或任意以 `|` 开头的 Markdown 表格行。
5) 代码块、引用块、脚注等非正文元素。

务必不要基于上述内容做出判断、引用或提出修改建议。你的关注点仅限各小节的正文叙述性文本（即二级标题`## {subtitle}`下的段落文字）。

# 核心标准与定义
在执行任务时，你必须严格区分"必要的重复"和"不必要的冗余"。

不必要的冗余（需要识别）：
定义：在不同章节中，对同一具体事实、细节或描述进行几乎一字不差或高度雷同的重复性陈述，且未增加新的信息、视角或论证。
特征：类似复制粘贴，导致冗长，降低精炼度与专业性。

必要的重复（需要忽略）：
定义：为强化核心论点、服务于不同章节的论证逻辑、或使关键数据支撑不同分析而进行的策略性重复。
特征：有助于构建逻辑闭环，保证章节独立性并强调关键信息。

# 输出要求（仅JSON）
你的最终输出必须是一个结构化的 JSON 数组。数组中的每一个对象都代表一条针对具体章节的修改指令，其结构如下：

[
  {
    "subtitle": "章节标题",
    "suggestion": "针对该章节正文内容的具体、可操作的修改建议。不得涉及图片/表格。"
  }
]

- subtitle: 必须精准引用文档中存在赘述或写作问题的章节完整标题（如："三、项目必要性分析"）。
- suggestion: 必须是可直接执行的正文修改建议；不得引用或建议改动任何图片/表格/媒体相关内容。

# 工作流程
1) 先从原文中“逻辑上忽略”所有被【评估范围限制】列出的内容，仅保留正文段落用于分析。
2) 以章节（subtitle）为单位，查找正文中的重复信息点或写作不佳之处。
3) 依据【核心标准与定义】判断是否为不必要的冗余。
4) 对每个问题章节，给出针对正文的具体修改建议。
5) 严格按照【输出要求】的JSON数组格式返回，仅返回JSON，不要包含任何其他文字说明。


待分析文档（完整原文，评估时请按上述范围只取正文）：
$document_content

请严格遵循以上要求，只返回JSON格式结果。禁止输出与图片/表格/媒体相关的建议或内容。"""

        self.colored_logger.info("✅ DocumentReviewer 初始化完成")
    
    def analyze_document_simple(self, document_content: str, document_path: str, document_title: str = "未命名文档") -> List[Dict[str, str]]:
        """
        简化的文档质量分析，返回用户期望的格式
        
        Args:
            document_content: 待分析的文档内容
            document_path: 文档文件路径
            document_title: 文档标题
            
        Returns:
            List[Dict[str, str]]: 包含subtitle和suggestion的简单格式
        """
        self.colored_logger.analysis_start(document_title)
        
        try:
            # 检查文档内容长度
            if len(document_content.strip()) < 100:
                self.colored_logger.warning("⚠️ 文档内容过短，可能无法进行有效分析")
                return []
            
            # 调用OpenRouter API进行冗余分析
            analysis_result = self._call_openrouter_api(document_content)
            
            # 解析API响应为简单格式
            simple_result = self._parse_api_response_simple(analysis_result, document_path, document_content)
            
            self.colored_logger.info(f"✅ 简化分析完成，发现 {len(simple_result)} 个需要修改的地方")
            
            return simple_result
            
        except Exception as e:
            self.colored_logger.error(f"❌ 文档质量分析失败: {e}")
            return []
    
    def _parse_api_response_simple(self, api_response: str, document_path: str, document_content: str) -> List[Dict[str, str]]:
        """
        解析API响应为用户期望的简单格式
        
        Args:
            api_response: API响应内容
            document_path: 文档文件路径
            document_content: 文档内容（用于查找行号）
            
        Returns:
            List[Dict[str, str]]: 简单格式的结果
        """
        try:
            # 清理响应内容，移除可能的markdown代码块标记
            cleaned_response = api_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            cleaned_response = cleaned_response.strip()
            
            # 尝试提取JSON内容
            json_match = re.search(r'[\[\{].*[\]\}]', cleaned_response, re.DOTALL)
            if not json_match:
                self.colored_logger.error(f"❌ API响应中未找到有效的JSON内容")
                return []
            
            json_str = json_match.group(0)
            
            # 尝试解析JSON
            try:
                parsed_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.colored_logger.error(f"❌ JSON解析失败: {e}")
                return []
            
            # 处理API返回的数组格式
            simple_results = []
            
            if isinstance(parsed_data, list):
                for item in parsed_data:
                    subtitle = item.get('subtitle', item.get('subtitle', ''))
                    suggestion = item.get('suggestion', '')
                    
                    # 直接使用二级标题作为subtitle
                    simple_results.append({
                        "subtitle": subtitle,
                        "suggestion": suggestion
                    })
            
            return simple_results
            
        except Exception as e:
            self.colored_logger.error(f"❌ 简化响应解析失败: {e}")
            return []
    
    def analyze_document_quality(self, document_content: str, document_title: str = "未命名文档") -> RedundancyAnalysis:
        """
        分析文档质量，识别冗余内容
        
        Args:
            document_content: 待分析的文档内容
            document_title: 文档标题
            
        Returns:
            RedundancyAnalysis: 冗余分析结果
        """
        self.colored_logger.analysis_start(document_title)
        
        try:
            # 检查文档内容长度
            if len(document_content.strip()) < 100:
                self.colored_logger.warning("⚠️ 文档内容过短，可能无法进行有效分析")
                return RedundancyAnalysis(
                    total_unnecessary_redundancy_types=0,
                    unnecessary_redundancies_analysis=[],
                    overall_quality_score=1.0,
                    improvement_suggestions=["文档内容过短，建议增加更多详细信息"]
                )
            
            # 调用OpenRouter API进行冗余分析
            analysis_result = self._call_openrouter_api(document_content)
            
            # 解析API响应
            redundancy_analysis = self._parse_api_response(analysis_result)
            
            # 计算整体质量评分
            quality_score = self._calculate_quality_score(redundancy_analysis)
            redundancy_analysis.overall_quality_score = quality_score
            
            # 生成改进建议
            improvement_suggestions = self._generate_improvement_suggestions(redundancy_analysis)
            redundancy_analysis.improvement_suggestions = improvement_suggestions
            
            # 记录分析结果
            self.colored_logger.redundancy_found(redundancy_analysis.total_unnecessary_redundancy_types)
            self.colored_logger.analysis_complete(document_title, quality_score)
            
            return redundancy_analysis
            
        except Exception as e:
            self.colored_logger.error(f"❌ 文档质量分析失败: {e}")
            return RedundancyAnalysis(
                total_unnecessary_redundancy_types=0,
                unnecessary_redundancies_analysis=[],
                overall_quality_score=0.0,
                improvement_suggestions=[f"分析过程中发生错误: {str(e)}"]
            )
    
    def _call_openrouter_api(self, document_content: str) -> str:
        """
        调用OpenRouter API进行冗余分析
        
        Args:
            document_content: 文档内容
            
        Returns:
            str: API响应内容
        """
        try:
            # 记录文档内容长度
            self.colored_logger.info(f"📄 文档内容长度: {len(document_content)}字符")
            
            # 构建提示词 - 使用字符串模板避免格式化问题
            prompt = self.redundancy_analysis_prompt.replace('$document_content', document_content)
            
            self.colored_logger.api_call(f"发送冗余分析请求到OpenRouter API，内容长度: {len(prompt)}字符")
            
            # 调用API
            completion = self.client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "https://gauz-document-agent.com",
                    "X-Title": "GauzDocumentAgent",
                },
                extra_body={},
                model="deepseek/deepseek-chat-v3-0324",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # 低温度确保输出一致性
                max_tokens=4000   # 足够长的输出
            )
            
            # 调试：打印响应对象信息
            self.colored_logger.debug(f"📊 API响应对象类型: {type(completion)}")
            self.colored_logger.debug(f"📊 API响应对象属性: {hasattr(completion, 'choices')}")
            
            # 详细检查响应结构
            if not hasattr(completion, 'choices'):
                self.colored_logger.error(f"❌ API响应对象没有choices属性")
                self.colored_logger.error(f"❌ 响应对象: {completion}")
                raise ValueError("API响应对象没有choices属性")
                
            if not completion.choices:
                self.colored_logger.error(f"❌ API响应中choices为空")
                self.colored_logger.error(f"❌ 完整响应: {completion}")
                raise ValueError("API响应中choices为空")
            
            if not completion.choices[0].message:
                self.colored_logger.error(f"❌ API响应中没有message")
                raise ValueError("API响应中没有message")
            
            response_content = completion.choices[0].message.content
            if response_content is None:
                self.colored_logger.error(f"❌ API响应中message.content为空")
                raise ValueError("API响应中message.content为空")
            
            self.colored_logger.api_response(f"API调用成功，响应长度: {len(response_content)} 字符")
            
            # 调试：显示响应的前500个字符
            self.colored_logger.debug(f"API响应预览: {response_content[:500]}...")
            
            # 检查响应是否为空
            if not response_content or response_content.strip() == "":
                raise ValueError("API返回了空响应")
            
            return response_content
            
        except Exception as e:
            self.colored_logger.error(f"❌ OpenRouter API调用失败: {e}")
            # 添加更详细的错误信息
            if "rate limit" in str(e).lower():
                self.colored_logger.error("可能是API速率限制，请稍后重试")
            elif "timeout" in str(e).lower():
                self.colored_logger.error("API调用超时，请检查网络连接")
            elif "authentication" in str(e).lower():
                self.colored_logger.error("API密钥认证失败，请检查密钥配置")
            else:
                self.colored_logger.error(f"未知错误类型: {type(e).__name__}")
            raise
    
    def _parse_api_response(self, api_response: str) -> RedundancyAnalysis:
        """
        解析API响应，提取冗余分析结果
        
        Args:
            api_response: API响应内容
            
        Returns:
            RedundancyAnalysis: 解析后的分析结果
        """
        try:
            # 清理响应内容，移除可能的markdown代码块标记
            cleaned_response = api_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            cleaned_response = cleaned_response.strip()
            
            # 尝试提取JSON内容 - 支持数组和对象格式
            json_match = re.search(r'[\[\{].*[\]\}]', cleaned_response, re.DOTALL)
            if not json_match:
                self.colored_logger.error(f"❌ API响应中未找到有效的JSON内容，响应内容: {cleaned_response[:200]}...")
                return RedundancyAnalysis()
            
            json_str = json_match.group(0)
            
            # 尝试解析JSON
            try:
                parsed_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.colored_logger.error(f"❌ JSON解析失败: {e}")
                self.colored_logger.error(f"❌ 问题JSON内容: {json_str[:200]}...")
                return RedundancyAnalysis()
            
            # 构建RedundancyAnalysis对象
            # 处理API返回的数组格式（按照prompt要求）
            processed_analysis = []
            
            if isinstance(parsed_data, list):
                # API返回的是数组格式，每个元素包含subtitle和suggestion
                for item in parsed_data:
                    subtitle = item.get('subtitle', item.get('subtitle', '未知位置'))
                    suggestion = item.get('suggestion', '建议优化')
                    
                    # 从subtitle中提取章节主题
                    theme = subtitle
                    if subtitle.startswith('## '):
                        theme = subtitle[3:]  # 去掉"## "前缀
                    
                    processed_item = {
                        "redundant_theme": theme,
                        "count": 1,  # 每个章节算作一个冗余点
                        "subtitles": [subtitle],
                        "evidence": [suggestion],
                        "suggestion": suggestion
                    }
                    processed_analysis.append(processed_item)
                
                analysis = RedundancyAnalysis(
                    total_unnecessary_redundancy_types=len(parsed_data),
                    unnecessary_redundancies_analysis=processed_analysis
                )
            else:
                # 兼容旧的对象格式
                raw_analysis = parsed_data.get('unnecessary_redundancies_analysis', [])
                
                for item in raw_analysis:
                    processed_item = {
                        "redundant_theme": item.get('redundant_theme', item.get('redundant_text', '未知主题')),
                        "count": item.get('count', 0),
                        "subtitles": item.get('subtitles', [f"位置{i+1}" for i in range(item.get('count', 0))]),
                        "evidence": item.get('evidence', [item.get('redundant_text', '')] * item.get('count', 0)),
                        "suggestion": item.get('suggestion', f"建议删除重复的'{item.get('redundant_text', '')}'内容")
                    }
                    processed_analysis.append(processed_item)
                
                analysis = RedundancyAnalysis(
                    total_unnecessary_redundancy_types=parsed_data.get('total_unnecessary_redundancy_types', 0),
                    unnecessary_redundancies_analysis=processed_analysis
                )
            
            self.colored_logger.debug(f"✅ 成功解析API响应，发现 {analysis.total_unnecessary_redundancy_types} 类冗余")
            
            return analysis
            
        except Exception as e:
            self.colored_logger.error(f"❌ 响应解析失败: {e}")
            self.colored_logger.error(f"❌ 原始响应内容: {api_response[:300]}...")
            return RedundancyAnalysis()
    
    def _calculate_quality_score(self, analysis: RedundancyAnalysis) -> float:
        """
        基于冗余分析结果计算整体质量评分
        
        Args:
            analysis: 冗余分析结果
            
        Returns:
            float: 质量评分 (0.0-1.0)
        """
        if analysis.total_unnecessary_redundancy_types == 0:
            return 1.0  # 无冗余，满分
        
        # 基于冗余类型数量和严重程度计算评分
        base_score = 1.0
        penalty_per_type = 0.15  # 每类冗余扣0.15分
        
        # 计算冗余严重程度
        total_redundant_instances = sum(
            item.get('count', 0) for item in analysis.unnecessary_redundancies_analysis
        )
        
        # 应用惩罚
        type_penalty = analysis.total_unnecessary_redundancy_types * penalty_per_type
        instance_penalty = min(0.3, total_redundant_instances * 0.05)  # 实例惩罚上限0.3
        
        final_score = max(0.0, base_score - type_penalty - instance_penalty)
        
        self.colored_logger.debug(f"📊 质量评分计算: 基础分1.0 - 类型惩罚{type_penalty:.2f} - 实例惩罚{instance_penalty:.2f} = {final_score:.2f}")
        
        return final_score
    
    def _generate_improvement_suggestions(self, analysis: RedundancyAnalysis) -> List[str]:
        """
        基于冗余分析结果生成改进建议
        
        Args:
            analysis: 冗余分析结果
            
        Returns:
            List[str]: 改进建议列表
        """
        suggestions = []
        
        if analysis.total_unnecessary_redundancy_types == 0:
            suggestions.append("✅ 文档质量优秀，未发现不必要的冗余内容")
            return suggestions
        
        # 添加总体建议
        suggestions.append(f"📝 发现 {analysis.total_unnecessary_redundancy_types} 类不必要的冗余内容，建议进行优化")
        
        # 添加具体建议
        for redundancy in analysis.unnecessary_redundancies_analysis:
            theme = redundancy.get('redundant_theme', '未知主题')
            count = redundancy.get('count', 0)
            suggestion = redundancy.get('suggestion', '建议删除重复内容')
            
            suggestions.append(f"🔍 {theme}: 出现{count}次 - {suggestion}")
        
        # 添加通用建议
        suggestions.extend([
            "💡 建议使用概括性语言替代重复的具体描述",
            "💡 考虑将重复信息整合到专门的章节中",
            "💡 使用引用和交叉引用来避免重复"
        ])
        
        return suggestions
    
    def generate_quality_report(self, analysis: RedundancyAnalysis, document_title: str = "未命名文档") -> str:
        """
        生成质量评估报告
        
        Args:
            analysis: 冗余分析结果
            document_title: 文档标题
            
        Returns:
            str: 格式化的质量报告
        """
        report_lines = [
            f"# 文档质量评估报告",
            f"**文档标题**: {document_title}",
            f"**评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## 📊 整体质量评分",
            f"**质量评分**: {analysis.overall_quality_score:.2f}/1.00",
            f"",
            f"## 🔍 冗余分析结果",
            f"**冗余类型总数**: {analysis.total_unnecessary_redundancy_types}",
            f""
        ]
        
        if analysis.total_unnecessary_redundancy_types == 0:
            report_lines.extend([
                f"✅ **优秀**: 未发现不必要的冗余内容",
                f""
            ])
        else:
            report_lines.extend([
                f"⚠️ **发现冗余**: 共 {analysis.total_unnecessary_redundancy_types} 类不必要的冗余内容",
                f""
            ])
            
            for i, redundancy in enumerate(analysis.unnecessary_redundancies_analysis, 1):
                theme = redundancy.get('redundant_theme', '未知主题')
                count = redundancy.get('count', 0)
                subtitles = redundancy.get('subtitles', [])
                evidence = redundancy.get('evidence', [])
                suggestion = redundancy.get('suggestion', '建议优化')
                
                report_lines.extend([
                    f"### {i}. {theme}",
                    f"**出现次数**: {count}",
                    f"**出现位置**:",
                ])
                
                for subtitle in subtitles:
                    report_lines.append(f"- {subtitle}")
                
                report_lines.extend([
                    f"**冗余证据**:",
                ])
                
                for j, evidence_text in enumerate(evidence, 1):
                    # 截断过长的证据文本
                    truncated_evidence = evidence_text[:200] + "..." if len(evidence_text) > 200 else evidence_text
                    report_lines.append(f"{j}. {truncated_evidence}")
                
                report_lines.extend([
                    f"**优化建议**: {suggestion}",
                    f""
                ])
        
        # 添加改进建议
        report_lines.extend([
            f"## 💡 改进建议",
        ])
        
        for suggestion in analysis.improvement_suggestions:
            report_lines.append(f"- {suggestion}")
        
        report_lines.extend([
            f"",
            f"---",
            f"*本报告由Gauz文档Agent自动生成*"
        ])
        
        return "\n".join(report_lines)
    
    def save_analysis_result(self, analysis: RedundancyAnalysis, document_title: str, output_path: str = None) -> str:
        """
        保存分析结果到文件
        
        Args:
            analysis: 冗余分析结果
            document_title: 文档标题
            output_path: 输出路径（可选）
            
        Returns:
            str: 保存的文件路径
        """
        import os
        from datetime import datetime
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r'[^\w\s-]', '', document_title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        
        if output_path is None:
            output_path = f"quality_analysis_{safe_title}_{timestamp}.json"
        
        # 准备保存的数据
        save_data = {
            "document_title": document_title,
            "analysis_timestamp": timestamp,
            "overall_quality_score": analysis.overall_quality_score,
            "total_unnecessary_redundancy_types": analysis.total_unnecessary_redundancy_types,
            "unnecessary_redundancies_analysis": analysis.unnecessary_redundancies_analysis,
            "improvement_suggestions": analysis.improvement_suggestions
        }
        
        # 保存JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        self.colored_logger.info(f"💾 分析结果已保存到: {output_path}")
        
        return output_path
    
    def save_simple_analysis_result(self, quality_issues: List[Dict[str, str]], document_title: str, output_dir: str = ".") -> str:
        """
        保存简化分析结果到文件
        
        Args:
            quality_issues: 简化分析结果列表
            document_title: 文档标题
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件路径
        """
        import os
        from datetime import datetime
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r'[^\w\s-]', '', document_title).strip()
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        
        output_path = os.path.join(output_dir, f"quality_analysis_{safe_title}_{timestamp}.json")
        
        # 准备保存的数据
        save_data = {
            "document_title": document_title,
            "analysis_timestamp": timestamp,
            "issues_found": len(quality_issues),
            "quality_issues": quality_issues,
            "analysis_type": "simple_format"
        }
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        self.colored_logger.info(f"💾 简化分析结果已保存到: {output_path}")
        
        return output_path