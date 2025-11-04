"""
Document Agent Prompts
所有Agent使用的提示词模板集合
"""

from .react_agent_prompts import (
    MULTI_DIMENSIONAL_QUERY_PROMPT,
    WEB_SEARCH_QUERY_PROMPT
)

from .orchestrator_agent_prompts import (
    DOCUMENT_STRUCTURE_PROMPT,
    WRITING_GUIDE_PROMPT
)

from .document_reviewer_prompts import (
    REDUNDANCY_ANALYSIS_PROMPT
)

from .regenerate_sections_prompts import (
    SECTION_MODIFICATION_PROMPT
)

from .content_generator_prompts import (
    CONTENT_GENERATION_PROMPT
)

__all__ = [
    # ReAct Agent prompts
    'MULTI_DIMENSIONAL_QUERY_PROMPT',
    'WEB_SEARCH_QUERY_PROMPT',
    
    # Orchestrator Agent prompts
    'DOCUMENT_STRUCTURE_PROMPT',
    'WRITING_GUIDE_PROMPT',
    
    # Document Reviewer prompts
    'REDUNDANCY_ANALYSIS_PROMPT',
    
    # Regenerate Sections prompts
    'SECTION_MODIFICATION_PROMPT',
    
    # Content Generator prompts
    'CONTENT_GENERATION_PROMPT',
]

