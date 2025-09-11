#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整测试ReAct Agent - 处理整个JSON并生成step2结果
"""

import json
import logging
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Document_Agent.section_writer_agent.react_agent import EnhancedReactAgent
from clients.external_api_client import get_external_api_client
from config.settings import get_concurrency_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'complete_react_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8')
    ]
)

class MockClient:
    """模拟LLM客户端 - 提供更真实的响应"""
    
    def __init__(self):
        self.call_count = 0
    
    def generate(self, prompt: str) -> str:
        self.call_count += 1
        print(f"\n🤖 AI调用 #{self.call_count} - Prompt长度: {len(prompt)} 字符")
        
        # 根据prompt内容返回模拟响应
        if "多维度检索计划" in prompt or "维度名称" in prompt:
            # 根据章节内容生成不同的查询维度
            if "概况" in prompt:
                return '''[
  {"dimension": "基本信息", "query": "清远市清新区 职业教育 基本情况", "priority": "high"},
  {"dimension": "政策支持", "query": "中等职业教育 政府政策", "priority": "high"},
  {"dimension": "发展现状", "query": "职业教育基地 发展状况", "priority": "medium"}
]'''
            elif "编制依据" in prompt:
                return '''[
  {"dimension": "法规政策", "query": "职业教育 法律法规", "priority": "high"},
  {"dimension": "技术标准", "query": "教育基地 建设标准", "priority": "high"},
  {"dimension": "规划文件", "query": "清远市 教育规划", "priority": "medium"}
]'''
            elif "需求分析" in prompt:
                return '''[
  {"dimension": "市场需求", "query": "职业教育 人才需求", "priority": "high"},
  {"dimension": "学生规模", "query": "中等职业学校 招生规模", "priority": "high"},
  {"dimension": "专业设置", "query": "职业教育 专业配置", "priority": "medium"}
]'''
            elif "选址" in prompt or "建设条件" in prompt:
                return '''[
  {"dimension": "地理条件", "query": "清远市清新区 地理环境", "priority": "high"},
  {"dimension": "基础设施", "query": "教育基地 配套设施", "priority": "high"},
  {"dimension": "交通条件", "query": "清远 交通便利性", "priority": "medium"}
]'''
            elif "技术方案" in prompt or "设备方案" in prompt:
                return '''[
  {"dimension": "教学技术", "query": "职业教育 教学设备", "priority": "high"},
  {"dimension": "信息化建设", "query": "智慧校园 技术方案", "priority": "high"},
  {"dimension": "实训设备", "query": "职业技能 实训装备", "priority": "medium"}
]'''
            elif "投资" in prompt or "财务" in prompt:
                return '''[
  {"dimension": "投资估算", "query": "职业教育基地 建设成本", "priority": "high"},
  {"dimension": "资金来源", "query": "教育项目 融资方案", "priority": "high"},
  {"dimension": "经济效益", "query": "职业教育 投资回报", "priority": "medium"}
]'''
            elif "风险" in prompt:
                return '''[
  {"dimension": "建设风险", "query": "教育基地 建设风险", "priority": "high"},
  {"dimension": "运营风险", "query": "职业学校 运营管理", "priority": "high"},
  {"dimension": "政策风险", "query": "教育政策 变化影响", "priority": "medium"}
]'''
            else:
                return '''[
  {"dimension": "政策法规", "query": "中等职业教育 相关政策", "priority": "high"},
  {"dimension": "建设标准", "query": "教育基地 建设规范", "priority": "high"},
  {"dimension": "案例参考", "query": "职业教育基地 成功案例", "priority": "medium"}
]'''
        
        elif "分析RAG检索结果" in prompt or "信息缺口" in prompt:
            # 根据章节生成不同的Web搜索查询
            if "概况" in prompt:
                return "清远市清新区 职业教育发展 最新规划 2024"
            elif "政策" in prompt or "规划" in prompt:
                return "广东省 职业教育政策 最新文件 2024"
            elif "需求" in prompt:
                return "清远市 技能人才需求 市场调研 2024"
            elif "选址" in prompt:
                return "清远市清新区 土地利用 教育用地 2024"
            elif "技术" in prompt:
                return "职业教育 智能化建设 最新技术 2024"
            elif "投资" in prompt or "财务" in prompt:
                return "职业教育基地 投资标准 资金政策 2024"
            elif "环境" in prompt:
                return "教育项目 环境影响评价 标准 2024"
            elif "风险" in prompt:
                return "教育基地建设 风险防控 案例 2024"
            else:
                return "清远市清新区 中等职业教育 最新动态 2024"
        
        else:
            return "模拟AI响应内容"

def complete_react_test():
    """完整测试ReAct Agent处理流程"""
    
    # 读取测试JSON文件
    json_file = "Document_Agent/section_writer_agent/step1_guide_json_step1_document_guide_20250904_165848.json"
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            guide_data = json.load(f)
    except Exception as e:
        print(f"❌ 读取JSON文件失败: {e}")
        return
    
    print("✅ 成功读取指南JSON文件")
    print(f"📊 报告包含 {len(guide_data['report_guide'])} 个主要部分")
    
    # 统计总章节数
    total_sections = 0
    for part in guide_data['report_guide']:
        total_sections += len(part.get('sections', []))
    print(f"📝 总计 {total_sections} 个章节")
    
    # 初始化ReAct Agent
    mock_client = MockClient()
    concurrency_manager = get_concurrency_manager()
    
    print("\n🚀 初始化ReAct Agent...")
    react_agent = EnhancedReactAgent(
        client=mock_client,
        concurrency_manager=concurrency_manager
    )
    
    # 设置项目名称
    project_name = "清远市清新区中等职业教育基地"
    print(f"🏗️ 项目名称: {project_name}")
    
    print("\n" + "="*80)
    print("🧪 开始完整处理所有章节...")
    print("="*80)
    
    # 处理所有章节
    processed_count = 0
    
    for part_idx, part in enumerate(guide_data['report_guide']):
        print(f"\n📋 处理部分 {part_idx + 1}/{len(guide_data['report_guide'])}: {part['title']}")
        
        for section_idx, section in enumerate(part.get('sections', [])):
            processed_count += 1
            
            print(f"\n🎯 处理章节 {processed_count}/{total_sections}")
            print(f"📌 章节: {section['subtitle']}")
            
            try:
                # 模拟完整的两步处理流程
                
                # 第1步: 生成多维度RAG查询
                print("🔍 第1步: 生成RAG查询...")
                section_context = {
                    'subtitle': section['subtitle'],
                    'how_to_write': section['how_to_write'],
                    'part_title': part['title'],
                    'part_goal': part.get('goal', '')
                }
                
                multi_queries = react_agent._generate_multi_dimensional_queries(section_context, None)
                
                if not multi_queries:
                    print("❌ 未能生成RAG查询")
                    continue
                
                print(f"✅ 生成 {len(multi_queries)} 个RAG查询维度")
                
                # 模拟RAG检索结果
                mock_rag_results = []
                for query in multi_queries:
                    mock_rag_results.extend([
                        {
                            'content': f'关于{section["subtitle"]}的{query["dimension"]}相关内容: 这里是从文档库检索到的详细资料，包含了相关的政策文件、技术标准和实施案例等信息...',
                            'type': 'text',
                            'page_number': f'{len(mock_rag_results) + 1}',
                            'source': f'{query["dimension"]}文档',
                            'dimension': query['dimension'],
                            'priority': query['priority']
                        },
                        {
                            'content': f'{section["subtitle"]}相关图表和数据',
                            'type': 'image',
                            'page_number': f'{len(mock_rag_results) + 2}',
                            'source': f'{query["dimension"]}图表',
                            'path': f'/images/{query["dimension"]}_chart.png',
                            'description': f'{query["dimension"]}相关图表',
                            'dimension': query['dimension'],
                            'priority': query['priority']
                        }
                    ])
                
                print(f"📊 模拟RAG结果: {len(mock_rag_results)} 条")
                
                # 第2步: 生成Web搜索查询
                print("🌐 第2步: 生成Web查询...")
                web_query = react_agent._analyze_rag_gaps_and_generate_query(section_context, mock_rag_results)
                
                if not web_query:
                    print("❌ 未能生成Web查询")
                    web_query = f"清远市清新区 {section['subtitle']} 最新信息 2024"
                
                print(f"✅ Web查询: {web_query}")
                
                # 模拟Web搜索结果
                mock_web_results = [
                    {
                        'content': f'最新的{section["subtitle"]}相关网络资讯和政策动态...',
                        'type': 'web_text',
                        'source': 'Web搜索',
                        'url': f'https://example.com/{section["subtitle"]}',
                        'title': f'{section["subtitle"]}最新资讯',
                        'dimension': 'web_intelligent',
                        'priority': 'high'
                    }
                ]
                
                # 将结果添加到section中
                section['retrieved_text'] = [r for r in mock_rag_results if r['type'] == 'text'] + mock_web_results
                section['retrieved_image'] = [r for r in mock_rag_results if r['type'] == 'image']
                section['retrieved_table'] = []  # 暂无表格数据
                section['retrieved_web'] = mock_web_results
                
                print(f"✅ 章节处理完成: 文本{len(section['retrieved_text'])}条, 图片{len(section['retrieved_image'])}条, Web{len(section['retrieved_web'])}条")
                
            except Exception as e:
                print(f"❌ 章节处理失败: {e}")
                # 设置空结果
                section['retrieved_text'] = []
                section['retrieved_image'] = []
                section['retrieved_table'] = []
                section['retrieved_web'] = []
    
    print("\n" + "="*80)
    print("🎉 所有章节处理完成!")
    print("="*80)
    
    # 生成step2 JSON文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    step2_filename = f"step2_enriched_guide_{timestamp}.json"
    
    try:
        with open(step2_filename, 'w', encoding='utf-8') as f:
            json.dump(guide_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 生成step2文件: {step2_filename}")
        
    except Exception as e:
        print(f"❌ 生成step2文件失败: {e}")
    
    # 显示统计信息
    print(f"\n📊 处理统计:")
    print(f"   📝 处理章节数: {processed_count}")
    print(f"   🔍 AI调用次数: {mock_client.call_count}")
    print(f"   📄 预期AI调用: {processed_count * 2}")
    print(f"   🎯 流程验证: {'✅ 正常' if mock_client.call_count == processed_count * 2 else '❌ 异常'}")
    
    # 显示文件大小
    try:
        file_size = os.path.getsize(step2_filename)
        print(f"   📁 step2文件大小: {file_size:,} 字节")
    except:
        pass
    
    return step2_filename

if __name__ == "__main__":
    result_file = complete_react_test()
    if result_file:
        print(f"\n🎊 测试完成! 生成文件: {result_file}")
    else:
        print("\n❌ 测试失败!")
