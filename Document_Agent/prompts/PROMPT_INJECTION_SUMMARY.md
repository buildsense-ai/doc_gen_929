# Prompt 注入改造总结

## 改造目标

将 `Document_Agent` 文件夹中所有硬编码的 prompt 提取到独立文件，通过文件方式进行注入。

## 改造范围

### 1. ReAct Agent (`section_writer_agent/react_agent.py`)

**文件修改**: 
- 添加 prompt 导入
- 替换 3 处硬编码 prompt

**使用的 Prompt**:
- `MULTI_DIMENSIONAL_QUERY_PROMPT` - 多维度查询生成
- `WEB_SEARCH_QUERY_PROMPT` - Web搜索查询生成
- `OVERALL_RAG_QUALITY_PROMPT` - 整体RAG质量评估

**原位置**: 第252行、第366行、第737行

---

### 2. Orchestrator Agent (`orchestrator_agent/agent.py`)

**文件修改**:
- 添加 prompt 导入
- 替换 2 处有效 prompt（1处废弃代码已跳过）

**使用的 Prompt**:
- `DOCUMENT_STRUCTURE_PROMPT` - 文档结构生成
- `WRITING_GUIDE_PROMPT` - 写作指导生成

**原位置**: 第575行、第921行

---

### 3. Content Generator Agent (`content_generator_agent/simple_agent.py`)

**文件修改**:
- 添加 prompt 导入和路径设置
- 替换 1 处硬编码 prompt

**使用的 Prompt**:
- `CONTENT_GENERATION_PROMPT` - 章节内容生成

**原位置**: 第149行

---

### 4. Document Reviewer (`final_review_agent/document_reviewer.py`)

**文件修改**:
- 添加 prompt 导入和路径设置
- 替换实例属性中的 prompt

**使用的 Prompt**:
- `REDUNDANCY_ANALYSIS_PROMPT` - 冗余分析

**原位置**: 第97行（实例属性）

---

### 5. Regenerate Sections (`final_review_agent/regenerate_sections.py`)

**文件修改**:
- 添加 prompt 导入
- 替换 1 处硬编码 prompt

**使用的 Prompt**:
- `SECTION_MODIFICATION_PROMPT` - 章节修改

**原位置**: 第174行

---

## Prompt 文件结构

```
Document_Agent/prompts/
├── __init__.py                          # 统一导入入口
├── react_agent_prompts.py               # ReAct Agent 提示词（3个）
├── orchestrator_agent_prompts.py        # Orchestrator Agent 提示词（2个）
├── content_generator_prompts.py         # Content Generator 提示词（1个）
├── document_reviewer_prompts.py         # Document Reviewer 提示词（1个）
├── regenerate_sections_prompts.py       # Regenerate Sections 提示词（1个）
├── README.md                            # 使用文档
├── verify_imports.py                    # 验证脚本
└── PROMPT_INJECTION_SUMMARY.md          # 本文件
```

**总计**: 8 个活跃 prompt 模板

---

## 使用方式

### 导入方式

```python
# 方式1：从统一入口导入
from Document_Agent.prompts import (
    MULTI_DIMENSIONAL_QUERY_PROMPT,
    WEB_SEARCH_QUERY_PROMPT,
    OVERALL_RAG_QUALITY_PROMPT,
    DOCUMENT_STRUCTURE_PROMPT,
    WRITING_GUIDE_PROMPT,
    REDUNDANCY_ANALYSIS_PROMPT,
    SECTION_MODIFICATION_PROMPT,
    CONTENT_GENERATION_PROMPT,
)

# 方式2：从具体文件导入
from Document_Agent.prompts.react_agent_prompts import (
    MULTI_DIMENSIONAL_QUERY_PROMPT
)
```

### 使用方式

所有 prompt 都使用 Python 字符串的 `.format()` 方法进行占位符替换：

```python
# 示例：使用多维度查询 prompt
prompt = MULTI_DIMENSIONAL_QUERY_PROMPT.format(
    project_name="示例项目",
    subtitle="项目背景",
    how_to_write="详细描述项目背景..."
)

response = llm_client.generate(prompt)
```

---

## 占位符参考

### ReAct Agent Prompts

1. **MULTI_DIMENSIONAL_QUERY_PROMPT**
   - `project_name`: 项目名称
   - `subtitle`: 章节标题
   - `how_to_write`: 写作指导

2. **WEB_SEARCH_QUERY_PROMPT**
   - `project_name`: 项目名称
   - `subtitle`: 章节标题
   - `how_to_write`: 写作指导
   - `rag_summary`: RAG检索结果摘要

3. **OVERALL_RAG_QUALITY_PROMPT**
   - `subtitle`: 章节标题
   - `how_to_write`: 写作指导
   - `text_count`: 文本结果数量
   - `image_count`: 图片结果数量
   - `table_count`: 表格结果数量
   - `total_count`: 总结果数量
   - `results_sample`: 结果样本

### Orchestrator Agent Prompts

1. **DOCUMENT_STRUCTURE_PROMPT**
   - `user_description`: 用户需求描述

2. **WRITING_GUIDE_PROMPT**
   - `user_description`: 用户需求描述
   - `section_title`: 章节标题
   - `section_goal`: 章节目标
   - `subtitles_text`: 子章节列表文本

### Content Generator Prompts

1. **CONTENT_GENERATION_PROMPT**
   - `subtitle`: 章节标题
   - `how_to_write`: 写作指导
   - `retrieved_text_content`: 检索到的文本内容
   - `feedback`: 改进反馈

### Document Reviewer Prompts

1. **REDUNDANCY_ANALYSIS_PROMPT**
   - 使用 `$document_content` 作为占位符（特殊格式，避免与JSON冲突）

### Regenerate Sections Prompts

1. **SECTION_MODIFICATION_PROMPT**
   - `section_title`: 章节标题
   - `original_content`: 原始内容
   - `suggestion`: 修改建议

---

## 验证

运行验证脚本确保所有 prompt 正确导入：

```bash
python Document_Agent/prompts/verify_imports.py
```

---

## 优势

1. **集中管理**: 所有 prompt 集中在 `prompts/` 目录，易于维护
2. **版本控制**: Prompt 变更可以独立追踪
3. **复用性**: 同一 prompt 可在多处使用
4. **可测试**: 可以单独测试和优化 prompt
5. **文档化**: 每个 prompt 都有清晰的说明和占位符文档

---

## 注意事项

1. 所有 prompt 使用 Python 字符串 `.format()` 方法进行占位符替换
2. 占位符使用 `{placeholder_name}` 格式
3. `REDUNDANCY_ANALYSIS_PROMPT` 例外，使用 `$document_content`（避免JSON格式冲突）
4. 修改 prompt 后需要重启应用才能生效
5. 新增 prompt 需要同时更新 `__init__.py` 和 `README.md`

---

**改造完成时间**: 2025-11-04
**改造人员**: AI Assistant

