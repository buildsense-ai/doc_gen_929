"""
验证脚本：检查所有prompt是否正确提取
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def verify_prompts():
    """验证所有prompt是否可以正常导入"""
    print("🔍 开始验证prompt提取...")
    print("=" * 60)
    
    errors = []
    success_count = 0
    
    try:
        # 验证 ReAct Agent prompts
        print("\n📋 验证 ReAct Agent prompts...")
        from Document_Agent.prompts import (
            MULTI_DIMENSIONAL_QUERY_PROMPT,
            WEB_SEARCH_QUERY_PROMPT,
            REACT_REASON_AND_ACT_PROMPT,
            SECTION_RESULTS_QUALITY_PROMPT,
            OVERALL_RAG_QUALITY_PROMPT
        )
        
        prompts = {
            'MULTI_DIMENSIONAL_QUERY_PROMPT': MULTI_DIMENSIONAL_QUERY_PROMPT,
            'WEB_SEARCH_QUERY_PROMPT': WEB_SEARCH_QUERY_PROMPT,
            'REACT_REASON_AND_ACT_PROMPT': REACT_REASON_AND_ACT_PROMPT,
            'SECTION_RESULTS_QUALITY_PROMPT': SECTION_RESULTS_QUALITY_PROMPT,
            'OVERALL_RAG_QUALITY_PROMPT': OVERALL_RAG_QUALITY_PROMPT,
        }
        
        for name, prompt in prompts.items():
            if not prompt or len(prompt.strip()) == 0:
                errors.append(f"❌ {name} 为空")
            else:
                print(f"  ✅ {name}: {len(prompt)} 字符")
                success_count += 1
        
        # 验证 Orchestrator Agent prompts
        print("\n📋 验证 Orchestrator Agent prompts...")
        from Document_Agent.prompts import (
            DOCUMENT_STRUCTURE_PROMPT,
            WRITING_GUIDE_PROMPT
        )
        
        prompts = {
            'DOCUMENT_STRUCTURE_PROMPT': DOCUMENT_STRUCTURE_PROMPT,
            'WRITING_GUIDE_PROMPT': WRITING_GUIDE_PROMPT,
        }
        
        for name, prompt in prompts.items():
            if not prompt or len(prompt.strip()) == 0:
                errors.append(f"❌ {name} 为空")
            else:
                print(f"  ✅ {name}: {len(prompt)} 字符")
                success_count += 1
        
        # 验证 Document Reviewer prompts
        print("\n📋 验证 Document Reviewer prompts...")
        from Document_Agent.prompts import REDUNDANCY_ANALYSIS_PROMPT
        
        if not REDUNDANCY_ANALYSIS_PROMPT or len(REDUNDANCY_ANALYSIS_PROMPT.strip()) == 0:
            errors.append(f"❌ REDUNDANCY_ANALYSIS_PROMPT 为空")
        else:
            print(f"  ✅ REDUNDANCY_ANALYSIS_PROMPT: {len(REDUNDANCY_ANALYSIS_PROMPT)} 字符")
            success_count += 1
        
        # 验证 Regenerate Sections prompts
        print("\n📋 验证 Regenerate Sections prompts...")
        from Document_Agent.prompts import SECTION_MODIFICATION_PROMPT
        
        if not SECTION_MODIFICATION_PROMPT or len(SECTION_MODIFICATION_PROMPT.strip()) == 0:
            errors.append(f"❌ SECTION_MODIFICATION_PROMPT 为空")
        else:
            print(f"  ✅ SECTION_MODIFICATION_PROMPT: {len(SECTION_MODIFICATION_PROMPT)} 字符")
            success_count += 1
        
        # 验证 Content Generator prompts
        print("\n📋 验证 Content Generator prompts...")
        from Document_Agent.prompts import CONTENT_GENERATION_PROMPT
        
        if not CONTENT_GENERATION_PROMPT or len(CONTENT_GENERATION_PROMPT.strip()) == 0:
            errors.append(f"❌ CONTENT_GENERATION_PROMPT 为空")
        else:
            print(f"  ✅ CONTENT_GENERATION_PROMPT: {len(CONTENT_GENERATION_PROMPT)} 字符")
            success_count += 1
        
    except ImportError as e:
        errors.append(f"❌ 导入错误: {e}")
    except Exception as e:
        errors.append(f"❌ 未知错误: {e}")
    
    # 打印结果
    print("\n" + "=" * 60)
    print(f"📊 验证结果:")
    print(f"  ✅ 成功: {success_count} 个")
    print(f"  ❌ 失败: {len(errors)} 个")
    
    if errors:
        print("\n❌ 发现错误:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n🎉 所有prompt验证通过！")
        return True

def check_placeholders():
    """检查prompt中的占位符是否符合规范"""
    print("\n" + "=" * 60)
    print("🔍 检查占位符规范...")
    print("=" * 60)
    
    from Document_Agent.prompts import (
        MULTI_DIMENSIONAL_QUERY_PROMPT,
        WEB_SEARCH_QUERY_PROMPT,
        DOCUMENT_STRUCTURE_PROMPT,
        WRITING_GUIDE_PROMPT,
        REDUNDANCY_ANALYSIS_PROMPT,
        SECTION_MODIFICATION_PROMPT,
        CONTENT_GENERATION_PROMPT
    )
    
    prompts_to_check = {
        'MULTI_DIMENSIONAL_QUERY_PROMPT': {
            'prompt': MULTI_DIMENSIONAL_QUERY_PROMPT,
            'expected_placeholders': ['project_name', 'subtitle', 'how_to_write']
        },
        'WEB_SEARCH_QUERY_PROMPT': {
            'prompt': WEB_SEARCH_QUERY_PROMPT,
            'expected_placeholders': ['project_name', 'subtitle', 'how_to_write', 'rag_summary']
        },
        'DOCUMENT_STRUCTURE_PROMPT': {
            'prompt': DOCUMENT_STRUCTURE_PROMPT,
            'expected_placeholders': ['user_description']
        },
        'WRITING_GUIDE_PROMPT': {
            'prompt': WRITING_GUIDE_PROMPT,
            'expected_placeholders': ['user_description', 'section_title', 'section_goal', 'subtitles_text']
        },
        'REDUNDANCY_ANALYSIS_PROMPT': {
            'prompt': REDUNDANCY_ANALYSIS_PROMPT,
            'expected_placeholders': []  # 使用 $ 格式
        },
        'SECTION_MODIFICATION_PROMPT': {
            'prompt': SECTION_MODIFICATION_PROMPT,
            'expected_placeholders': ['section_title', 'original_content', 'suggestion']
        },
        'CONTENT_GENERATION_PROMPT': {
            'prompt': CONTENT_GENERATION_PROMPT,
            'expected_placeholders': ['subtitle', 'how_to_write', 'retrieved_text_content', 'feedback']
        }
    }
    
    import re
    all_ok = True
    
    for name, config in prompts_to_check.items():
        prompt = config['prompt']
        expected = config['expected_placeholders']
        
        # 查找所有 {xxx} 格式的占位符
        found_placeholders = re.findall(r'\{(\w+)\}', prompt)
        found_placeholders = list(set(found_placeholders))  # 去重
        
        print(f"\n📝 {name}:")
        print(f"  预期占位符: {expected}")
        print(f"  实际占位符: {found_placeholders}")
        
        # 检查是否匹配
        if set(expected) == set(found_placeholders):
            print(f"  ✅ 占位符匹配")
        else:
            missing = set(expected) - set(found_placeholders)
            extra = set(found_placeholders) - set(expected)
            if missing:
                print(f"  ⚠️  缺少: {missing}")
            if extra:
                print(f"  ⚠️  多余: {extra}")
            all_ok = False
    
    if all_ok:
        print("\n🎉 所有占位符检查通过！")
    else:
        print("\n⚠️  部分占位符存在差异，请检查")
    
    return all_ok

def main():
    """主函数"""
    print("🚀 Prompt验证工具")
    
    # 验证基本导入
    basic_ok = verify_prompts()
    
    # 检查占位符
    placeholder_ok = check_placeholders()
    
    # 最终结果
    print("\n" + "=" * 60)
    if basic_ok and placeholder_ok:
        print("✅ 所有检查通过！Prompt提取完全正确。")
        return 0
    else:
        print("❌ 部分检查未通过，请查看上述错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())

