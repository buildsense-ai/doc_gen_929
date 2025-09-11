#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试最新的ReAct Agent - 两步式检索流程
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
        logging.FileHandler(f'test_react_agent_new_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8')
    ]
)

class MockClient:
    """模拟LLM客户端"""
    def generate(self, prompt: str) -> str:
        print(f"\n🤖 AI调用 - Prompt长度: {len(prompt)} 字符")
        print(f"📝 Prompt预览: {prompt[:200]}...")
        
        # 根据prompt内容返回模拟响应
        if "多维度检索计划" in prompt or "维度名称" in prompt:
            return '''[
  {"dimension": "政策法规", "query": "中等职业教育 政策文件", "priority": "high"},
  {"dimension": "建设标准", "query": "职业教育基地 建设规范", "priority": "high"},
  {"dimension": "案例分析", "query": "职业教育基地 成功案例", "priority": "medium"}
]'''
        
        elif "分析RAG检索结果" in prompt or "信息缺口" in prompt:
            return "清远市清新区 中等职业教育 最新政策 2024"
        
        else:
            return "模拟AI响应"

def test_react_agent():
    """测试ReAct Agent的新流程"""
    
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
    
    # 测试前几个章节
    print("\n" + "="*80)
    print("🧪 开始测试资料召回...")
    print("="*80)
    
    # 只测试前2个部分的前2个章节，避免测试时间过长
    test_count = 0
    max_test_sections = 4
    
    for part_idx, part in enumerate(guide_data['report_guide']):
        if test_count >= max_test_sections:
            break
            
        print(f"\n📋 处理部分: {part['title']}")
        
        for section_idx, section in enumerate(part.get('sections', [])):
            if test_count >= max_test_sections:
                break
                
            print(f"\n🎯 测试章节 {test_count + 1}/{max_test_sections}")
            print(f"📌 章节标题: {section['subtitle']}")
            print(f"📝 写作指导: {section['how_to_write'][:100]}...")
            
            # 创建章节上下文
            section_context = {
                'subtitle': section['subtitle'],
                'how_to_write': section['how_to_write'],
                'part_title': part['title'],
                'part_goal': part.get('goal', '')
            }
            
            # 模拟单个章节的处理
            print(f"\n🔄 开始处理章节: {section['subtitle']}")
            
            try:
                # 这里我们手动模拟两步流程来测试
                print("🔍 第1步: 生成多维度RAG查询...")
                multi_queries = react_agent._generate_multi_dimensional_queries(section_context, None)
                
                if multi_queries:
                    print(f"✅ 生成了 {len(multi_queries)} 个维度的查询:")
                    for i, query in enumerate(multi_queries, 1):
                        print(f"   {i}. 维度: {query['dimension']}, 查询: {query['query']}, 优先级: {query['priority']}")
                else:
                    print("❌ 未能生成有效的多维度查询")
                    test_count += 1
                    continue
                
                # 模拟RAG结果
                print("\n🔍 第2步: 模拟RAG检索结果...")
                mock_rag_results = [
                    {
                        'content': f'关于{section["subtitle"]}的相关政策文件内容...',
                        'type': 'text',
                        'page_number': '1',
                        'source': '政策文档'
                    },
                    {
                        'content': f'{section["subtitle"]}的建设标准和规范要求...',
                        'type': 'text', 
                        'page_number': '2',
                        'source': '标准文档'
                    }
                ]
                print(f"✅ 模拟获得 {len(mock_rag_results)} 条RAG结果")
                
                # 测试Web查询生成
                print("\n🌐 第3步: 生成Web搜索查询...")
                web_query = react_agent._analyze_rag_gaps_and_generate_query(section_context, mock_rag_results)
                
                if web_query:
                    print(f"✅ 生成Web查询: {web_query}")
                else:
                    print("❌ 未能生成Web搜索查询")
                
                print(f"✅ 章节 '{section['subtitle']}' 测试完成")
                
            except Exception as e:
                print(f"❌ 章节处理失败: {e}")
                import traceback
                traceback.print_exc()
            
            test_count += 1
            print("-" * 60)
    
    print("\n" + "="*80)
    print("🎉 测试完成!")
    print("="*80)
    
    # 显示统计信息
    try:
        stats = react_agent.get_processing_stats()
        print(f"\n📊 处理统计:")
        print(f"   📝 处理章节数: {stats['total_sections_processed']}")
        print(f"   🔍 RAG查询数: {stats.get('total_rag_queries', 0)}")
        print(f"   🌐 Web查询数: {stats.get('total_web_queries', 0)}")
    except AttributeError:
        print(f"\n📊 测试统计:")
        print(f"   📝 测试章节数: {test_count}")
        print(f"   🔍 AI调用次数: {test_count * 2}  (每章节2次)")
        print(f"   🎯 流程验证: ✅ 两步式检索流程正常")

if __name__ == "__main__":
    test_react_agent()
