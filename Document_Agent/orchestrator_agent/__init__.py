"""
编排代理 (OrchestratorAgent) - 智能速率控制增强版

职责：
1. 分析文档生成目标和需求
2. 解析源文档结构和内容
3. 生成详细的文档大纲
4. 将任务分解为具体的章节规格
5. 协调整个生成流程
6. 集成智能速率控制和性能监控
"""

from .agent import EnhancedOrchestratorAgent

# 向后兼容性别名
OrchestratorAgent = EnhancedOrchestratorAgent

__all__ = ['EnhancedOrchestratorAgent', 'OrchestratorAgent'] 