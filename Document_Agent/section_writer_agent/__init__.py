"""
章节写作代理 (ReactAgent) - 智能速率控制增强版

职责：
1. 使用ReAct模式进行智能信息检索
2. 执行Reasoning-Acting-Observing循环
3. 收集和整理相关信息和资料
4. 为内容生成代理提供高质量的信息支持
5. 集成智能速率控制和RAG查询优化

特点：
- 多策略查询方式
- 智能质量评估
- 并行处理支持
- 智能速率控制
"""

from .react_agent import EnhancedReactAgent

# 向后兼容性别名
ReactAgent = EnhancedReactAgent

__all__ = [
    'EnhancedReactAgent',
    'ReactAgent'
] 