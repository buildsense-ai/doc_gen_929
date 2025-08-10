"""
内容生成代理 (ContentGeneratorAgent) - 智能速率控制增强版

职责：
1. 分析收集到的完美上下文
2. 生成高质量的章节内容
3. 进行多轮质量检查和改进
4. 确保内容的连贯性和准确性
5. 计算和优化内容质量评分
6. 集成智能速率控制和性能监控
7. 提供实时性能仪表盘
"""

from .simple_agent import SimpleContentGeneratorAgent
from .main_generator import EnhancedMainDocumentGenerator

# 向后兼容性别名
ContentGeneratorAgent = SimpleContentGeneratorAgent
MainDocumentGenerator = EnhancedMainDocumentGenerator

__all__ = [
    'EnhancedMainDocumentGenerator',
    'SimpleContentGeneratorAgent', 
    'MainDocumentGenerator',
    'ContentGeneratorAgent'
] 