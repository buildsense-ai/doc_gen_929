"""
检查提示词模板

直接检查提示词模板是否有问题。
"""

import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Document_Agent.final_review_agent.document_reviewer import DocumentReviewer


def check_prompt_template():
    """检查提示词模板"""
    print("🔍 检查提示词模板...")
    
    try:
        # 创建评估器
        reviewer = DocumentReviewer()
        
        # 检查提示词模板
        prompt_template = reviewer.redundancy_analysis_prompt
        print(f"提示词模板长度: {len(prompt_template)} 字符")
        
        # 检查是否包含占位符
        if 'DOCUMENT_CONTENT_PLACEHOLDER' in prompt_template:
            print("✅ 找到占位符: DOCUMENT_CONTENT_PLACEHOLDER")
        else:
            print("❌ 未找到占位符")
        
        # 检查是否包含大括号
        brace_count = prompt_template.count('{')
        print(f"大括号数量: {brace_count}")
        
        # 尝试简单的替换
        test_content = "测试文档内容"
        try:
            result = prompt_template.replace('DOCUMENT_CONTENT_PLACEHOLDER', test_content)
            print("✅ 替换成功")
            print(f"替换后长度: {len(result)} 字符")
        except Exception as e:
            print(f"❌ 替换失败: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🚀 开始检查提示词模板...")
    
    success = check_prompt_template()
    
    if success:
        print("\n🎉 提示词模板检查完成！")
    else:
        print("\n⚠️ 提示词模板检查失败！")


if __name__ == "__main__":
    main() 