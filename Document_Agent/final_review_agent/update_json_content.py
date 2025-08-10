#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接更新JSON文件中的章节内容
根据重新生成的章节内容，直接替换目标JSON文件中对应章节的generated_content字段
"""

import os
import sys
from json_merger import update_json_sections_inplace

def main():
    """
    主函数：直接更新JSON文件中的章节内容
    """
    # 目标JSON文件路径
    target_json_path = r"c:\Users\heyyy\Desktop\Gauz文档Agent\生成文档的依据_完成_20250808_182026.json"
    
    # 重新生成的章节JSON路径
    regenerated_json_path = r"c:\Users\heyyy\Desktop\Gauz文档Agent\Document_Agent\final_review_agent\regenerated_outputs\regenerated_sections_20250808_151212.json"
    
    print("=== 直接更新JSON文件章节内容工具 ===")
    print(f"目标JSON文件: {target_json_path}")
    print(f"重新生成的章节: {regenerated_json_path}")
    print()
    
    # 检查文件是否存在
    if not os.path.exists(target_json_path):
        print(f"✗ 目标JSON文件不存在: {target_json_path}")
        return 1
    
    if not os.path.exists(regenerated_json_path):
        print(f"✗ 重新生成的章节文件不存在: {regenerated_json_path}")
        return 1
    
    # 执行更新
    success = update_json_sections_inplace(target_json_path, regenerated_json_path)
    
    if success:
        print("\n=== 更新完成 ===")
        print("✓ 已成功更新JSON文件中的章节内容")
        print("✓ 原始的图片和表格信息已保留")
        print("✓ 只有generated_content字段被替换")
        print("\n现在您可以使用更新后的JSON文件重新生成Markdown文档")
        return 0
    else:
        print("\n=== 更新失败 ===")
        print("✗ 更新过程中发生错误，请检查日志信息")
        return 1

if __name__ == "__main__":
    exit(main())