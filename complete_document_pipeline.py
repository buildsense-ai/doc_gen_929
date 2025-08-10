#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gauz文档Agent - 完整文档生成闭环流程

实现从初始文档生成到质量评估、章节重新生成、最终文档合并的完整闭环流程
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from main import DocumentGenerationPipeline
    from Document_Agent.final_review_agent.document_reviewer import DocumentReviewer
    from Document_Agent.final_review_agent.regenerate_sections import DocumentRegenerator
    from Document_Agent.final_review_agent.json_merger import JSONDocumentMerger
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保您在项目根目录下运行此程序，并安装了所有依赖。")
    sys.exit(1)


class CompleteDocumentPipeline:
    """
    完整文档生成闭环流程
    
    实现以下完整流程：
    1. 初始文档生成（结构规划 → 资料检索 → 内容生成）
    2. 文档质量评估（识别冗余内容和问题）
    3. 章节重新生成（基于评估建议优化内容）
    4. 智能文档合并（生成最终优化版本）
    """
    
    def __init__(self):
        """初始化完整流水线"""
        print("🔧 正在初始化完整文档生成闭环系统...")
        
        # 初始化各个组件
        self.base_pipeline = DocumentGenerationPipeline()
        self.document_reviewer = DocumentReviewer()
        self.document_regenerator = DocumentRegenerator()
        # DocumentMerger需要在使用时初始化，因为它需要特定的参数
        
        print("✅ 完整闭环系统初始化成功！")
    
    def generate_complete_document_with_optimization(self, 
                                                   user_query: str, 
                                                   project_name: str = "默认项目", 
                                                   output_dir: str = "complete_outputs",
                                                   enable_regeneration: bool = True) -> Dict[str, Any]:
        """
        完整文档生成闭环流程
        
        Args:
            user_query: 用户需求描述
            project_name: 项目名称
            output_dir: 输出目录
            enable_regeneration: 是否启用章节重新生成和合并
            
        Returns:
            Dict: 包含所有生成文件和流程信息的字典
        """
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("🚀 开始完整文档生成闭环流程...")
        print("=" * 100)
        print(f"📝 用户需求：{user_query}")
        print(f"🏷️ 项目名称：{project_name}")
        print(f"🔄 章节优化：{'启用' if enable_regeneration else '禁用'}")
        print("=" * 100)
        
        total_start_time = time.time()
        result = {
            'timestamp': timestamp,
            'user_query': user_query,
            'project_name': project_name,
            'output_directory': output_dir,
            'enable_regeneration': enable_regeneration,
            'stages': {}
        }
        
        try:
            # ==================== 阶段1-3：初始文档生成 ====================
            print("\n📋 阶段1-3：初始文档生成（结构规划 → 资料检索 → 内容生成）")
            stage1_start = time.time()
            
            # 使用基础流水线生成初始文档（不包含质量评估）
            initial_result = self.base_pipeline.generate_document_without_evaluation(
                user_query=user_query,
                project_name=project_name,
                output_dir=output_dir
            )
            
            stage1_time = time.time() - stage1_start
            result['stages']['initial_generation'] = {
                'duration': stage1_time,
                'files': initial_result,
                'status': 'completed'
            }
            
            print(f"✅ 初始文档生成完成！耗时：{stage1_time:.1f}秒")
            print(f"   📄 生成文档：{initial_result['final_document']}")
            
            # 如果禁用重新生成，直接返回初始结果
            if not enable_regeneration:
                total_time = time.time() - total_start_time
                result['total_duration'] = total_time
                result['final_document'] = initial_result['final_document']
                result['optimization_applied'] = False
                
                print("\n" + "=" * 100)
                print("🎉 文档生成流程完成！（未启用章节优化）")
                print(f"⏱️  总耗时：{total_time:.1f}秒")
                print("=" * 100)
                
                return result
            
            # ==================== 阶段4：文档质量评估 ====================
            print("\n📊 阶段4：文档质量深度评估")
            stage4_start = time.time()
            
            # 读取生成的文档内容
            with open(initial_result['final_document'], 'r', encoding='utf-8') as f:
                document_content = f.read()
            
            # 进行简化质量分析（用于重新生成）
            document_title = os.path.basename(initial_result['final_document']).replace('.md', '')
            quality_issues = self.document_reviewer.analyze_document_simple(
                document_content=document_content,
                document_path=initial_result['final_document'],
                document_title=document_title
            )
            
            # 保存质量评估结果到文件
            if quality_issues:
                analysis_file = self.document_reviewer.save_simple_analysis_result(
                    quality_issues=quality_issues,
                    document_title=document_title,
                    output_dir=output_dir
                )
                print(f"   📄 评估结果已保存：{analysis_file}")
            
            stage4_time = time.time() - stage4_start
            result['stages']['quality_evaluation'] = {
                'duration': stage4_time,
                'issues_found': len(quality_issues),
                'issues': quality_issues,
                'status': 'completed'
            }
            
            print(f"✅ 质量评估完成！耗时：{stage4_time:.1f}秒")
            print(f"   ⚠️  发现问题：{len(quality_issues)} 个章节需要优化")
            
            # 如果没有发现问题，直接返回原文档
            if len(quality_issues) == 0:
                total_time = time.time() - total_start_time
                result['total_duration'] = total_time
                result['final_document'] = initial_result['final_document']
                result['optimization_applied'] = False
                
                print("\n" + "=" * 100)
                print("🎉 文档质量良好，无需优化！")
                print(f"⏱️  总耗时：{total_time:.1f}秒")
                print("=" * 100)
                
                return result
            
            # ==================== 阶段5：章节重新生成 ====================
            print("\n🔄 阶段5：基于评估建议重新生成章节")
            stage5_start = time.time()
            
            # 首先保存质量问题到临时文件
            temp_evaluation_file = os.path.join(output_dir, f"temp_evaluation_{timestamp}.json")
            with open(temp_evaluation_file, 'w', encoding='utf-8') as f:
                json.dump(quality_issues, f, ensure_ascii=False, indent=2)
            
            # 重新生成有问题的章节
            regenerated_result = self.document_regenerator.regenerate_document_sections(
                evaluation_file=temp_evaluation_file,
                document_file=initial_result['final_document'],
                output_dir=os.path.join(output_dir, "regenerated_outputs")
            )
            
            # 清理临时文件
            try:
                os.remove(temp_evaluation_file)
            except:
                pass
            
            stage5_time = time.time() - stage5_start
            result['stages']['section_regeneration'] = {
                'duration': stage5_time,
                'regenerated_sections': len(regenerated_result),
                'output_files': regenerated_result,
                'status': 'completed'
            }
            
            print(f"✅ 章节重新生成完成！耗时：{stage5_time:.1f}秒")
            print(f"   🔄 重新生成：{len(regenerated_result)} 个章节")
            
            # ==================== 阶段6：智能文档合并 ====================
            print("\n🔗 阶段6：智能合并生成最终优化文档")
            stage6_start = time.time()
            
            # 保存重新生成的结果到JSON文件
            regenerated_json_path = os.path.join(output_dir, "regenerated_outputs", f"regenerated_sections_{timestamp}.json")
            os.makedirs(os.path.dirname(regenerated_json_path), exist_ok=True)
            with open(regenerated_json_path, 'w', encoding='utf-8') as f:
                json.dump(regenerated_result, f, ensure_ascii=False, indent=2)
            
            # 获取原始JSON文件路径
            original_json_path = initial_result.get('structured_document', '')
            if not original_json_path or not os.path.exists(original_json_path):
                print(f"⚠️ 原始JSON文件不存在，尝试查找: {original_json_path}")
                # 尝试从输出目录中查找JSON文件
                for file in os.listdir(output_dir):
                    if file.endswith('.json') and '生成文档的依据' in file:
                        original_json_path = os.path.join(output_dir, file)
                        print(f"✓ 找到原始JSON文件: {original_json_path}")
                        break
            
            # 初始化并使用JSON文档合并器
            document_merger = JSONDocumentMerger(
                original_json_path=original_json_path,
                regenerated_json_path=regenerated_json_path
            )
            
            # 加载文件
            document_merger.load_original_json()
            document_merger.load_regenerated_sections()
            
            # 在JSON层面合并文档
            merged_json_data = document_merger.merge_json_documents()
            
            # 保存合并后的JSON文档
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(original_json_path))[0]
            merged_json_path = os.path.join(output_dir, f"merged_{base_name}_{timestamp_str}.json")
            final_merged_json_path = document_merger.save_merged_json(merged_json_data, merged_json_path)
            
            # 转换为Markdown格式
            merged_md_path = os.path.join(output_dir, f"merged_{base_name}_{timestamp_str}.md")
            final_merged_path = document_merger.convert_to_markdown(merged_json_data, merged_md_path)
            
            # 生成摘要报告
            document_merger.generate_summary_report(final_merged_json_path, final_merged_path)
            
            # 构建返回结果
            merged_result = {
                'merged_document': final_merged_path,
                'summary_report': final_merged_path.replace('.md', '_summary.md'),
                'sections_replaced': len(regenerated_result)
            }
            
            stage6_time = time.time() - stage6_start
            result['stages']['document_merging'] = {
                'duration': stage6_time,
                'merged_document': merged_result['merged_document'],
                'summary_report': merged_result['summary_report'],
                'sections_replaced': merged_result.get('sections_replaced', 0),
                'status': 'completed'
            }
            
            print(f"✅ 文档合并完成！耗时：{stage6_time:.1f}秒")
            print(f"   📄 最终文档：{merged_result['merged_document']}")
            print(f"   📋 摘要报告：{merged_result['summary_report']}")
            
            # ==================== 流程完成 ====================
            total_time = time.time() - total_start_time
            result['total_duration'] = total_time
            result['final_document'] = merged_result['merged_document']
            result['optimization_applied'] = True
            result['summary_report'] = merged_result['summary_report']
            
            print("\n" + "=" * 100)
            print("🎉 完整文档生成闭环流程全部完成！")
            print(f"📊 流程统计：")
            print(f"   📋 初始生成：{stage1_time:.1f}秒")
            print(f"   📊 质量评估：{stage4_time:.1f}秒")
            print(f"   🔄 章节重生：{stage5_time:.1f}秒")
            print(f"   🔗 文档合并：{stage6_time:.1f}秒")
            print(f"   ⏱️  总耗时：{total_time:.1f}秒")
            print(f"   ✨ 优化章节：{len(quality_issues)} 个")
            print("=" * 100)
            
            return result
            
        except Exception as e:
            print(f"❌ 完整流程执行失败: {e}")
            result['error'] = str(e)
            result['status'] = 'failed'
            raise

    
def run_complete_pipeline(user_query: str,
                          project_name: str = "默认项目",
                          output_dir: str = "complete_outputs",
                          enable_regeneration: bool = True) -> Dict[str, Any]:
    """
    一键运行四个Agent的完整闭环流程（结构→检索→成文→评审→再生→合并）。

    Args:
        user_query: 文档生成需求描述
        project_name: 项目名称（用于检索与标识）
        output_dir: 输出目录
        enable_regeneration: 是否启用基于评审结果的章节再生成与合并

    Returns:
        Dict[str, Any]: 包含各阶段输出路径与统计信息的结果字典。额外包含
        键 `process_report`（流程报告路径），便于溯源。
    """
    pipeline = CompleteDocumentPipeline()
    result = pipeline.generate_complete_document_with_optimization(
        user_query=user_query,
        project_name=project_name,
        output_dir=output_dir,
        enable_regeneration=enable_regeneration,
    )

    # 可选：生成流程报告
    try:
        report_path = pipeline.generate_process_report(result)
        result['process_report'] = report_path
    except Exception:
        # 报告生成失败不阻断主流程
        pass

    return result
    
    def generate_process_report(self, result: Dict[str, Any], output_path: str = None) -> str:
        """
        生成流程报告
        
        Args:
            result: 流程执行结果
            output_path: 报告输出路径
            
        Returns:
            str: 报告文件路径
        """
        if output_path is None:
            output_path = os.path.join(
                result['output_directory'], 
                f"complete_process_report_{result['timestamp']}.md"
            )
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report_content = f"""# 完整文档生成闭环流程报告

**生成时间**: {timestamp}
**用户需求**: {result['user_query']}
**项目名称**: {result['project_name']}
**章节优化**: {'启用' if result['enable_regeneration'] else '禁用'}
**总耗时**: {result.get('total_duration', 0):.1f}秒

## 流程概览

本次文档生成采用了完整的闭环优化流程：

1. **初始文档生成** - 结构规划、资料检索、内容生成
2. **文档质量评估** - 识别冗余内容和改进点
3. **章节重新生成** - 基于评估建议优化内容
4. **智能文档合并** - 生成最终优化版本

## 各阶段详情

"""
        
        # 添加各阶段详情
        for stage_name, stage_info in result.get('stages', {}).items():
            stage_title = {
                'initial_generation': '初始文档生成',
                'quality_evaluation': '文档质量评估',
                'section_regeneration': '章节重新生成',
                'document_merging': '智能文档合并'
            }.get(stage_name, stage_name)
            
            report_content += f"### {stage_title}\n\n"
            report_content += f"- **耗时**: {stage_info.get('duration', 0):.1f}秒\n"
            report_content += f"- **状态**: {stage_info.get('status', 'unknown')}\n"
            
            if stage_name == 'quality_evaluation':
                report_content += f"- **发现问题**: {stage_info.get('issues_found', 0)} 个章节需要优化\n"
            elif stage_name == 'section_regeneration':
                report_content += f"- **重新生成**: {stage_info.get('regenerated_sections', 0)} 个章节\n"
            elif stage_name == 'document_merging':
                report_content += f"- **替换章节**: {stage_info.get('sections_replaced', 0)} 个\n"
            
            report_content += "\n"
        
        # 添加最终结果
        report_content += f"""## 最终结果

- **最终文档**: {result.get('final_document', 'N/A')}
- **优化应用**: {'是' if result.get('optimization_applied', False) else '否'}
- **输出目录**: {result.get('output_directory', 'N/A')}

## 质量提升

通过完整的闭环优化流程，本次生成的文档在以下方面得到了提升：

1. **内容质量** - 消除了冗余表达，提高了内容精炼度
2. **逻辑结构** - 优化了章节间的逻辑关系和衔接
3. **专业性** - 增强了专业术语使用和表达准确性
4. **可读性** - 改善了文档的整体可读性和用户体验

---

*本报告由Gauz文档Agent完整闭环系统自动生成*
"""
        
        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return output_path


def main():
    """主函数 - 演示完整闭环流程"""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Gauz文档Agent - 完整文档生成闭环系统                        ║
║                                                                              ║
║  🔄 实现从初始生成到质量评估、章节优化、智能合并的完整闭环流程                  ║
║  📝 支持智能识别问题章节并自动重新生成优化内容                                ║
║  🚀 提供专业级文档质量控制和持续改进能力                                      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    
    # 创建完整流水线
    pipeline = CompleteDocumentPipeline()
    
    # 示例：生成一个完整的文档
    user_query = "编写医灵古庙文物保护项目的可行性研究报告"
    project_name = "医灵古庙"
    
    try:
        # 执行完整闭环流程
        result = pipeline.generate_complete_document_with_optimization(
            user_query=user_query,
            project_name=project_name,
            output_dir="complete_demo_outputs",
            enable_regeneration=True
        )
        
        # 生成流程报告
        report_path = pipeline.generate_process_report(result)
        print(f"\n📋 流程报告已生成：{report_path}")
        
        print(f"\n📁 所有文件已保存到：{result['output_directory']}")
        print(f"📄 最终优化文档：{result['final_document']}")
        
    except Exception as e:
        print(f"❌ 演示执行失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())