"""
Final Review Agent - 文档质量评估模块

负责对生成的文档进行质量评估，主要关注冗余度分析。
使用OpenRouter API进行智能文档分析。
"""

from .document_reviewer import DocumentReviewer

__all__ = ['DocumentReviewer'] 