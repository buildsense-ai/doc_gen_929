#!/usr/bin/env python3
"""
验证所有 prompt 导入是否正常
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

def verify_prompts():
    """验证所有 prompt 是否可以正常导入"""
    print("=" * 60)
    print("验证 Document_Agent Prompt 导入")
    print("=" * 60)
    
    try:
        # 导入所有 prompt（只导入活跃的 prompt，废弃的已移除）
        from Document_Agent.prompts import (
            # ReAct Agent
            MULTI_DIMENSIONAL_QUERY_PROMPT,
            WEB_SEARCH_QUERY_PROMPT,
            # Orchestrator Agent
            DOCUMENT_STRUCTURE_PROMPT,
            WRITING_GUIDE_PROMPT,
            # Document Reviewer
            REDUNDANCY_ANALYSIS_PROMPT,
            # Regenerate Sections
            SECTION_MODIFICATION_PROMPT,
            # Content Generator
            CONTENT_GENERATION_PROMPT,
        )
        
        prompts = {
            'ReAct Agent': [
                ('MULTI_DIMENSIONAL_QUERY_PROMPT', MULTI_DIMENSIONAL_QUERY_PROMPT),
                ('WEB_SEARCH_QUERY_PROMPT', WEB_SEARCH_QUERY_PROMPT),
            ],
            'Orchestrator Agent': [
                ('DOCUMENT_STRUCTURE_PROMPT', DOCUMENT_STRUCTURE_PROMPT),
                ('WRITING_GUIDE_PROMPT', WRITING_GUIDE_PROMPT),
            ],
            'Document Reviewer': [
                ('REDUNDANCY_ANALYSIS_PROMPT', REDUNDANCY_ANALYSIS_PROMPT),
            ],
            'Regenerate Sections': [
                ('SECTION_MODIFICATION_PROMPT', SECTION_MODIFICATION_PROMPT),
            ],
            'Content Generator': [
                ('CONTENT_GENERATION_PROMPT', CONTENT_GENERATION_PROMPT),
            ],
        }
        
        print("\n✅ 所有 prompt 导入成功！\n")
        
        total_count = 0
        for category, prompt_list in prompts.items():
            print(f"\n【{category}】")
            for name, prompt in prompt_list:
                length = len(prompt.strip())
                print(f"  ✓ {name:40s} ({length:5d} 字符)")
                total_count += 1
        
        print("\n" + "=" * 60)
        print(f"总计: {total_count} 个 prompt 模板")
        print("=" * 60)
        
        # 验证占位符
        print("\n\n验证占位符格式:")
        print("-" * 60)
        
        placeholder_checks = {
            'MULTI_DIMENSIONAL_QUERY_PROMPT': ['project_name', 'subtitle', 'how_to_write'],
            'WEB_SEARCH_QUERY_PROMPT': ['project_name', 'subtitle', 'how_to_write', 'rag_summary'],
            'DOCUMENT_STRUCTURE_PROMPT': ['user_description'],
            'WRITING_GUIDE_PROMPT': ['user_description', 'section_title', 'section_goal', 'subtitles_text'],
            'SECTION_MODIFICATION_PROMPT': ['section_title', 'original_content', 'suggestion'],
            'CONTENT_GENERATION_PROMPT': ['subtitle', 'how_to_write', 'retrieved_text_content', 'feedback'],
        }
        
        all_valid = True
        for prompt_name, expected_placeholders in placeholder_checks.items():
            prompt_text = locals()[prompt_name]
            missing = []
            for placeholder in expected_placeholders:
                if f'{{{placeholder}}}' not in prompt_text:
                    missing.append(placeholder)
            
            if missing:
                print(f"  ❌ {prompt_name}: 缺少占位符 {missing}")
                all_valid = False
            else:
                print(f"  ✓ {prompt_name}: 所有占位符正确")
        
        if all_valid:
            print("\n✅ 所有占位符验证通过！")
        else:
            print("\n⚠️ 部分占位符验证失败，请检查！")
        
        print("\n" + "=" * 60)
        print("验证完成！")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_prompts()
    sys.exit(0 if success else 1)

