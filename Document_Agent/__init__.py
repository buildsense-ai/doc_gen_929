"""
Gauz Document Agent - 智能速率控制增强版

主要组件：
- 编排代理（OrchestratorAgent）
- 章节写作代理（ReAct Agent）  
- 内容生成代理（Content Generator Agent）
- 通用数据结构（Common）

版本：v2.0 - 智能速率控制增强版
"""

# 导入增强版本的Agent类
from .orchestrator_agent.agent import EnhancedOrchestratorAgent
from .section_writer_agent.react_agent import EnhancedReactAgent
from .content_generator_agent.main_generator import EnhancedMainDocumentGenerator
from .common.performance_monitor import DocumentAgentPerformanceMonitor
from .common.advanced_rate_limiter import DocumentAgentRateLimiter

# 向后兼容性别名（确保现有代码不会中断）
OrchestratorAgent = EnhancedOrchestratorAgent
ReactAgent = EnhancedReactAgent  
MainDocumentGenerator = EnhancedMainDocumentGenerator

# 导出所有主要类
__all__ = [
    # 增强版本（推荐使用）
    'EnhancedOrchestratorAgent',
    'EnhancedReactAgent', 
    'EnhancedMainDocumentGenerator',
    'DocumentAgentPerformanceMonitor',
    'DocumentAgentRateLimiter',
    
    # 兼容性别名（保持现有代码工作）
    'OrchestratorAgent',
    'ReactAgent',
    'MainDocumentGenerator'
]

__version__ = "2.0.0-smart-rate-control"
__author__ = "Document Agent Team" 