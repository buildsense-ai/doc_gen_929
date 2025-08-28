#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON文档合并器
在JSON层面进行章节替换，然后转换为Markdown格式，确保文档结构不变
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# 添加路径以导入main_generator
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'content_generator_agent'))
from main_generator import EnhancedMainDocumentGenerator

class JSONDocumentMerger:
    def __init__(self, original_json_path: str, regenerated_json_path: str):
        """
        初始化JSON文档合并器
        
        Args:
            original_json_path: 原始JSON文档路径
            regenerated_json_path: 重新生成的章节JSON路径
        """
        self.original_json_path = original_json_path
        self.regenerated_json_path = regenerated_json_path
        self.original_data = {}
        self.regenerated_sections = {}
        
    def load_original_json(self):
        """加载原始JSON文档"""
        try:
            with open(self.original_json_path, 'r', encoding='utf-8') as f:
                self.original_data = json.load(f)
            print(f"✓ 成功加载原始JSON文档: {self.original_json_path}")
        except Exception as e:
            print(f"✗ 加载原始JSON文档失败: {e}")
            raise
    
    def load_regenerated_sections(self):
        """加载重新生成的章节"""
        try:
            with open(self.regenerated_json_path, 'r', encoding='utf-8') as f:
                self.regenerated_sections = json.load(f)
            print(f"✓ 成功加载重新生成的章节: {len(self.regenerated_sections)} 个章节")
            for section_title in self.regenerated_sections.keys():
                print(f"  - {section_title}")
        except Exception as e:
            print(f"✗ 加载重新生成章节失败: {e}")
            raise
    
    def find_section_in_json(self, section_title: str):
        """
        在JSON结构中找到对应的章节
        
        Args:
            section_title: 章节标题
            
        Returns:
            tuple: (title_section_index, section_index) 或 (None, None)
        """
        # 清理章节标题
        clean_title = section_title.replace("##", "").strip()
        
        report_guide = self.original_data.get('report_guide', [])

        def walk_sections(parent_index: int, sections: List[Dict[str, Any]], path: List[int]) -> Optional[Tuple[int, List[int]]]:
            for idx, sec in enumerate(sections):
                subtitle = sec.get('subtitle', '').strip()
                if subtitle == clean_title:
                    print(f"✓ 在JSON中找到章节: {clean_title} (位置: part={parent_index}, path={path + [idx]})")
                    return parent_index, path + [idx]
                # 递归查找子节点
                if sec.get('subsections'):
                    found = walk_sections(parent_index, sec.get('subsections', []), path + [idx])
                    if found is not None:
                        return found
            return None

        for title_idx, title_section in enumerate(report_guide):
            sections = title_section.get('sections', [])
            found = walk_sections(title_idx, sections, [])
            if found is not None:
                return found
        
        print(f"⚠ 在JSON中未找到章节: {clean_title}")
        return None, None
    
    def merge_json_documents(self) -> Dict[str, Any]:
        """
        在JSON层面合并文档
        
        Returns:
            合并后的JSON数据
        """
        print("\n开始在JSON层面合并文档...")
        
        # 深拷贝原始数据
        merged_data = json.loads(json.dumps(self.original_data))
        
        replaced_count = 0
        
        for section_title, section_data in self.regenerated_sections.items():
            title_idx, index_path = self.find_section_in_json(section_title)

            if title_idx is not None and index_path is not None:
                # 获取原始章节数据（根据路径深入）
                original_section = merged_data['report_guide'][title_idx]
                current = original_section.get('sections', [])
                for depth, idx in enumerate(index_path):
                    target = current[idx]
                    if depth == len(index_path) - 1:
                        original_section = target
                    else:
                        current = target.get('subsections', [])
                
                # 更新章节内容，保留原有的其他字段（包括图片和表格信息）
                content = section_data['content']
                
                # 检查并移除重复的标题（支持任意级别#）
                subtitle = original_section.get('subtitle', '')
                first_line = content.strip().split('\n', 1)[0].strip()
                import re as _re
                header_pattern = _re.compile(rf"^\s*#{{1,6}}\s*{_re.escape(subtitle)}\s*$")
                if header_pattern.match(first_line):
                    parts = content.split('\n', 1)
                    content = parts[1].lstrip() if len(parts) > 1 else ''
                elif first_line == subtitle:
                    parts = content.split('\n', 1)
                    content = parts[1].lstrip() if len(parts) > 1 else ''
                
                # 只更新生成的内容，保留原始的retrieved_image和retrieved_table等字段
                original_section['generated_content'] = content
                original_section['quality_score'] = section_data.get('quality_score', 0.0)
                original_section['word_count'] = section_data.get('word_count', 0)
                original_section['generation_time'] = section_data.get('generation_time', '')
                
                # 添加替换标记
                original_section['regenerated'] = True
                original_section['regeneration_timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 确保保留原始的图片和表格信息
                # retrieved_image 和 retrieved_table 字段会自动保留，因为我们只更新了特定字段
                
                print(f"✓ 替换章节: {section_title}")
                replaced_count += 1
            else:
                print(f"⚠ 跳过未找到的章节: {section_title}")
        
        print(f"\n✓ JSON合并完成，共替换了 {replaced_count} 个章节")
        return merged_data
    
    def save_merged_json(self, merged_data: Dict[str, Any], output_path: str = None) -> str:
        """
        保存合并后的JSON文档
        
        Args:
            merged_data: 合并后的JSON数据
            output_path: 输出路径
            
        Returns:
            保存的文件路径
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(self.original_json_path))[0]
            output_path = f"merged_{base_name}_{timestamp}.json"
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 成功保存合并后的JSON文档: {output_path}")
            return output_path
        except Exception as e:
            print(f"✗ 保存合并JSON文档失败: {e}")
            raise
    
    def convert_to_markdown(self, merged_data: Dict[str, Any], output_path: str = None) -> str:
        """
        将合并后的JSON转换为Markdown格式
        
        Args:
            merged_data: 合并后的JSON数据
            output_path: 输出路径
            
        Returns:
            保存的Markdown文件路径
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(self.original_json_path))[0]
            output_path = f"merged_{base_name}_{timestamp}.md"
        
        try:
            # 创建临时生成器实例来使用转换方法
            generator = EnhancedMainDocumentGenerator()
            markdown_content = generator._convert_to_markdown(merged_data)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"✓ 成功生成Markdown文档: {output_path}")
            return output_path
        except Exception as e:
            print(f"✗ 转换为Markdown失败: {e}")
            raise
    
    def generate_summary_report(self, json_output_path: str, md_output_path: str):
        """
        生成合并摘要报告
        
        Args:
            json_output_path: JSON输出文件路径
            md_output_path: Markdown输出文件路径
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        summary = f"""# JSON文档合并摘要报告

**生成时间**: {timestamp}
**原始JSON文档**: {self.original_json_path}
**重新生成章节数据**: {self.regenerated_json_path}
**输出JSON文档**: {json_output_path}
**输出Markdown文档**: {md_output_path}

## 替换的章节

"""
        
        for i, (section_title, section_data) in enumerate(self.regenerated_sections.items(), 1):
            # 检查section_data的类型，确保是字典
            if isinstance(section_data, dict):
                quality_score = section_data.get('quality_score', 'N/A')
                word_count = section_data.get('word_count', 'N/A')
                generation_time = section_data.get('generation_time', 'N/A')
            else:
                # 如果是字符串或其他类型，使用默认值
                quality_score = 'N/A'
                word_count = 'N/A'
                generation_time = 'N/A'
            
            summary += f"""{i}. **{section_title}**
   - 质量评分: {quality_score}
   - 字数: {word_count}
   - 生成时间: {generation_time}

"""
        
        summary += "\n## 合并说明\n\n"
        summary += "本次合并采用JSON层面的章节替换策略，确保文档结构完全保持不变。\n"
        summary += "重新生成的章节已在JSON结构中替换，然后使用原始转换逻辑生成Markdown文档。\n"
        summary += "这种方法避免了直接在Markdown文件中替换可能导致的结构变化问题。\n"
        
        summary_path = md_output_path.replace('.md', '_summary.md')
        
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"✓ 成功生成合并摘要报告: {summary_path}")
        except Exception as e:
            print(f"✗ 生成摘要报告失败: {e}")

def update_json_sections_inplace(target_json_path: str, regenerated_json_path: str) -> bool:
    """
    直接更新目标JSON文件中指定章节的generated_content字段
    
    Args:
        target_json_path: 目标JSON文件路径
        regenerated_json_path: 重新生成的章节JSON路径
        
    Returns:
        bool: 更新是否成功
    """
    print(f"=== 直接更新JSON文件中的章节内容 ===")
    print(f"目标JSON文件: {target_json_path}")
    print(f"重新生成的章节: {regenerated_json_path}")
    print()
    
    try:
        # 加载目标JSON文件
        with open(target_json_path, 'r', encoding='utf-8') as f:
            target_data = json.load(f)
        print(f"✓ 成功加载目标JSON文件")
        
        # 加载重新生成的章节
        with open(regenerated_json_path, 'r', encoding='utf-8') as f:
            regenerated_sections = json.load(f)
        print(f"✓ 成功加载重新生成的章节: {len(regenerated_sections)} 个章节")
        
        updated_count = 0
        
        # 遍历重新生成的章节
        for section_title, section_data in regenerated_sections.items():
            # 清理章节标题
            clean_title = section_title.replace("##", "").strip()
            
            # 在目标JSON中查找对应章节
            found = False
            report_guide = target_data.get('report_guide', [])
            
            for title_idx, title_section in enumerate(report_guide):
                sections = title_section.get('sections', [])
                for section_idx, section in enumerate(sections):
                    subtitle = section.get('subtitle', '').strip()
                    if subtitle == clean_title:
                        # 找到匹配的章节，更新generated_content
                        content = section_data['content']
                        
                        # 检查并移除重复的标题
                        if content.strip().startswith(f"## {subtitle}"):
                            lines = content.split('\n')
                            if lines and lines[0].strip() == f"## {subtitle}":
                                content = '\n'.join(lines[1:]).strip()
                        elif content.strip().startswith(subtitle):
                            if content.strip().split('\n')[0].strip() == subtitle:
                                lines = content.split('\n')
                                content = '\n'.join(lines[1:]).strip()
                        
                        # 更新章节内容，保留其他字段
                        section['generated_content'] = content
                        section['quality_score'] = section_data.get('quality_score', 0.0)
                        section['word_count'] = section_data.get('word_count', 0)
                        section['generation_time'] = section_data.get('generation_time', '')
                        section['regenerated'] = True
                        section['regeneration_timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        print(f"✓ 更新章节: {clean_title}")
                        updated_count += 1
                        found = True
                        break
                if found:
                    break
            
            if not found:
                print(f"⚠ 未找到章节: {clean_title}")
        
        # 保存更新后的JSON文件
        with open(target_json_path, 'w', encoding='utf-8') as f:
            json.dump(target_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ 成功更新JSON文件，共更新了 {updated_count} 个章节")
        print(f"✓ 已保存到: {target_json_path}")
        
        return True
        
    except Exception as e:
        print(f"✗ 更新JSON文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """
    主函数
    """
    # 文件路径
    original_json_path = r"c:\Users\heyyy\Desktop\Gauz文档Agent\生成文档的依据_完成_20250808_172126.json"
    regenerated_json_path = r"C:\Users\heyyy\Desktop\Gauz文档Agent\Document_Agent\final_review_agent\regenerated_outputs\regenerated_sections_20250808_151212.json"
    
    print("=== JSON文档合并工具 ===")
    print(f"原始JSON文档: {original_json_path}")
    print(f"重新生成的章节: {regenerated_json_path}")
    print()
    
    try:
        # 创建合并器
        merger = JSONDocumentMerger(original_json_path, regenerated_json_path)
        
        # 加载文件
        merger.load_original_json()
        merger.load_regenerated_sections()
        
        # 在JSON层面合并文档
        merged_data = merger.merge_json_documents()
        
        # 保存合并后的JSON
        json_output_path = merger.save_merged_json(merged_data)
        
        # 转换为Markdown
        md_output_path = merger.convert_to_markdown(merged_data)
        
        # 生成摘要报告
        merger.generate_summary_report(json_output_path, md_output_path)
        
        print("\n=== 合并完成 ===")
        print(f"✓ 已生成完整的微调后文档（JSON层面合并）")
        print(f"✓ 共替换了 {len(merger.regenerated_sections)} 个章节")
        print(f"✓ JSON文档: {json_output_path}")
        print(f"✓ Markdown文档: {md_output_path}")
        
    except Exception as e:
        print(f"\n✗ 合并过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())