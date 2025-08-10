#!/usr/bin/env python3
"""
基于评估结果重新生成文档章节的脚本

该脚本读取文档质量评估结果，并使用SimpleContentGeneratorAgent
对需要修改的章节进行重新生成。
"""

import json
import logging
import os
import sys
import re
from typing import Dict, List, Any
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from clients.openrouter_client import OpenRouterClient

class DocumentRegenerator:
    """
    文档重新生成器
    
    基于评估结果对文档章节进行重新生成
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 初始化LLM客户端
        self.llm_client = OpenRouterClient()
        
        # 不再需要复杂的内容生成代理
        
    def load_evaluation_results(self, evaluation_file: str) -> List[Dict]:
        """
        加载评估结果文件
        
        Args:
            evaluation_file: 评估结果JSON文件路径
            
        Returns:
            List[Dict]: 评估结果列表
        """
        try:
            with open(evaluation_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查数据格式，提取冗余分析数组
            if isinstance(data, dict) and 'unnecessary_redundancies_analysis' in data:
                results = data['unnecessary_redundancies_analysis']
                # 转换数据格式以适配后续处理
                formatted_results = []
                for item in results:
                    # 从locations数组中获取第一个位置作为主要位置
                    locations = item.get('locations', [])
                    primary_location = locations[0] if locations else item.get('redundant_theme', '未知章节')
                    
                    formatted_item = {
                        'location': primary_location,
                        'suggestion': item.get('suggestion', ''),
                        'evidence': item.get('evidence', []),
                        'count': item.get('count', 1)
                    }
                    formatted_results.append(formatted_item)
                results = formatted_results
            elif isinstance(data, dict) and 'quality_issues' in data:
                results = data['quality_issues']
            elif isinstance(data, list):
                results = data
            else:
                self.logger.error(f"不支持的评估结果格式: {type(data)}")
                return []
            
            self.logger.info(f"成功加载评估结果，共{len(results)}个需要修改的章节")
            return results
        except Exception as e:
            self.logger.error(f"加载评估结果失败: {e}")
            return []
    
    def load_original_document(self, document_file: str) -> str:
        """
        加载原始文档
        
        Args:
            document_file: 原始文档文件路径
            
        Returns:
            str: 文档内容
        """
        try:
            if document_file.endswith('.json'):
                # 处理JSON文档，提取generated_content
                with open(document_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                content_parts = []
                # 处理新的JSON结构：report_guide
                report_guide = json_data.get('report_guide', [])
                total_sections = 0
                
                for part in report_guide:
                    part_title = part.get('title', '')
                    sections = part.get('sections', [])
                    
                    for section in sections:
                        subtitle = section.get('subtitle', '')
                        generated_content = section.get('generated_content', '')
                        if subtitle and generated_content:
                            content_parts.append(f"## {subtitle}\n\n{generated_content}")
                            total_sections += 1
                
                content = "\n\n".join(content_parts)
                self.logger.info(f"成功加载JSON文档: {document_file}，提取了{total_sections}个章节")
                return content
            else:
                # 处理Markdown文档
                with open(document_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.logger.info(f"成功加载Markdown文档: {document_file}")
                return content
        except Exception as e:
            self.logger.error(f"加载原始文档失败: {e}")
            return ""
    
    def extract_section_content(self, document_content: str, section_title: str) -> str:
        """
        从文档中提取指定章节的内容
        
        Args:
            document_content: 完整文档内容
            section_title: 章节标题（如"## 一、项目背景"）
            
        Returns:
            str: 章节内容
        """
        try:
            # 仅匹配以二级标题(H2)开头的章节，避免命中同名的 H1
            pattern = rf"(?m)^\s*##\s*{re.escape(section_title)}\s*$([\s\S]*?)(?=^\s*##\s|\Z)"
            match = re.search(pattern, document_content)
            
            if match:
                # 分组2即为去掉标题后的正文
                content_without_title = (match.group(1) or '').strip()
                return content_without_title
            else:
                self.logger.warning(f"未找到章节: {section_title}")
                return ""
        except Exception as e:
            self.logger.error(f"提取章节内容失败: {e}")
            return ""
    
    def _call_llm_for_modification(self, section_title: str, original_content: str, suggestion: str) -> Dict[str, Any]:
        """
        直接调用大模型进行内容修改
        
        Args:
            section_title: 章节标题
            original_content: 原始章节内容
            suggestion: 修改建议
            
        Returns:
            Dict[str, Any]: 修改结果
        """
        import time
        start_time = time.time()
        
        prompt = f"""你是一位专业的文档编辑，请根据以下要求修改文档章节内容（仅正文）。

【章节标题】：{section_title}

【原始内容】：
{original_content}

【修改建议】：
{suggestion}

【修改要求】：
1. 仅改写“正文”段落；严格忽略任何与图片/表格/媒体相关的内容。
2. 绝对不要输出以下任何内容：
   - “### 相关图片资料”或“相关图片资料”等标题或段落；
   - 以“图片描述:”或“图片来源:”开头的行；
   - 任意 Markdown 图片/链接（如 `![...](...)`、`[...](http...)` 等）；
   - 任何表格（包括以“### 相关表格资料”为标题或以“|”开头的表格行）。
3. 保持专业、客观、严谨的语言风格，确保逻辑清晰、结构合理，避免重复和冗余。
4. 仅输出纯文本正文，不要包含任何Markdown标记、标题（如“#/##/### ...”）或媒体引用。
5. 字数建议控制在800-1200字之间；段落之间用一个空行分隔。

请直接输出修改后的“正文”内容，不要添加任何说明、标题或媒体相关信息："""
        
        try:
            response = self.llm_client.generate(prompt)
            content = response.strip()

            # 强制清洗：移除任何图片/表格/媒体相关内容与Markdown图片/链接
            content = self._sanitize_content_remove_media(content)
            
            generation_time = time.time() - start_time
            
            result = {
                'content': content,
                'quality_score': 0.8,  # 假设修改后质量良好
                'word_count': len(content),
                'generation_time': f"{generation_time:.2f}s",
                'feedback': '内容已根据建议进行修改',
                'subtitle': section_title
            }
            
            self.logger.info(f"章节修改完成: {section_title} ({result['word_count']}字)")
            return result
            
        except Exception as e:
            self.logger.error(f"调用大模型修改内容失败: {e}")
            return {
                'content': f"[修改失败: {str(e)}]",
                'quality_score': 0.0,
                'word_count': 0,
                'generation_time': "0.00s",
                'feedback': f"修改失败: {str(e)}",
                'subtitle': section_title
            }

    def _sanitize_content_remove_media(self, content: str) -> str:
        """
        清洗模型输出，移除图片/表格/媒体相关段落与Markdown标记。
        规则：
        - 删除包含 Markdown 图片的行：![](...)
        - 删除包含链接的行：[text](http...)
        - 删除以“### 相关图片资料”或“相关图片资料”开头的行
        - 删除以“图片描述:”或“图片来源:”开头的行
        - 删除以“### 相关表格资料”开头的行
        - 删除以“|”开头（疑似表格）的行
        - 删除以“#”开头的标题行
        """
        import re

        if not content:
            return content

        cleaned_lines: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()

            # 标题与媒体相关的硬性过滤
            if not stripped:
                cleaned_lines.append(line)
                continue

            # 标题行
            if stripped.startswith('#'):
                continue

            # 表格标题与表格行
            if stripped.startswith('### 相关表格资料'):
                continue
            if stripped.startswith('|'):
                continue

            # 图片标题/段落与图片描述/来源
            if stripped.startswith('### 相关图片资料'):
                continue
            if stripped == '相关图片资料' or stripped.startswith('相关图片资料'):
                continue
            if stripped.startswith('图片描述:') or stripped.startswith('图片来源:'):
                continue

            # Markdown 图片或链接
            if re.search(r'!\[.*?\]\(.*?\)', stripped):
                continue
            if re.search(r'\[[^\]]+\]\(https?://[^\)]+\)', stripped, flags=re.IGNORECASE):
                continue

            cleaned_lines.append(line)

        # 合并并去除可能出现的多余空行堆叠
        cleaned_text = '\n'.join(cleaned_lines)
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
        return cleaned_text
    
    def regenerate_section(self, section_title: str, original_content: str, 
                          suggestion: str, original_json_data: Dict = None) -> Dict[str, Any]:
        """
        重新生成单个章节
        
        Args:
            section_title: 章节标题
            original_content: 原始章节内容
            suggestion: 修改建议
            original_json_data: 原始JSON文档数据（用于提取图片和表格信息）
            
        Returns:
            Dict[str, Any]: 生成结果
        """
        self.logger.info(f"开始重新生成章节: {section_title}")
        
        # 直接调用大模型进行修改
        result = self._call_llm_for_modification(
            section_title=section_title,
            original_content=original_content,
            suggestion=suggestion
        )
        
        return result
    
    def regenerate_document_sections(self, evaluation_file: str, 
                                   document_file: str, 
                                   output_dir: str = None) -> Dict[str, Any]:
        """
        重新生成文档中需要修改的章节
        
        Args:
            evaluation_file: 评估结果文件路径
            document_file: 原始文档文件路径
            output_dir: 输出目录（可选）
            
        Returns:
            Dict[str, Any]: 重新生成的结果
        """
        # 加载评估结果和原始文档
        evaluation_results = self.load_evaluation_results(evaluation_file)
        if not evaluation_results:
            return {'error': '无法加载评估结果'}
        
        document_content = self.load_original_document(document_file)
        if not document_content:
            return {'error': '无法加载原始文档'}
        
        # 尝试加载对应的JSON文档以获取图片和表格信息
        original_json_data = None
        if document_file.endswith('.json'):
            # 如果document_file本身就是JSON文件，直接使用
            json_file = document_file
        else:
            # 如果是Markdown文件，尝试找对应的JSON文件
            json_file = document_file.replace('.md', '.json')
        
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    original_json_data = json.load(f)
                self.logger.info(f"成功加载原始JSON文档: {json_file}")
            except Exception as e:
                self.logger.warning(f"无法加载原始JSON文档 {json_file}: {e}")
        else:
            self.logger.warning(f"未找到对应的JSON文档: {json_file}")
        
        # 重新生成结果
        regeneration_results = {}
        
        for item in evaluation_results:
            # 适配新的评估结果格式，使用 'subtitle' 字段
            section_title = item.get('subtitle', item.get('location', ''))
            suggestion = item.get('suggestion', '')
            
            if not section_title:
                continue
            
            # 提取原始章节内容
            # 优先从 JSON 结构按 subtitle 获取原文；若传入的是 MD 再尝试 H2 抽取
            original_content = ""
            if original_json_data:
                try:
                    for part in original_json_data.get('report_guide', []):
                        for sec in part.get('sections', []):
                            if sec.get('subtitle', '').strip() == section_title.strip():
                                original_content = (sec.get('generated_content') or '').strip()
                                raise StopIteration
                except StopIteration:
                    pass

            if not original_content and document_file.endswith('.md'):
                original_content = self.extract_section_content(document_content, section_title)
            
            # 重新生成章节（传入原始JSON数据）
            result = self.regenerate_section(section_title, original_content, suggestion, original_json_data)
            regeneration_results[section_title] = result
        
        # 保存结果
        if output_dir:
            self._save_regeneration_results(regeneration_results, output_dir)
        
        return regeneration_results
    
    def _save_regeneration_results(self, results: Dict[str, Any], output_dir: str):
        """
        保存重新生成的结果
        
        Args:
            results: 重新生成的结果
            output_dir: 输出目录
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存JSON格式的详细结果
            json_file = os.path.join(output_dir, f"regenerated_sections_{timestamp}.json")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            # 保存Markdown格式的可读结果
            md_file = os.path.join(output_dir, f"regenerated_sections_{timestamp}.md")
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write("# 重新生成的文档章节\n\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for section_title, result in results.items():
                    f.write(f"{section_title}\n\n")
                    content = result.get('content', '[生成失败]')
                    # 如果生成的内容已经包含了标题，则移除重复的标题
                    if content.startswith(section_title):
                        content = content[len(section_title):].strip()
                    f.write(content)
                    f.write("\n\n---\n\n")
                    f.write(f"质量评分: {result.get('quality_score', 0):.2f}\n")
                    f.write(f"字数: {result.get('word_count', 0)}\n")
                    f.write(f"生成时间: {result.get('generation_time', '未知')}\n")
                    if result.get('feedback'):
                        f.write(f"反馈: {result.get('feedback')}\n")
                    f.write("\n\n")
            
            self.logger.info(f"重新生成结果已保存到: {output_dir}")
            
        except Exception as e:
            self.logger.error(f"保存重新生成结果失败: {e}")

def main():
    """
    主函数
    """
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('document_regeneration.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python regenerate_sections.py <质量分析文件路径>")
        print("示例: python regenerate_sections.py complete_demo_outputs/quality_analysis_完整版文档_20250808_172126_20250808_172243.json")
        return
    
    evaluation_file = sys.argv[1]
    
    # 根据质量分析文件路径推断对应的文档文件
    # 从质量分析文件名中提取时间戳
    import re
    match = re.search(r'完整版文档_(\d{8}_\d{6})', evaluation_file)
    if match:
        timestamp = match.group(1)
        document_file = f"完整版文档_{timestamp}.md"
    else:
        # 尝试从其他模式中提取时间戳
        match = re.search(r'生成文档的依据_完成_(\d{8}_\d{6})', evaluation_file)
        if match:
            timestamp = match.group(1)
            document_file = f"生成文档的依据_完成_{timestamp}.json"
        else:
            # 默认使用最新的文档文件
            document_file = "完整版文档_20250808_172126.md"
    
    output_dir = "./regenerated_outputs"
    
    print(f"质量分析文件: {evaluation_file}")
    print(f"对应文档文件: {document_file}")
    print(f"输出目录: {output_dir}")
    
    # 创建重新生成器
    regenerator = DocumentRegenerator()
    
    # 执行重新生成
    print("开始重新生成文档章节...")
    results = regenerator.regenerate_document_sections(
        evaluation_file=evaluation_file,
        document_file=document_file,
        output_dir=output_dir
    )
    
    if 'error' in results:
        print(f"重新生成失败: {results['error']}")
        return
    
    print(f"\n重新生成完成！共处理 {len(results)} 个章节")
    
    # 显示结果摘要
    for section_title, result in results.items():
        print(f"\n章节: {section_title}")
        print(f"  质量评分: {result.get('quality_score', 0):.2f}")
        print(f"  字数: {result.get('word_count', 0)}")
        print(f"  生成时间: {result.get('generation_time', '未知')}")
        if result.get('feedback'):
            print(f"  反馈: {result.get('feedback')[:100]}...")

if __name__ == "__main__":
    main()