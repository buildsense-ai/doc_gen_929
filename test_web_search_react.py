"""
测试带有Web搜索功能的ReactAgent
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
    level=logging.DEBUG,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('test_web_search_react.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def create_test_data():
    """创建测试数据 - 模拟一个质量较低的场景来触发Web搜索"""
    return {
        "report_guide": [
            {
                "title": "一、市场分析",
                "sections": [
                    {
                        "subtitle": "1.1、2025年第一季度经济形势",
                        "how_to_write": "分析2025年第一季度的宏观经济形势，包括GDP增长、通胀水平、就业状况等关键指标。重点关注政策变化对经济的影响，以及各行业的发展趋势。需要提供具体的数据支撑和权威分析。"
                    },
                    {
                        "subtitle": "1.2、人工智能行业发展现状",
                        "how_to_write": "深入分析人工智能行业在2025年的最新发展动态，包括技术突破、市场规模、主要玩家、投资情况等。重点关注ChatGPT、Claude等大语言模型的发展，以及AI在各个垂直领域的应用情况。"
                    }
                ]
            }
        ]
    }

def main():
    """主函数"""
    
    print("🧪 测试带有Web搜索功能的ReactAgent")
    print("=" * 60)
    
    try:
        # 创建测试数据
        test_data = create_test_data()
        
        print("🔗 初始化OpenRouter客户端和ReactAgent...")
        client = OpenRouterClient()
        agent = EnhancedReactAgent(client)
        
        print(f"🚀 开始处理报告指南 (测试Web搜索功能)...")
        start_time = datetime.now()
        
        # 处理测试数据
        result_data = agent.process_report_guide(test_data, project_name="test_web_search")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"\n⏱️ 处理完成，总耗时: {processing_time:.2f}秒")
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"test_web_search_output_{timestamp}.json"
        
        print(f"💾 保存结果到: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        # 分析结果
        print(f"\n📊 结果分析:")
        for part in result_data.get('report_guide', []):
            for section in part.get('sections', []):
                subtitle = section.get('subtitle', 'Unknown')
                
                text_count = len(section.get('retrieved_text', []))
                image_count = len(section.get('retrieved_image', []))
                table_count = len(section.get('retrieved_table', []))
                web_count = len(section.get('retrieved_web', []))
                
                print(f"  📝 {subtitle}:")
                print(f"     文本: {text_count}条, 图片: {image_count}条, 表格: {table_count}条, Web: {web_count}条")
                
                # 显示Web搜索结果详情
                if web_count > 0:
                    print(f"     🌐 Web搜索结果:")
                    for i, web_result in enumerate(section.get('retrieved_web', [])):
                        title = web_result.get('title', 'No Title')[:50]
                        url = web_result.get('url', 'No URL')
                        print(f"       {i+1}. {title} - {url}")
        
        print(f"\n✅ 测试完成!")
        print(f"   输出文件: {output_file}")
        print(f"   日志文件: test_web_search_react.log")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        logging.error(f"测试错误: {e}", exc_info=True)

if __name__ == "__main__":
    main()
