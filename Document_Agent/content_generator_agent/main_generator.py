#!/usr/bin/env python3
"""
简化文档生成器 - 主程序（智能速率控制增强版）

功能：
- 读取JSON文件（生成文档的依据.json）
- 集成高级智能速率控制系统
- 只生成正文内容（不包含标题）
- 输出完整版markdown文档（无首行缩进）
- 实时性能监控和优化建议
"""

import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Tuple
from datetime import datetime
import logging

# 确保可以导入模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Document_Agent.content_generator_agent.simple_agent import SimpleContentGeneratorAgent
from clients.openrouter_client import OpenRouterClient
from config.settings import setup_logging, get_concurrency_manager, SmartConcurrencyManager


class EnhancedMainDocumentGenerator:
    """主文档生成器 - 集成智能速率控制系统"""
    
    def __init__(self, concurrency_manager: SmartConcurrencyManager = None):
        # 设置日志
        setup_logging()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 初始化LLM客户端和Agent
        self.llm_client = OpenRouterClient()
        self.agent = SimpleContentGeneratorAgent(self.llm_client)
        
        # 智能并发管理器
        self.concurrency_manager = concurrency_manager or get_concurrency_manager()
        self.max_workers = self.concurrency_manager.get_max_workers('content_generator_agent')
        
        # 智能速率控制器
        self.rate_limiter = self.concurrency_manager.get_rate_limiter('content_generator_agent')
        self.has_smart_control = self.concurrency_manager.has_smart_rate_control('content_generator_agent')
        
        # 兼容性：保留传统速率控制作为后备
        self.rate_limit_delay = self.concurrency_manager.get_rate_limit_delay('content_generator_agent')
        self.last_request_time = 0
        self.request_lock = threading.Lock()
        
        # 性能统计
        self.generation_stats = {
            'total_sections': 0,
            'completed_sections': 0,
            'failed_sections': 0,
            'total_generation_time': 0.0,
            'avg_quality_score': 0.0,
            'start_time': None,
            'end_time': None
        }
        
        status_msg = f"智能速率控制: {'已启用' if self.has_smart_control else '传统模式'}"
        self.logger.info(f"EnhancedMainDocumentGenerator 初始化完成，并发线程数: {self.max_workers}, {status_msg}")

    def set_max_workers(self, max_workers: int):
        """动态设置最大线程数"""
        self.max_workers = max_workers
        self.concurrency_manager.set_max_workers('content_generator_agent', max_workers)
        self.logger.info(f"ContentGeneratorAgent 线程数已更新为: {max_workers}")

    def get_max_workers(self) -> int:
        """获取当前最大线程数"""
        return self.max_workers

    def set_rate_limit_delay(self, delay: float):
        """动态设置速率限制延迟"""
        self.rate_limit_delay = delay
        self.concurrency_manager.set_rate_limit_delay(delay, 'content_generator_agent')
        self.logger.info(f"ContentGeneratorAgent 速率限制已更新为: {delay}秒")

    def get_rate_limit_delay(self) -> float:
        """获取当前速率限制延迟"""
        if self.has_smart_control:
            return self.rate_limiter.get_delay()
        return self.rate_limit_delay

    def generate_document(self, json_file_path: str = "第二agent的输出.json") -> str:
        """
        生成文档（智能速率控制增强版）
        
        Args:
            json_file_path: JSON文件路径
            
        Returns:
            str: 完整版文档路径
        """
        
        print("🚀 开始生成文档（智能速率控制增强版）...")
        print(f"📁 输入文件: {json_file_path}")
        print(f"🔧 并行线程: {self.max_workers}")
        
        if self.has_smart_control:
            print(f"🧠 智能速率控制: 已启用，目标成功率 {self.rate_limiter.agent_config['target_success_rate']:.0%}")
        else:
            print(f"⏱️  传统速率限制: {self.rate_limit_delay}秒/请求")
            
        print("=" * 60)
        
        # 初始化统计
        self.generation_stats['start_time'] = datetime.now()
        
        # 1. 检查文件
        if not os.path.exists(json_file_path):
            raise FileNotFoundError(f"文件不存在: {json_file_path}")
        
        # 2. 读取JSON
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # 3. 并行生成内容（智能速率控制版）
        updated_json = self._generate_content_parallel_smart(json_data)
        
        # 4. 保存JSON和生成markdown
        result_path = self._save_results(updated_json)
        
        # 5. 输出性能报告
        self._print_performance_report()
        
        return result_path
    
    def _generate_content_parallel_smart(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        并行生成内容（智能速率控制版）
        """
        
        updated_json = json.loads(json.dumps(json_data))
        tasks = []
        
        # 构建任务列表
        for title_idx, title_part in enumerate(updated_json.get('report_guide', [])):
            for section_idx, section in enumerate(title_part.get('sections', [])):
                if 'subtitle' in section:
                    task = {
                        'title_idx': title_idx,
                        'section_idx': section_idx,
                        'subtitle': section['subtitle'],
                        'how_to_write': section.get('how_to_write', ''),
                        'retrieved_text': section.get('retrieved_text', []),
                        'retrieved_image': section.get('retrieved_image', []),
                        'retrieved_table': section.get('retrieved_table', [])
                    }
                tasks.append(task)
        
        total_tasks = len(tasks)
        completed_tasks = 0
        self.generation_stats['total_sections'] = total_tasks
        
        print(f"📊 开始并行处理 {total_tasks} 个任务...")
        
        # 并行执行（智能速率控制版）
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(self._generate_single_section_smart, task): task
                for task in tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    
                    # 更新JSON
                    title_idx = task['title_idx']
                    section_idx = task['section_idx']
                    section = updated_json['report_guide'][title_idx]['sections'][section_idx]
                    
                    section['generated_content'] = result['content']
                    section['quality_score'] = result['quality_score']
                    section['word_count'] = result['word_count']
                    section['generation_time'] = result['generation_time']
                    
                    completed_tasks += 1
                    self.generation_stats['completed_sections'] = completed_tasks
                    progress = (completed_tasks / total_tasks) * 100
                    
                    # 获取当前延迟状态
                    if self.has_smart_control:
                        current_delay = self.rate_limiter.current_delay
                        performance_level = self.rate_limiter._assess_performance_level()
                        status_icon = "🚀" if performance_level == "excellent" else "⚡" if performance_level == "good" else "⚠️"
                    else:
                        current_delay = self.rate_limit_delay
                        status_icon = "🔄"
                    
                    print(f"{status_icon} [{completed_tasks:2d}/{total_tasks}] {progress:5.1f}% | {task['subtitle'][:25]:<25} | {result['word_count']:4d}字 | 质量:{result['quality_score']:.2f} | 延迟:{current_delay:.1f}s")
                    
                except Exception as e:
                    completed_tasks += 1
                    self.generation_stats['failed_sections'] += 1
                    
                    # 记录失败到智能速率控制器
                    if self.has_smart_control:
                        self.concurrency_manager.record_api_request(
                            agent_name='content_generator_agent',
                            success=False,
                            error_type='unknown'
                        )
                    
                    print(f"❌ [{completed_tasks:2d}/{total_tasks}] 失败 | {task['subtitle'][:25]:<25} | 错误: {e}")
        
        print("🎉 并行生成完成!")
        self.generation_stats['end_time'] = datetime.now()
        return updated_json
    
    def _generate_single_section_smart(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """生成单个章节（智能速率控制版）"""
        
        start_time = time.time()
        
        # 智能速率控制
        if self.has_smart_control:
            # 使用智能速率控制器获取动态延迟
            delay = self.rate_limiter.get_delay()
            if delay > 0:
                time.sleep(delay)
        else:
            # 兼容性：使用传统速率控制
            with self.request_lock:
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                
                if time_since_last < self.rate_limit_delay:
                    sleep_time = self.rate_limit_delay - time_since_last
                    time.sleep(sleep_time)
                
                self.last_request_time = time.time()
        
        # 执行内容生成
        try:
            generation_start = time.time()
            result = self.agent.generate_content_from_json(
                task['subtitle'],
                task['how_to_write'],
                task['retrieved_text'],
                task['retrieved_image'],
                task['retrieved_table']
            )
            generation_time = time.time() - generation_start
            
            # 记录成功到智能速率控制器
            if self.has_smart_control:
                self.concurrency_manager.record_api_request(
                    agent_name='content_generator_agent',
                    success=True,
                    response_time=generation_time
                )
            
            return result
            
        except Exception as e:
            generation_time = time.time() - generation_start if 'generation_start' in locals() else 0
            
            # 智能错误分类和记录
            if self.has_smart_control:
                error_type = self._classify_error(str(e))
                self.concurrency_manager.record_api_request(
                    agent_name='content_generator_agent',
                    success=False,
                    response_time=generation_time,
                    error_type=error_type
                )
            
            raise e
    
    def _classify_error(self, error_message: str) -> str:
        """智能错误分类"""
        error_msg = error_message.lower()
        
        if 'rate limit' in error_msg or '429' in error_msg:
            return 'rate_limit'
        elif 'timeout' in error_msg:
            return 'timeout'
        elif 'network' in error_msg or 'connection' in error_msg:
            return 'network'
        elif '5' in error_msg[:2]:  # 5xx errors
            return 'server_error'
        elif '4' in error_msg[:2]:  # 4xx errors
            return 'client_error'
        else:
            return 'unknown'
    
    def _save_results(self, updated_json: Dict[str, Any]) -> str:
        """保存结果文件"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存JSON
        json_path = f"生成文档的依据_完成_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(updated_json, f, ensure_ascii=False, indent=2)
        
        # 生成markdown
        full_md_path = f"完整版文档_{timestamp}.md"
        
        # 完整版
        full_content = self._convert_to_markdown(updated_json)
        with open(full_md_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        # 统计信息
        stats = self._get_stats(updated_json)
        
        print("=" * 60)
        print("📊 生成统计:")
        print(f"   总章节数: {stats['total_sections']}")
        print(f"   完成章节: {stats['completed_sections']}")
        print(f"   失败章节: {self.generation_stats['failed_sections']}")
        print(f"   总字数: {stats['total_words']:,}")
        print(f"   平均质量分: {stats['average_quality']:.3f}")
        print("=" * 60)
        print("📁 输出文件:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {full_md_path}")
        print("=" * 60)
        
        # 返回JSON文件路径，以便后续的重新生成功能使用
        return json_path
    
    def _print_performance_report(self):
        """打印性能报告"""
        if not self.has_smart_control:
            print("ℹ️  智能速率控制未启用，无详细性能报告")
            return
        
        print("\n" + "="*60)
        print("📈 智能速率控制性能报告")
        print("="*60)
        
        # 获取性能报告
        report = self.concurrency_manager.get_performance_report('content_generator_agent')
        
        if 'error' in report:
            print(f"⚠️  {report['error']}")
            return
        
        # 基本性能指标
        print(f"🎯 目标成功率: {report['target_success_rate']:.0%}")
        print(f"📊 实际成功率: {report['recent_success_rate']:.1%}")
        print(f"⏱️  当前延迟: {report['current_delay']:.2f}秒")
        print(f"🔄 自适应因子: {report['adaptive_factor']:.2f}")
        print(f"📈 性能等级: {report['performance_level']}")
        print(f"📉 趋势: {report['trend']}")
        
        # 错误统计
        if report['error_breakdown']:
            print(f"\n🚨 错误分布:")
            for error_type, count in report['error_breakdown'].items():
                print(f"   {error_type}: {count}次")
        
        # 优化建议
        print(f"\n💡 优化建议:")
        for suggestion in report['recommendations']:
            print(f"   • {suggestion}")
        
        print("="*60)

    def get_comprehensive_performance_report(self) -> Dict[str, Any]:
        """获取综合性能报告"""
        base_report = {
            'generation_stats': self.generation_stats.copy(),
            'system_config': {
                'max_workers': self.max_workers,
                'has_smart_control': self.has_smart_control,
                'rate_limit_delay': self.rate_limit_delay
            }
        }
        
        if self.has_smart_control:
            smart_report = self.concurrency_manager.get_performance_report('content_generator_agent')
            base_report['smart_rate_control'] = smart_report
        
        return base_report

    def _convert_to_markdown(self, json_data: Dict[str, Any]) -> str:
        """
        转换为markdown格式
        """
        
        markdown_lines = []
        report_guide = json_data.get('report_guide', [])
        
        for title_section in report_guide:
            title = title_section.get('title', '')
            sections = title_section.get('sections', [])
            
            # 添加主标题（一级标题）
            markdown_lines.append(f"# {title}")
            markdown_lines.append("")
            
            # 处理每个子节
            for section in sections:
                subtitle = section.get('subtitle', '')
                generated_content = section.get('generated_content', '')
                retrieved_table = section.get('retrieved_table', [])
                retrieved_image = section.get('retrieved_image', [])
                
                # 添加子标题（二级标题）
                markdown_lines.append(f"## {subtitle}")
                markdown_lines.append("")
                
                # 添加生成的内容（只有正文，不包含标题）
                if generated_content:
                    # 对正文内容进行缩进处理
                    content = self._format_content(generated_content)
                    # 添加表格和图片
                    content_with_media = self._append_tables_and_images(content, retrieved_table, retrieved_image)
                    markdown_lines.append(content_with_media)
                else:
                    markdown_lines.append("*[内容未生成]*")
                
                markdown_lines.append("")
        
        return "\n".join(markdown_lines)
    
    def _format_content(self, content: str) -> str:
        """
        对正文内容进行格式化（无缩进）
        """
        
        if not content:
            return content
        
        # 直接返回原内容，不进行缩进处理
        return content
    
    def _append_tables_and_images(self, content: str, retrieved_table: list, retrieved_image: list) -> str:
        """
        在生成的章节内容后面插入表格和图片
        
        Args:
            content: 生成的章节内容
            retrieved_table: 表格检索结果列表
            retrieved_image: 图片检索结果列表
            
        Returns:
            str: 包含表格和图片的完整内容
        """
        final_content = content
        
        # 添加表格 - 使用三级标题
        if retrieved_table:
            final_content += "\n\n### 相关表格资料\n"
            for i, table_item in enumerate(retrieved_table, 1):
                table_content = table_item.get('content', str(table_item))
                table_source = table_item.get('source', '未知来源')
                final_content += f"\n**表格{i}** (来源: {table_source})\n\n{table_content}\n"
        
        # 添加图片 - 使用三级标题和markdown图片语法，并去重
        if retrieved_image:
            final_content += "\n\n### 相关图片资料\n"
            
            # 根据URL去重图片
            seen_urls = set()
            unique_images = []
            for image_item in retrieved_image:
                image_path = image_item.get('path', '无路径')
                if image_path and image_path != '无路径' and image_path not in seen_urls:
                    seen_urls.add(image_path)
                    unique_images.append(image_item)
                elif image_path == '无路径':  # 保留没有路径的图片项
                    unique_images.append(image_item)
            
            for i, image_item in enumerate(unique_images, 1):
                image_desc = image_item.get('content', image_item.get('description', f'检索到的相关图片 {i}'))
                image_path = image_item.get('path', '无路径')
                image_source = image_item.get('source', '未知来源')
                
                # 限制图片描述长度到100字符以内
                if len(image_desc) > 100:
                    image_desc = image_desc[:97] + "..."
                
                # 使用标准markdown图片语法
                if image_path and image_path != '无路径':
                    final_content += f"\n![{image_desc}]({image_path})\n*图片来源: {image_source}*\n"
                else:
                    final_content += f"\n**图片{i}** (来源: {image_source})  \n描述: {image_desc}  \n*路径未提供*\n"
        
        return final_content
    
    def _get_stats(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """获取统计信息"""
        
        stats = {
            'total_sections': 0,
            'completed_sections': 0,
            'total_words': 0,
            'average_quality': 0.0
        }
        
        report_guide = json_data.get('report_guide', [])
        quality_scores = []
        
        for title_section in report_guide:
            sections = title_section.get('sections', [])
            stats['total_sections'] += len(sections)
            
            for section in sections:
                if 'generated_content' in section:
                    stats['completed_sections'] += 1
                    stats['total_words'] += section.get('word_count', 0)
                    
                    quality_score = section.get('quality_score', 0.0)
                    quality_scores.append(quality_score)
        
        if quality_scores:
            stats['average_quality'] = sum(quality_scores) / len(quality_scores)
        
        return stats


def main():
    """主函数"""
    
    try:
        # 创建生成器
        generator = EnhancedMainDocumentGenerator()
        
        # 生成文档
        full_path = generator.generate_document()
        
        print("🎉 文档生成完成!")
        
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())