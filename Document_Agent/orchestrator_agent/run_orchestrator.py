#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OrchestratorAgent 启动文件

快速启动和测试重构后的两步式文档生成系统
"""

import sys
import os
import json
import time
from datetime import datetime

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

# SimpleRAGClient已移除，OrchestratorAgent现在使用外部API
from clients.openrouter_client import OpenRouterClient
from agents.orchestrator_agent.agent import OrchestratorAgent
from config.settings import setup_logging


def create_orchestrator():
    """创建OrchestratorAgent实例"""
    print("🔧 初始化系统组件...")
    
    # 设置日志系统
    setup_logging()
    
    try:
        # rag_client = SimpleRAGClient()  # 已移除，使用外部API
        llm_client = OpenRouterClient()
        orchestrator = OrchestratorAgent(llm_client)  # 不再需要rag_client参数
        
        print("✅ 系统初始化成功！")
        return orchestrator
        
    except Exception as e:
        print(f"❌ 系统初始化失败: {e}")
        return None


def test_step_by_step(orchestrator, user_description):
    """测试两步式生成"""
    
    print("\n" + "=" * 60)
    print("🚀 两步式文档生成测试")
    print("=" * 60)
    
    print(f"📝 用户需求：\n{user_description.strip()}")
    
    # 第一步：生成基础结构
    print(f"\n🔥 第一步：生成文档基础结构...")
    start_time = time.time()
    
    try:
        structure = orchestrator.generate_document_structure(user_description)
        step1_time = time.time() - start_time
        
        print(f"✅ 基础结构生成完成！耗时：{step1_time:.1f}秒")
        
        # 统计信息
        sections_count = len(structure.get('report_guide', []))
        subsections_count = sum(len(s.get('sections', [])) for s in structure.get('report_guide', []))
        
        print(f"📊 生成了 {sections_count} 个主要章节，{subsections_count} 个子章节")
        
        # 显示结构预览
        print(f"\n📋 结构预览：")
        for i, section in enumerate(structure.get('report_guide', []), 1):
            print(f"  {i}. {section.get('title', '')}")
            print(f"     目标：{section.get('goal', '')}")
            for j, subsection in enumerate(section.get('sections', []), 1):
                print(f"     {j}) {subsection.get('subtitle', '')}")
        
        # 保存第一步结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        step1_file = f"step1_structure_{timestamp}.json"
        with open(step1_file, 'w', encoding='utf-8') as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        print(f"💾 第一步结果保存到：{step1_file}")
        
    except Exception as e:
        print(f"❌ 第一步失败：{e}")
        return None
    
    # 第二步：添加写作指导
    print(f"\n🔥 第二步：为 {subsections_count} 个子章节添加写作指导...")
    start_time = time.time()
    
    try:
        complete_guide = orchestrator.add_writing_guides(structure, user_description)
        step2_time = time.time() - start_time
        
        print(f"✅ 写作指导添加完成！耗时：{step2_time:.1f}秒")
        
        # 验证写作指导
        with_how_to_write = 0
        for section in complete_guide.get('report_guide', []):
            for subsection in section.get('sections', []):
                if 'how_to_write' in subsection and subsection['how_to_write']:
                    with_how_to_write += 1
        
        print(f"📊 成功为 {with_how_to_write}/{subsections_count} 个子章节生成了写作指导")
        print(f"📊 成功率：{with_how_to_write/subsections_count*100:.1f}%")
        
        # 显示写作指导示例
        print(f"\n📝 写作指导示例：")
        count = 0
        for section in complete_guide.get('report_guide', []):
            for subsection in section.get('sections', []):
                if count < 3:  # 显示前3个
                    subtitle = subsection.get('subtitle', '')
                    how_to_write = subsection.get('how_to_write', '')
                    print(f"\n  📌 {subtitle}:")
                    preview = how_to_write[:150] + "..." if len(how_to_write) > 150 else how_to_write
                    print(f"     {preview}")
                    count += 1
        
        # 保存完整结果
        complete_file = f"complete_guide_{timestamp}.json"
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(complete_guide, f, ensure_ascii=False, indent=2)
        print(f"💾 完整指导保存到：{complete_file}")
        
        # 总结
        total_time = step1_time + step2_time
        print(f"\n🎉 两步式生成完成！")
        print(f"⏱️  总耗时：{total_time:.1f}秒")
        print(f"   - 第一步（结构生成）：{step1_time:.1f}秒")
        print(f"   - 第二步（写作指导）：{step2_time:.1f}秒")
        
        return complete_guide
        
    except Exception as e:
        print(f"❌ 第二步失败：{e}")
        return None


def test_complete_workflow(orchestrator, user_description):
    """测试一次性完整工作流程"""
    
    print(f"\n" + "=" * 60)
    print("🚀 一次性完整工作流程测试")
    print("=" * 60)
    
    print(f"🔥 使用 generate_complete_guide() 一次性生成...")
    start_time = time.time()
    
    try:
        complete_guide = orchestrator.generate_complete_guide(user_description)
        total_time = time.time() - start_time
        
        # 统计信息
        sections_count = len(complete_guide.get('report_guide', []))
        subsections_count = sum(len(s.get('sections', [])) for s in complete_guide.get('report_guide', []))
        
        print(f"✅ 一次性生成完成！耗时：{total_time:.1f}秒")
        print(f"📊 生成了 {sections_count} 个章节，{subsections_count} 个子章节")
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow_file = f"workflow_result_{timestamp}.json"
        with open(workflow_file, 'w', encoding='utf-8') as f:
            json.dump(complete_guide, f, ensure_ascii=False, indent=2)
        print(f"💾 结果保存到：{workflow_file}")
        
        return complete_guide
        
    except Exception as e:
        print(f"❌ 完整工作流程失败：{e}")
        return None


def interactive_mode(orchestrator):
    """交互模式"""
    
    print(f"\n🎮 进入交互模式")
    print("输入你的文档需求，系统将为你生成编写指导")
    print("输入 'quit' 退出")
    
    while True:
        print(f"\n" + "-" * 50)
        user_input = input("📝 请描述你需要编写的文档：").strip()
        
        if user_input.lower() in ['quit', 'exit', '退出']:
            print("👋 再见！")
            break
            
        if not user_input:
            print("❌ 请输入有效的文档描述")
            continue
        
        # 运行生成
        result = test_step_by_step(orchestrator, user_input)
        
        if result:
            print(f"\n✅ 生成完成！请查看生成的JSON文件。")
        else:
            print(f"\n❌ 生成失败，请重试。")


def main():
    """主函数"""
    
    print("=" * 60)
    print("🎯 OrchestratorAgent 启动器")
    print("重构后的两步式文档生成系统")
    print("=" * 60)
    
    # 初始化系统
    orchestrator = create_orchestrator()
    if not orchestrator:
        return
    
    # 预设测试用例
    test_cases = [
        {
            "name": "文物影响评估报告",
            "description": """
我需要为"白云区鹤边一社吉祥街二巷1号社文体活动中心项目"编写一份文物影响评估报告。

项目情况：
- 原址为一栋两层砖混结构的知青楼，建于1980年代，目前已有安全隐患
- 计划拆除重建为新的社文体活动中心，建筑面积473.6平方米，高度8.8米
- 项目距离白云区登记保护文物单位"医灵古庙"仅6米
- 医灵古庙始建于清雍正二十年（1724年），为三路三开间二进式建筑
- 需要评估新建项目对文物的各种影响，包括风貌、视线、结构安全等

这份报告将提交给文物管理部门审批，需要专业、严谨、符合法规要求。
            """
        },
        {
            "name": "环境影响评估报告",
            "description": """
需要编写城市中心30层综合办公楼建设项目的环境影响评估报告。

项目涉及：
- 交通影响分析
- 噪音污染评估
- 空气质量影响
- 水土保持方案
- 生态环境保护措施
            """
        }
    ]
    
    # 选择模式
    print(f"\n请选择运行模式：")
    print("1. 预设测试用例")
    print("2. 交互模式")
    print("3. 退出")
    
    choice = input("\n请选择 (1/2/3): ").strip()
    
    if choice == "1":
        # 预设测试
        print(f"\n可用的测试用例：")
        for i, case in enumerate(test_cases, 1):
            print(f"{i}. {case['name']}")
        
        test_choice = input(f"\n请选择测试用例 (1-{len(test_cases)}): ").strip()
        
        try:
            case_index = int(test_choice) - 1
            if 0 <= case_index < len(test_cases):
                selected_case = test_cases[case_index]
                print(f"\n🎯 运行测试用例：{selected_case['name']}")
                
                # 运行两步式测试
                test_step_by_step(orchestrator, selected_case['description'])
                
                # 可选：运行完整工作流程
                run_workflow = input(f"\n是否同时测试一次性工作流程？(y/n): ").strip().lower()
                if run_workflow in ['y', 'yes', '是']:
                    test_complete_workflow(orchestrator, selected_case['description'])
                    
            else:
                print("❌ 无效的选择")
        except ValueError:
            print("❌ 请输入有效的数字")
            
    elif choice == "2":
        # 交互模式
        interactive_mode(orchestrator)
        
    elif choice == "3":
        print("👋 再见！")
        
    else:
        print("❌ 无效的选择")


if __name__ == "__main__":
    main() 