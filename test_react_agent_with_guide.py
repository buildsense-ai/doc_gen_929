"""
测试优化后的ReAct Agent - 使用step1_document_guide文件
"""

import json
import logging
import sys
import os
from datetime import datetime

# 添加项目路径
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.append(project_root)

from Document_Agent.section_writer_agent.react_agent import EnhancedReactAgent
from clients.openrouter_client import OpenRouterClient

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 设置为DEBUG级别以查看详细信息
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('test_react_agent_guide.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main():
    """主函数"""
    
    print("🧪 测试优化后的ReAct Agent - 多维度并行查询")
    print("=" * 60)
    
    # 输入文件路径
    input_file = "api_outputs/089d7c8f-18c2-44f1-94cf-c68f63a787c6_20250901_163359/step1_document_guide_20250901_163359.json"
    
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        return
    
    try:
        print(f"📖 读取输入文件: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        
        print("🔗 初始化OpenRouter客户端和ReactAgent...")
        client = OpenRouterClient()
        agent = EnhancedReactAgent(client)
        
        print(f"🚀 开始处理报告指南 (项目: test828)...")
        start_time = datetime.now()
        
        # 使用test828项目进行测试
        result_data = agent.process_report_guide(input_data, project_name="test828")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"\n⏱️ 所有章节处理完成，总耗时: {processing_time:.2f}秒")
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"test_react_output_guide_{timestamp}.json"
        
        print(f"💾 保存结果到: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # 显示统计信息
        print(f"\n📊 处理统计:")
        total_sections = 0
        sections_with_results = 0
        
        for part in result_data.get('report_guide', []):
            for section in part.get('sections', []):
                total_sections += 1
                if any(key in section for key in ['retrieved_text', 'retrieved_image', 'retrieved_table']):
                    sections_with_results += 1
                    
                    # 显示每个章节的结果统计
                    text_count = len(section.get('retrieved_text', []))
                    image_count = len(section.get('retrieved_image', []))
                    table_count = len(section.get('retrieved_table', []))
                    
                    print(f"  📝 {section.get('subtitle', 'Unknown')}: "
                          f"文本{text_count}条, 图片{image_count}条, 表格{table_count}条")
                
                # 递归处理subsections
                for subsection in section.get('subsections', []):
                    total_sections += 1
                    if any(key in subsection for key in ['retrieved_text', 'retrieved_image', 'retrieved_table']):
                        sections_with_results += 1
                        
                        text_count = len(subsection.get('retrieved_text', []))
                        image_count = len(subsection.get('retrieved_image', []))
                        table_count = len(subsection.get('retrieved_table', []))
                        
                        print(f"    📝 {subsection.get('subtitle', 'Unknown')}: "
                              f"文本{text_count}条, 图片{image_count}条, 表格{table_count}条")
        
        print(f"\n✅ 测试完成!")
        print(f"   总章节数: {total_sections}")
        print(f"   成功处理: {sections_with_results}")
        print(f"   输出文件: {output_file}")
        print(f"   日志文件: test_react_agent_guide.log")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        logging.error(f"测试错误: {e}", exc_info=True)

if __name__ == "__main__":
    main()
