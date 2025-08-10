"""
文档质量评估运行脚本

提供简单的接口来运行文档质量评估，分析文档的冗余度。
"""

import json
import logging
import sys
import os
from typing import Optional

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Document_Agent.final_review_agent.document_reviewer import DocumentReviewer, RedundancyAnalysis


def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('document_quality_analysis.log', encoding='utf-8')
        ]
    )


def analyze_document_from_file(file_path: str, document_title: Optional[str] = None, simple_format: bool = True):
    """
    从文件读取文档内容并进行质量分析
    
    Args:
        file_path: 文档文件路径
        document_title: 文档标题（可选，默认使用文件名）
        simple_format: 是否使用简化格式（默认True）
        
    Returns:
        分析结果（简化格式为list，完整格式为RedundancyAnalysis）
    """
    try:
        # 读取文档内容
        with open(file_path, 'r', encoding='utf-8') as f:
            document_content = f.read()
        
        # 如果没有提供标题，使用文件名
        if document_title is None:
            document_title = os.path.basename(file_path)
        
        # 创建评估器并分析
        reviewer = DocumentReviewer()
        
        if simple_format:
            analysis_result = reviewer.analyze_document_simple(document_content, document_title, file_path)
        else:
            analysis_result = reviewer.analyze_document_quality(document_content, document_title)
        
        return analysis_result
        
    except FileNotFoundError:
        print(f"❌ 文件未找到: {file_path}")
        return None
    except Exception as e:
        print(f"❌ 分析过程中发生错误: {e}")
        return None


def analyze_document_content(document_content: str, document_title: str = "未命名文档") -> RedundancyAnalysis:
    """
    直接分析文档内容
    
    Args:
        document_content: 文档内容
        document_title: 文档标题
        
    Returns:
        RedundancyAnalysis: 分析结果
    """
    try:
        reviewer = DocumentReviewer()
        analysis_result = reviewer.analyze_document_quality(document_content, document_title)
        return analysis_result
    except Exception as e:
        print(f"❌ 分析过程中发生错误: {e}")
        return None


def save_analysis_results(analysis: RedundancyAnalysis, document_title: str, output_dir: str = ".") -> str:
    """
    保存分析结果
    
    Args:
        analysis: 分析结果
        document_title: 文档标题
        output_dir: 输出目录
        
    Returns:
        str: 保存的文件路径
    """
    try:
        reviewer = DocumentReviewer()
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件路径
        output_path = os.path.join(output_dir, f"quality_analysis_{document_title}.json")
        
        # 保存分析结果
        saved_path = reviewer.save_analysis_result(analysis, document_title, output_path)
        
        # 生成质量报告
        report_content = reviewer.generate_quality_report(analysis, document_title)
        report_path = os.path.join(output_dir, f"quality_report_{document_title}.md")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"✅ 分析结果已保存:")
        print(f"   - JSON数据: {saved_path}")
        print(f"   - 质量报告: {report_path}")
        
        return saved_path
        
    except Exception as e:
        print(f"❌ 保存分析结果时发生错误: {e}")
        return None


def main():
    """主函数 - 命令行接口"""
    setup_logging()
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python run_reviewer.py <文档文件路径> [文档标题]")
        print("")
        print("示例:")
        print("  python run_reviewer.py 完整版文档_20250731_150525.md")
        print("  python run_reviewer.py 完整版文档_20250731_150525.md '医灵古庙项目报告'")
        return
    
    file_path = sys.argv[1]
    document_title = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"🔍 开始分析文档: {file_path}")
    
    # 分析文档（使用简化格式）
    analysis_result = analyze_document_from_file(file_path, document_title, simple_format=True)
    
    if analysis_result is None:
        print("❌ 文档分析失败")
        return
    
    # 显示分析结果摘要
    print(f"\n📊 分析结果摘要:")
    print(f"   找到需要修改的位置数: {len(analysis_result)}")
    
    # 保存简化结果为JSON
    if document_title is None:
        document_title = os.path.basename(file_path)
    
    output_path = f"simple_analysis_{document_title}.json"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, ensure_ascii=False, indent=2)
        print(f"✅ 简化分析结果已保存: {output_path}")
    except Exception as e:
        print(f"❌ 保存结果时发生错误: {e}")
    
    # 显示前几个修改建议
    if analysis_result:
        print(f"\n💡 主要修改建议:")
        for i, item in enumerate(analysis_result[:3], 1):
            print(f"   {i}. {item['location']}: {item['suggestion'][:100]}...")


if __name__ == "__main__":
    main()