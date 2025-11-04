# Document Agent Prompts

本目录包含了Document Agent系统中所有Agent使用的提示词模板。

## 文件说明

### 1. react_agent_prompts.py
ReAct Agent的提示词模板，用于智能检索和查询生成。

**包含的提示词：**
- `MULTI_DIMENSIONAL_QUERY_PROMPT`: 多维度查询生成提示词
  - 用途：根据项目信息和写作要求生成精准的检索查询
  - 输出格式：JSON数组，包含维度、查询词和优先级

- `WEB_SEARCH_QUERY_PROMPT`: Web搜索查询生成提示词
  - 用途：基于RAG检索结果的不足生成Web搜索查询
  - 输出格式：3-6个关键词的搜索字符串

- `REACT_REASON_AND_ACT_PROMPT`: ReAct推理和行动提示词（已废弃）
  - 用途：原ReAct循环中的推理和行动阶段
  - 输出格式：包含analysis, strategy, keywords的JSON

- `SECTION_RESULTS_QUALITY_PROMPT`: 单次检索结果质量评估
  - 用途：评估单次检索结果的质量
  - 输出格式：0.0-1.0的评分

- `OVERALL_RAG_QUALITY_PROMPT`: 整体RAG质量评估
  - 用途：评估所有RAG检索结果的整体质量
  - 输出格式：0.0-1.0的评分

### 2. orchestrator_agent_prompts.py
Orchestrator Agent的提示词模板，用于文档结构设计和写作指导。

**包含的提示词：**
- `DOCUMENT_STRUCTURE_PROMPT`: 文档基础结构生成提示词
  - 用途：根据用户需求生成完整的文档结构
  - 输出格式：包含report_guide的JSON结构

- `WRITING_GUIDE_PROMPT`: 写作指导生成提示词
  - 用途：为每个子章节生成具体的写作指导
  - 输出格式：包含writing_guides的JSON数组

### 3. document_reviewer_prompts.py
Document Reviewer的提示词模板，用于文档质量评估。

**包含的提示词：**
- `REDUNDANCY_ANALYSIS_PROMPT`: 冗余分析提示词
  - 用途：识别文档中的不必要冗余内容
  - 输出格式：包含subtitle和suggestion的JSON数组

### 4. regenerate_sections_prompts.py
章节重新生成的提示词模板。

**包含的提示词：**
- `SECTION_MODIFICATION_PROMPT`: 章节修改提示词
  - 用途：根据评估建议重新生成章节内容
  - 输出格式：纯文本正文内容

### 5. content_generator_prompts.py
Content Generator的提示词模板，用于章节内容生成。

**包含的提示词：**
- `CONTENT_GENERATION_PROMPT`: 内容生成提示词
  - 用途：根据写作指导和参考资料生成章节内容
  - 输出格式：800-1200字的纯文本正文

## 使用方法

### 方法1：直接导入
```python
from Document_Agent.prompts import MULTI_DIMENSIONAL_QUERY_PROMPT

# 使用提示词
prompt = MULTI_DIMENSIONAL_QUERY_PROMPT.format(
    project_name="项目名称",
    subtitle="章节标题",
    how_to_write="写作要求"
)
```

### 方法2：从子模块导入
```python
from Document_Agent.prompts.react_agent_prompts import MULTI_DIMENSIONAL_QUERY_PROMPT
from Document_Agent.prompts.orchestrator_agent_prompts import DOCUMENT_STRUCTURE_PROMPT

# 使用提示词
prompt = MULTI_DIMENSIONAL_QUERY_PROMPT.format(...)
```

## 提示词格式说明

所有提示词模板都使用Python字符串格式化语法，支持以下占位符：

### ReAct Agent提示词占位符
- `{project_name}`: 项目名称
- `{subtitle}`: 章节标题
- `{how_to_write}`: 写作要求
- `{rag_summary}`: RAG检索结果摘要
- `{attempted_queries}`: 已尝试的查询列表
- `{quality_scores}`: 历史质量评分
- `{available_strategies}`: 可用的检索策略
- `{query}`: 查询词
- `{results_summary}`: 检索结果摘要
- `{text_count}`, `{image_count}`, `{table_count}`, `{total_count}`: 结果数量统计
- `{results_sample}`: 结果样本

### Orchestrator Agent提示词占位符
- `{user_description}`: 用户需求描述
- `{section_title}`: 章节标题
- `{section_goal}`: 章节目标
- `{subtitles_text}`: 子章节标题列表文本

### Document Reviewer提示词占位符
- `$document_content`: 待分析的文档内容（使用$而非{}以避免格式化冲突）

### Content Generator提示词占位符
- `{subtitle}`: 章节标题
- `{how_to_write}`: 写作指导
- `{retrieved_text_content}`: 参考资料内容
- `{feedback}`: 改进反馈

## 注意事项

1. **占位符格式**：大部分提示词使用 `{variable}` 格式，但Document Reviewer使用 `$variable` 格式以避免JSON格式冲突
2. **输出格式**：各提示词的预期输出格式不同，使用时请注意对应Agent的解析逻辑
3. **修改提示词**：修改提示词时请确保：
   - 保持占位符名称不变
   - 保持输出格式要求一致
   - 测试修改后的效果

## 版本历史

- v1.0 (2025-01-04): 初始版本，从各Agent代码中提取prompt

