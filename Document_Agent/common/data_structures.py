"""
多Agent文档生成系统 - 共同数据结构

定义了系统中使用的所有数据结构和枚举类型
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import datetime

class InfoType(Enum):
    """信息类型枚举"""
    FACTUAL = "factual"        # 事实性信息
    PROCEDURAL = "procedural"  # 程序性信息
    CONTEXTUAL = "contextual"  # 上下文信息
    EXAMPLES = "examples"      # 示例信息

class DocType(Enum):
    """文档类型枚举"""
    TECHNICAL = "technical"    # 技术文档
    USER_MANUAL = "user_manual"  # 用户手册
    RESEARCH = "research"      # 研究报告
    TUTORIAL = "tutorial"      # 教程文档

@dataclass
class SectionSpec:
    """章节规格说明"""
    title: str
    description: str
    info_types: List[InfoType]
    dependencies: List[str] = field(default_factory=list)
    estimated_length: int = 1000
    priority: int = 1
    keywords: List[str] = field(default_factory=list)

@dataclass
class DocumentPlan:
    """文档规划"""
    title: str
    goal: str
    doc_type: DocType
    target_audience: str
    outline: List[SectionSpec]
    total_sections: int
    estimated_length: int
    abstract: str = ""
    style_requirements: Dict[str, Any] = field(default_factory=dict)

@dataclass
class QueryGroup:
    """查询组"""
    info_type: InfoType
    queries: List[str]
    priority: int = 1

@dataclass
class CollectionPlan:
    """信息收集计划"""
    query_groups: List[QueryGroup]
    total_queries: int = 0
    
    def __post_init__(self):
        self.total_queries = sum(len(group.queries) for group in self.query_groups)

@dataclass
class CollectedInfo:
    """收集的信息"""
    factual_info: List[str] = field(default_factory=list)
    procedural_info: List[str] = field(default_factory=list)
    contextual_info: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    
    def get_total_items(self) -> int:
        return len(self.factual_info) + len(self.procedural_info) + \
               len(self.contextual_info) + len(self.examples)

@dataclass
class PerfectContext:
    """完美上下文"""
    section_spec: SectionSpec
    collected_info: CollectedInfo
    organized_content: Dict[str, List[str]]
    context_summary: str = ""
    relevance_score: float = 0.0

@dataclass
class GeneratedSection:
    """生成的章节"""
    title: str
    content: str
    metadata: Dict[str, Any]
    quality_score: float
    generation_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    word_count: int = 0
    
    def __post_init__(self):
        self.word_count = len(self.content.split())

@dataclass
class GenerationMetrics:
    """生成过程指标"""
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    end_time: Optional[datetime.datetime] = None
    total_rag_queries: int = 0
    total_llm_calls: int = 0
    average_section_quality: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def get_duration(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0 