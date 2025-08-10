"""
多Agent文档生成系统 - 共同模块

包含所有Agent共享的数据结构和工具函数
"""

from .data_structures import (
    InfoType, DocType, SectionSpec, DocumentPlan, QueryGroup,
    CollectionPlan, CollectedInfo, PerfectContext, GeneratedSection,
    GenerationMetrics
)

__all__ = [
    'InfoType', 'DocType', 'SectionSpec', 'DocumentPlan', 'QueryGroup',
    'CollectionPlan', 'CollectedInfo', 'PerfectContext', 'GeneratedSection',
    'GenerationMetrics'
] 