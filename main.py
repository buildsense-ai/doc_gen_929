#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gauz文档Agent - 智能长文档生成系统
主程序入口

基于多Agent架构的智能文档生成系统，支持从用户查询到完整文档的全流程自动化生成。

系统架构：
1. OrchestratorAgent - 编排代理：分析需求，生成文档结构和写作指导
2. SectionWriterAgent - 章节写作代理：使用ReAct框架智能检索相关资料
3. ContentGeneratorAgent - 内容生成代理：基于结构和资料生成最终文档

使用方法：
    python main.py [选项]
    
选项：
    --query "查询内容"    直接指定文档需求
    --interactive       进入交互模式
    --help             显示帮助信息
"""

import sys
import os

# ===== 必须在所有其他导入之前禁用ChromaDB telemetry =====
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_DISABLED'] = 'True'

import json
import argparse
import time
from datetime import datetime
from typing import Dict, Any, Optional

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from clients.openrouter_client import OpenRouterClient
    # 移除SimpleRAGClient导入
    from Document_Agent.orchestrator_agent import OrchestratorAgent
    from Document_Agent.section_writer_agent import ReactAgent
    from Document_Agent.content_generator_agent import MainDocumentGenerator
    from Document_Agent.final_review_agent import DocumentReviewer
    from Document_Agent.final_review_agent.json_merger import JSONDocumentMerger
    from Document_Agent.final_review_agent.regenerate_sections import DocumentRegenerator
    from config.settings import setup_logging, get_config, get_concurrency_manager
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保您在项目根目录下运行此程序，并安装了所有依赖。")
    sys.exit(1)


class DocumentGenerationPipeline:
    """文档生成流水线 - 整合三个Agent的完整工作流，支持统一并发管理"""
    
    def __init__(self):
        """初始化流水线"""
        print("🔧 正在初始化文档生成系统...")
        
        # 设置日志
        setup_logging()
        
        # 初始化并发管理器
        self.concurrency_manager = get_concurrency_manager()
        
        # 初始化客户端
        try:
            self.llm_client = OpenRouterClient()
            # 移除rag_client，OrchestratorAgent已经集成外部API
            
            # 初始化五个Agent，传入统一的并发管理器
            # OrchestratorAgent不再需要rag_client参数
            self.orchestrator = OrchestratorAgent(self.llm_client, self.concurrency_manager)
            self.section_writer = ReactAgent(self.llm_client, self.concurrency_manager)
            self.content_generator = MainDocumentGenerator(self.concurrency_manager)
            self.document_reviewer = DocumentReviewer()
            self.document_regenerator = DocumentRegenerator()
            
            print("✅ 系统初始化成功！（使用外部API服务）")
            self._print_concurrency_settings()
            
        except Exception as e:
            print(f"❌ 系统初始化失败: {e}")
            raise
    
    def _print_concurrency_settings(self):
        """打印当前并发设置"""
        print("\n" + "="*60)
        self.concurrency_manager.print_settings()
        print("="*60 + "\n")
    
    def set_concurrency(self, orchestrator_workers: int = None, react_workers: int = None, 
                       content_workers: int = None, rate_delay: float = None):
        """
        统一设置并发参数
        
        Args:
            orchestrator_workers: 编排代理线程数
            react_workers: 检索代理线程数
            content_workers: 内容生成代理线程数
            rate_delay: 请求间隔时间(秒)
        """
        print("🔧 更新并发设置...")
        
        if orchestrator_workers is not None:
            self.orchestrator.set_max_workers(orchestrator_workers)
            
        if react_workers is not None:
            self.section_writer.set_max_workers(react_workers)
            
        if content_workers is not None:
            self.content_generator.set_max_workers(content_workers)
            
        if rate_delay is not None:
            self.content_generator.set_rate_limit_delay(rate_delay)
            
        print("✅ 并发设置更新完成！")
        self._print_concurrency_settings()
    
    def get_concurrency_settings(self) -> dict:
        """获取当前并发设置"""
        return {
            'orchestrator_workers': self.orchestrator.get_max_workers(),
            'react_workers': self.section_writer.get_max_workers(),
            'content_workers': self.content_generator.get_max_workers(),
            'rate_delay': self.content_generator.get_rate_limit_delay()
        }
    
    def generate_document(self, user_query: str, project_name: str, output_dir: str = "医灵古庙") -> Dict[str, str]:
        """
        完整文档生成流程
        
        Args:
            user_query: 用户需求描述
            project_name: 项目名称，用于RAG检索
            output_dir: 输出目录
            
        Returns:
            Dict: 包含生成文件路径的字典
        """
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("🚀 开始文档生成流程...")
        print("=" * 80)
        print(f"📝 用户需求：{user_query}")
        print(f"🏷️ 项目名称：{project_name}")
        print("=" * 80)
        
        try:
            # 阶段1：生成文档结构（OrchestratorAgent）
            print("\n🏗️  阶段1：生成文档结构和写作指导...")
            step1_start = time.time()
            
            document_guide = self.orchestrator.generate_complete_guide(user_query)
            
            step1_time = time.time() - step1_start
            sections_count = sum(len(part.get('sections', [])) for part in document_guide.get('report_guide', []))
            
            print(f"✅ 文档结构生成完成！")
            print(f"   📊 生成了 {len(document_guide.get('report_guide', []))} 个主要部分，{sections_count} 个子章节")
            print(f"   ⏱️  耗时：{step1_time:.1f}秒")
            
            # 保存阶段1结果
            step1_file = os.path.join(output_dir, f"step1_document_guide_{timestamp}.json")
            with open(step1_file, 'w', encoding='utf-8') as f:
                json.dump(document_guide, f, ensure_ascii=False, indent=2)
            
            # 阶段2：智能检索相关资料（SectionWriterAgent）
            print("\n🔍 阶段2：为各章节智能检索相关资料...")
            step2_start = time.time()
            
            enriched_guide = self.section_writer.process_report_guide(document_guide, project_name)
            
            step2_time = time.time() - step2_start
            print(f"✅ 资料检索完成！")
            print(f"   🔍 为 {sections_count} 个章节检索了相关资料")
            print(f"   ⏱️  耗时：{step2_time:.1f}秒")
            
            # 保存阶段2结果
            step2_file = os.path.join(output_dir, f"step2_enriched_guide_{timestamp}.json")
            with open(step2_file, 'w', encoding='utf-8') as f:
                json.dump(enriched_guide, f, ensure_ascii=False, indent=2)
            
            # 阶段3：生成最终文档（ContentGeneratorAgent）
            print("\n📝 阶段3：生成最终文档内容...")
            step3_start = time.time()
            
            # 保存为content_generator能识别的文件名
            generation_input = os.path.join(output_dir, f"生成文档的依据_{timestamp}.json")
            with open(generation_input, 'w', encoding='utf-8') as f:
                json.dump(enriched_guide, f, ensure_ascii=False, indent=2)
            
            # 生成最终文档
            final_doc_path = self.content_generator.generate_document(generation_input)
            
            step3_time = time.time() - step3_start
            print(f"✅ 最终文档生成完成！")
            print(f"   ⏱️  耗时：{step3_time:.1f}秒")
            
            # 阶段4：文档质量评估（DocumentReviewer）
            print("\n📊 阶段4：文档质量评估...")
            step4_start = time.time()
            
            # 读取生成的文档内容
            try:
                with open(final_doc_path, 'r', encoding='utf-8') as f:
                    document_content = f.read()
                
                # 进行质量评估
                document_title = os.path.basename(final_doc_path).replace('.md', '')
                quality_analysis = self.document_reviewer.analyze_document_quality(
                    document_content, document_title
                )
                
                # 生成质量报告
                quality_report = self.document_reviewer.generate_quality_report(
                    quality_analysis, document_title
                )
                
                # 保存质量分析结果
                quality_analysis_file = os.path.join(output_dir, f"quality_analysis_{timestamp}.json")
                self.document_reviewer.save_analysis_result(
                    quality_analysis, document_title, quality_analysis_file
                )
                
                # 保存质量报告
                quality_report_file = os.path.join(output_dir, f"quality_report_{timestamp}.md")
                with open(quality_report_file, 'w', encoding='utf-8') as f:
                    f.write(quality_report)
                
                step4_time = time.time() - step4_start
                print(f"✅ 文档质量评估完成！")
                print(f"   📊 质量评分：{quality_analysis.overall_quality_score:.2f}/1.00")
                print(f"   ⚠️  发现冗余：{quality_analysis.total_unnecessary_redundancy_types} 类")
                print(f"   ⏱️  耗时：{step4_time:.1f}秒")
                
            except Exception as e:
                print(f"⚠️  文档质量评估失败: {e}")
                step4_time = 0
                quality_analysis_file = None
                quality_report_file = None
            
            # 计算总耗时
            total_time = step1_time + step2_time + step3_time + step4_time
            print("\n" + "=" * 80)
            print("🎉 文档生成流程全部完成！")
            print(f"📊 总体统计：")
            print(f"   📑 主要部分：{len(document_guide.get('report_guide', []))} 个")
            print(f"   📄 子章节：{sections_count} 个")
            if step4_time > 0:
                print(f"   📊 质量评分：{quality_analysis.overall_quality_score:.2f}/1.00")
            print(f"   ⏱️  总耗时：{total_time:.1f}秒")
            print("=" * 80)
            
            # 返回生成的文件路径
            result = {
                'document_guide': step1_file,
                'enriched_guide': step2_file,
                'generation_input': generation_input,
                'final_document': final_doc_path,
                'output_directory': output_dir
            }
            
            # 添加质量评估文件（如果生成成功）
            if step4_time > 0:
                result['quality_analysis'] = quality_analysis_file
                result['quality_report'] = quality_report_file
            
            return result
            
        except Exception as e:
            print(f"❌ 文档生成过程中出现错误: {e}")
            raise
    
    def regenerate_and_merge_document(self, original_json_path: str, quality_analysis_path: str, 
                                    output_dir: str = None) -> Dict[str, str]:
        """
        基于质量评估结果重新生成并合并文档
        
        Args:
            original_json_path: 原始JSON文档路径
            quality_analysis_path: 质量评估结果路径
            output_dir: 输出目录
            
        Returns:
            Dict: 包含生成文件路径的字典
        """
        if output_dir is None:
            output_dir = os.path.dirname(original_json_path)
        
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("🔄 开始文档重新生成和合并流程...")
        print("=" * 80)
        print(f"📄 原始文档：{original_json_path}")
        print(f"📊 质量评估：{quality_analysis_path}")
        print("=" * 80)
        
        try:
            # 阶段1：重新生成需要修改的章节
            print("\n🔧 阶段1：重新生成需要修改的章节...")
            step1_start = time.time()
            
            regenerated_sections = self.document_regenerator.regenerate_document_sections(
                quality_analysis_path, original_json_path, output_dir
            )
            
            # regenerate_document_sections返回的是字典，需要保存为文件
            regenerated_sections_path = os.path.join(output_dir, f"regenerated_sections_{timestamp}.json")
            with open(regenerated_sections_path, 'w', encoding='utf-8') as f:
                json.dump(regenerated_sections, f, ensure_ascii=False, indent=2)
            
            step1_time = time.time() - step1_start
            print(f"✅ 章节重新生成完成！")
            print(f"   ⏱️  耗时：{step1_time:.1f}秒")
            
            # 阶段2：合并文档
            print("\n🔗 阶段2：合并重新生成的章节...")
            step2_start = time.time()
            
            merger = JSONDocumentMerger(original_json_path, regenerated_sections_path)
            merger.load_original_json()
            merger.load_regenerated_sections()
            
            # 合并JSON文档
            merged_data = merger.merge_json_documents()
            
            # 保存合并后的JSON
            merged_json_path = os.path.join(output_dir, f"merged_document_{timestamp}.json")
            merger.save_merged_json(merged_data, merged_json_path)
            
            # 转换为Markdown
            merged_md_path = os.path.join(output_dir, f"merged_document_{timestamp}.md")
            merger.convert_to_markdown(merged_data, merged_md_path)
            
            # 生成摘要报告
            merger.generate_summary_report(merged_json_path, merged_md_path)
            
            step2_time = time.time() - step2_start
            print(f"✅ 文档合并完成！")
            print(f"   ⏱️  耗时：{step2_time:.1f}秒")
            
            # 计算总耗时
            total_time = step1_time + step2_time
            print("\n" + "=" * 80)
            print("🎉 文档重新生成和合并流程完成！")
            print(f"📊 总体统计：")
            print(f"   ⏱️  总耗时：{total_time:.1f}秒")
            print("=" * 80)
            
            # 返回生成的文件路径
            result = {
                'regenerated_sections': regenerated_sections_path,
                'merged_json': merged_json_path,
                'merged_document': merged_md_path,
                'output_directory': output_dir
            }
            
            return result
            
        except Exception as e:
            print(f"❌ 文档重新生成和合并过程中出现错误: {e}")
            raise
    
    def final_review_workflow(self, markdown_file: str, json_file: str, document_title: str, 
                             output_dir: str = None) -> Dict[str, str]:
        """
        执行final_review_agent完整工作流程
        
        Args:
            markdown_file: 生成的markdown文档路径
            json_file: 原始JSON文档路径
            document_title: 文档标题
            output_dir: 输出目录
            
        Returns:
            Dict: 包含评审和重新生成结果的字典
        """
        if output_dir is None:
            output_dir = os.path.dirname(markdown_file)
        
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("🔍 开始final_review_agent工作流程...")
        print("=" * 80)
        print(f"📄 Markdown文档：{markdown_file}")
        print(f"📊 JSON文档：{json_file}")
        print(f"📝 文档标题：{document_title}")
        print("=" * 80)
        
        try:
            # 阶段1：文档质量评审
            print("\n📋 阶段1：执行文档质量评审...")
            step1_start = time.time()
            
            # 读取文档内容
            with open(markdown_file, 'r', encoding='utf-8') as f:
                document_content = f.read()
            
            # 执行简化分析
            analysis_result = self.document_reviewer.analyze_document_simple(document_content, markdown_file, document_title)
            
            if not analysis_result:
                print("❌ 文档质量评审失败")
                return {}
            
            step1_time = time.time() - step1_start
            print(f"✅ 文档质量评审完成！")
            print(f"   📊 发现问题：{len(analysis_result)} 个")
            print(f"   ⏱️  耗时：{step1_time:.1f}秒")
            
            # 保存评审结果
            analysis_file = os.path.join(output_dir, f"final_review_analysis_{timestamp}.json")
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, ensure_ascii=False, indent=2)
            
            # 阶段2：文档重新生成
            print("\n🔄 阶段2：执行文档重新生成...")
            step2_start = time.time()
            
            # 执行重新生成
            regeneration_result = self.document_regenerator.regenerate_document_sections(
                analysis_file,
                json_file,
                output_dir=output_dir
            )
            
            if not regeneration_result or regeneration_result.get('error'):
                error_msg = regeneration_result.get('error', '未知错误') if regeneration_result else '返回结果为空'
                print(f"❌ 文档重新生成失败: {error_msg}")
                return {'analysis_file': analysis_file}
            
            step2_time = time.time() - step2_start
            print(f"✅ 文档重新生成完成！")
            print(f"   📊 重新生成章节：{len(regeneration_result)} 个")
            print(f"   ⏱️  耗时：{step2_time:.1f}秒")
            
            # 计算统计信息
            total_words = sum(result.get('word_count', 0) for result in regeneration_result.values())
            avg_quality = sum(result.get('quality_score', 0) for result in regeneration_result.values()) / len(regeneration_result)
            
            # 阶段3：生成工作流程摘要
            print("\n📈 阶段3：生成工作流程摘要...")
            
            workflow_summary = {
                'timestamp': timestamp,
                'input_files': {
                    'markdown_file': markdown_file,
                    'json_file': json_file,
                    'document_title': document_title
                },
                'analysis_results': {
                    'total_issues': len(analysis_result),
                    'analysis_file': analysis_file
                },
                'regeneration_results': {
                    'total_sections': len(regeneration_result),
                    'total_words': total_words,
                    'average_quality': avg_quality,
                    'output_directory': output_dir
                },
                'status': 'success'
            }
            
            # 保存工作流程摘要
            summary_file = os.path.join(output_dir, f"final_review_summary_{timestamp}.json")
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(workflow_summary, f, ensure_ascii=False, indent=2)
            
            # 计算总耗时
            total_time = step1_time + step2_time
            print("\n" + "=" * 80)
            print("🎉 final_review_agent工作流程完成！")
            print(f"📊 总体统计：")
            print(f"   📋 发现问题：{len(analysis_result)} 个")
            print(f"   📝 重新生成章节：{len(regeneration_result)} 个")
            print(f"   📄 总字数：{total_words} 字")
            print(f"   📊 平均质量：{avg_quality:.2f}")
            print(f"   ⏱️  总耗时：{total_time:.1f}秒")
            print("=" * 80)
            
            # 返回结果
            result = {
                'analysis_file': analysis_file,
                'summary_file': summary_file,
                'output_directory': output_dir,
                'regeneration_sections': len(regeneration_result),
                'total_words': total_words,
                'average_quality': avg_quality
            }
            
            return result
            
        except Exception as e:
            print(f"❌ final_review_agent工作流程失败: {e}")
            raise
    
    def complete_workflow_with_regeneration(self, user_query: str, project_name: str = "默认项目", 
                                          output_dir: str = "outputs", auto_regenerate: bool = True) -> Dict[str, str]:
        """
        完整的文档生成工作流，包含质量评估和自动重新生成
        
        Args:
            user_query: 用户需求描述
            project_name: 项目名称，用于RAG检索
            output_dir: 输出目录
            auto_regenerate: 是否自动重新生成低质量章节
            
        Returns:
            Dict: 包含生成文件路径的字典
        """
        # 首先执行标准的文档生成流程
        initial_result = self.generate_document(user_query, project_name, output_dir)
        
        if not auto_regenerate:
            return initial_result
        
        # 检查是否有质量评估结果
        if 'quality_analysis' not in initial_result:
            print("⚠️  未找到质量评估结果，跳过自动重新生成")
            return initial_result
        
        # 检查是否有需要修改的章节
        try:
            with open(initial_result['quality_analysis'], 'r', encoding='utf-8') as f:
                quality_data = json.load(f)
            
            # 检查冗余分析结果
            redundancy_count = quality_data.get('total_unnecessary_redundancy_types', 0)
            redundancy_analysis = quality_data.get('unnecessary_redundancies_analysis', [])
            quality_score = quality_data.get('overall_quality_score', 1.0)
            
            # 设置重新生成的阈值：冗余类型超过3个或质量分数低于0.7
            should_regenerate = redundancy_count > 3 or quality_score < 0.7
            
            if not should_regenerate:
                print(f"✅ 文档质量良好（冗余类型: {redundancy_count}, 质量分: {quality_score:.2f}），无需重新生成")
                return initial_result
            
            print(f"⚠️  文档质量需要改进（冗余类型: {redundancy_count}, 质量分: {quality_score:.2f}），开始自动重新生成...")
            
            # 执行重新生成和合并
            regeneration_result = self.regenerate_and_merge_document(
                initial_result['final_document'],  # 传递最终生成的JSON文档
                initial_result['quality_analysis'],  # 传递质量分析文件
                output_dir
            )
            
            # 合并结果
            final_result = {**initial_result, **regeneration_result}
            final_result['final_document'] = regeneration_result['merged_document']
            
            return final_result
            
        except Exception as e:
            print(f"⚠️  自动重新生成失败: {e}")
            print("📄 返回初始生成结果")
            return initial_result
    
    def generate_document_without_evaluation(self, user_query: str, project_name: str = "默认项目", output_dir: str = "outputs") -> Dict[str, str]:
        """
        完整文档生成流程（不包含质量评估阶段）
        专为API服务器设计，跳过质量评估以提高响应速度
        
        Args:
            user_query: 用户需求描述
            project_name: 项目名称，用于RAG检索
            output_dir: 输出目录
            
        Returns:
            Dict: 包含生成文件路径的字典
        """
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("🚀 开始文档生成流程...")
        print("=" * 80)
        print(f"📝 用户需求：{user_query}")
        print(f"🏷️ 项目名称：{project_name}")
        print("=" * 80)
        
        try:
            # 阶段1：生成文档结构（OrchestratorAgent）
            print("\n🏗️  阶段1：生成文档结构和写作指导...")
            step1_start = time.time()
            
            document_guide = self.orchestrator.generate_complete_guide(user_query)
            
            step1_time = time.time() - step1_start
            sections_count = sum(len(part.get('sections', [])) for part in document_guide.get('report_guide', []))
            
            print(f"✅ 文档结构生成完成！")
            print(f"   📊 生成了 {len(document_guide.get('report_guide', []))} 个主要部分，{sections_count} 个子章节")
            print(f"   ⏱️  耗时：{step1_time:.1f}秒")
            
            # 保存阶段1结果
            step1_file = os.path.join(output_dir, f"step1_document_guide_{timestamp}.json")
            with open(step1_file, 'w', encoding='utf-8') as f:
                json.dump(document_guide, f, ensure_ascii=False, indent=2)
            
            # 阶段2：智能检索相关资料（SectionWriterAgent）
            print("\n🔍 阶段2：为各章节智能检索相关资料...")
            step2_start = time.time()
            
            enriched_guide = self.section_writer.process_report_guide(document_guide, project_name)
            
            step2_time = time.time() - step2_start
            print(f"✅ 资料检索完成！")
            print(f"   🔍 为 {sections_count} 个章节检索了相关资料")
            print(f"   ⏱️  耗时：{step2_time:.1f}秒")
            
            # 保存阶段2结果
            step2_file = os.path.join(output_dir, f"step2_enriched_guide_{timestamp}.json")
            with open(step2_file, 'w', encoding='utf-8') as f:
                json.dump(enriched_guide, f, ensure_ascii=False, indent=2)
            
            # 阶段3：生成最终文档（ContentGeneratorAgent）
            print("\n📝 阶段3：生成最终文档内容...")
            step3_start = time.time()
            
            # 保存为content_generator能识别的文件名
            generation_input = os.path.join(output_dir, f"生成文档的依据_{timestamp}.json")
            with open(generation_input, 'w', encoding='utf-8') as f:
                json.dump(enriched_guide, f, ensure_ascii=False, indent=2)
            
            # 生成最终文档
            final_doc_path = self.content_generator.generate_document(generation_input)
            
            step3_time = time.time() - step3_start
            print(f"✅ 最终文档生成完成！")
            print(f"   ⏱️  耗时：{step3_time:.1f}秒")
            
            # 计算总耗时（不包含质量评估）
            total_time = step1_time + step2_time + step3_time
            print("\n" + "=" * 80)
            print("🎉 文档生成流程完成！（已跳过质量评估）")
            print(f"📊 总体统计：")
            print(f"   📑 主要部分：{len(document_guide.get('report_guide', []))} 个")
            print(f"   📄 子章节：{sections_count} 个")
            print(f"   ⏱️  总耗时：{total_time:.1f}秒")
            print("=" * 80)
            
            # 返回生成的文件路径（不包含质量评估文件）
            result = {
                'document_guide': step1_file,
                'enriched_guide': step2_file,
                'generation_input': generation_input,
                'final_document': final_doc_path,
                'output_directory': output_dir
            }
            
            return result
            
        except Exception as e:
            print(f"❌ 文档生成过程中出现错误: {e}")
            raise


def print_banner():
    """打印程序横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                        Gauz文档Agent - 智能长文档生成系统                        ║
║                                                                              ║
║  🤖 基于多Agent架构的智能文档生成系统                                            ║
║  📝 支持从查询到完整文档的全流程自动化生成                                        ║
║  🚀 集成结构规划、智能检索、内容生成、质量评估四大核心功能                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def interactive_mode():
    """交互模式"""
    print("\n🎮 进入交互模式")
    print("💡 您可以输入任何文档需求，系统将为您自动生成完整的专业文档")
    print("📌 支持的文档类型：评估报告、分析报告、方案书、技术文档等")
    print("🔄 支持智能重新生成：基于质量评估自动优化文档")
    print("⚡ 输入 'quit' 或 'exit' 退出程序")
    print("⚡ 输入 'regenerate' 进入文档重新生成模式")
    print("⚡ 输入 'final_review' 进入final_review_agent模式")
    
    pipeline = DocumentGenerationPipeline()
    
    while True:
        print("\n" + "-" * 60)
        user_input = input("📝 请描述您需要生成的文档：").strip()
        
        if user_input.lower() in ['quit', 'exit', '退出', 'q']:
            print("👋 感谢使用Gauz文档Agent，再见！")
            break
            
        if not user_input:
            print("❌ 请输入有效的文档描述")
            continue
        
        if user_input.lower() == 'regenerate':
            # 进入文档重新生成模式
            print("\n🔄 进入文档重新生成模式")
            original_json = input("📄 请输入原始JSON文档路径：").strip()
            quality_analysis = input("📊 请输入质量评估文件路径：").strip()
            
            if not original_json or not quality_analysis:
                print("❌ 请提供有效的文件路径")
                continue
            
            try:
                result_files = pipeline.regenerate_and_merge_document(
                    original_json, quality_analysis
                )
                
                print(f"\n📁 重新生成的文件：")
                print(f"   📄 合并后文档: {result_files['merged_document']}")
                print(f"   📊 重新生成的章节: {result_files['regenerated_sections']}")
                print(f"   📋 合并后JSON: {result_files['merged_json']}")
                
                print(f"\n✨ 您可以在 '{result_files['output_directory']}' 目录下查看所有生成的文件")
                
            except Exception as e:
                print(f"❌ 重新生成失败: {e}")
                print("💡 请检查文件路径是否正确")
            
            continue
        
        if user_input.lower() == 'final_review':
            # 进入final_review_agent模式
            print("\n🔍 进入final_review_agent模式")
            markdown_file = input("📄 请输入Markdown文档路径：").strip()
            json_file = input("📊 请输入原始JSON文档路径：").strip()
            document_title = input("📝 请输入文档标题：").strip()
            
            if not markdown_file or not json_file or not document_title:
                print("❌ 请提供有效的文件路径和文档标题")
                continue
            
            try:
                result_files = pipeline.final_review_workflow(
                    markdown_file, json_file, document_title
                )
                
                print(f"\n📁 final_review_agent结果：")
                print(f"   📋 评审结果: {result_files.get('analysis_file', 'N/A')}")
                print(f"   📊 工作流程摘要: {result_files.get('summary_file', 'N/A')}")
                print(f"   📝 重新生成章节: {result_files.get('regeneration_sections', 0)} 个")
                print(f"   📄 总字数: {result_files.get('total_words', 0)} 字")
                print(f"   📊 平均质量: {result_files.get('average_quality', 0):.2f}")
                
                print(f"\n✨ 您可以在 '{result_files['output_directory']}' 目录下查看所有生成的文件")
                
            except Exception as e:
                print(f"❌ final_review_agent失败: {e}")
                print("💡 请检查文件路径是否正确")
            
            continue
        
        try:
            # 询问是否启用自动重新生成
            auto_regen = input("🔄 是否启用自动重新生成功能？(y/N): ").strip().lower()
            use_regeneration = auto_regen in ['y', 'yes', '是', '启用']
            
            if use_regeneration:
                # 使用完整工作流（包含自动重新生成）
                result_files = pipeline.complete_workflow_with_regeneration(
                    user_input, "医灵古庙", "医灵古庙", auto_regenerate=True
                )
            else:
                # 使用标准工作流
                result_files = pipeline.generate_document(user_input, "医灵古庙")
            
            print(f"\n📁 生成的文件：")
            for file_type, file_path in result_files.items():
                if file_type != 'output_directory':
                    if file_type == 'final_document':
                        print(f"   📄 最终文档: {file_path}")
                    elif file_type == 'quality_analysis':
                        print(f"   📊 质量分析: {file_path}")
                    elif file_type == 'quality_report':
                        print(f"   📋 质量报告: {file_path}")
                    elif file_type == 'merged_document':
                        print(f"   🔄 重新生成后文档: {file_path}")
                    elif file_type == 'regenerated_sections':
                        print(f"   📝 重新生成的章节: {file_path}")
                    else:
                        print(f"   {file_type}: {file_path}")
            
            print(f"\n✨ 您可以在 '{result_files['output_directory']}' 目录下查看所有生成的文件")
            
        except Exception as e:
            print(f"❌ 生成失败: {e}")
            print("💡 请尝试重新描述您的需求或检查系统配置")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Gauz文档Agent - 智能长文档生成系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py --interactive
  python main.py --query "为城市更新项目编写环境影响评估报告"
  python main.py --query "白云区文物保护影响评估报告" --output outputs/heritage
        """
    )
    
    parser.add_argument(
        '--query', '-q',
        type=str,
        help='直接指定文档生成需求'
    )
    
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='进入交互模式'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='医灵古庙',
        help='指定输出目录（默认：医灵古庙）'
    )
    
    parser.add_argument(
        '--regenerate', '-r',
        action='store_true',
        help='启用自动重新生成功能（基于质量评估结果）'
    )
    
    parser.add_argument(
        '--merge-only',
        nargs=2,
        metavar=('ORIGINAL_JSON', 'QUALITY_ANALYSIS'),
        help='仅执行文档重新生成和合并（需要提供原始JSON文档和质量评估文件路径）'
    )
    
    parser.add_argument(
        '--final-review',
        nargs=3,
        metavar=('MARKDOWN_FILE', 'JSON_FILE', 'DOCUMENT_TITLE'),
        help='执行final_review_agent工作流程（需要提供Markdown文档、JSON文档和文档标题）'
    )
    
    args = parser.parse_args()
    
    # 打印横幅
    print_banner()
    
    # 检查参数
    if not args.query and not args.interactive and not args.merge_only and not args.final_review:
        print("💡 请使用 --query 指定需求或使用 --interactive 进入交互模式")
        print("📖 使用 --help 查看详细帮助信息")
        return
    
    try:
        pipeline = DocumentGenerationPipeline()
        
        if args.merge_only:
            # 仅执行重新生成和合并模式
            print(f"🔄 文档重新生成和合并模式")
            original_json, quality_analysis = args.merge_only
            result_files = pipeline.regenerate_and_merge_document(
                original_json, quality_analysis, args.output
            )
            
            print(f"\n📁 文档已重新生成到目录：{result_files['output_directory']}")
            print(f"📄 合并后文档：{result_files['merged_document']}")
            print(f"📊 重新生成的章节：{result_files['regenerated_sections']}")
            
        elif args.final_review:
            # 执行final_review_agent模式
            print(f"🔍 final_review_agent模式")
            markdown_file, json_file, document_title = args.final_review
            result_files = pipeline.final_review_workflow(
                markdown_file, json_file, document_title, args.output
            )
            
            print(f"\n📁 final_review_agent已完成到目录：{result_files['output_directory']}")
            print(f"📋 评审结果：{result_files['analysis_file']}")
            print(f"📊 工作流程摘要：{result_files['summary_file']}")
            print(f"📝 重新生成章节：{result_files['regeneration_sections']} 个")
            print(f"📄 总字数：{result_files['total_words']} 字")
            print(f"📊 平均质量：{result_files['average_quality']:.2f}")
            
        elif args.interactive:
            # 交互模式
            interactive_mode()
        else:
            # 直接生成模式
            print(f"🎯 直接生成模式")
            
            if args.regenerate:
                # 使用完整工作流（包含自动重新生成）
                result_files = pipeline.complete_workflow_with_regeneration(
                    args.query, "医灵古庙", args.output, auto_regenerate=True
                )
            else:
                # 使用标准工作流
                result_files = pipeline.generate_document(args.query, "医灵古庙", args.output)
            
            print(f"\n📁 文档已生成到目录：{result_files['output_directory']}")
            print(f"📄 最终文档：{result_files['final_document']}")
            if 'quality_report' in result_files:
                print(f"📊 质量报告：{result_files['quality_report']}")
                print(f"📋 质量分析：{result_files['quality_analysis']}")
            if 'merged_document' in result_files:
                print(f"🔄 重新生成后文档：{result_files['merged_document']}")
                print(f"📝 重新生成的章节：{result_files['regenerated_sections']}")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 程序执行失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())