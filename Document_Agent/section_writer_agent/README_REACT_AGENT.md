# ReAct Agent - 文档智能检索系统

## 概述

ReAct Agent实现了完整的**Reasoning-Acting-Observing-Reflecting**循环，能够基于章节的`subtitle`和`how_to_write`字段进行智能检索，并将检索结果添加到JSON结构的`retrieved_data`字段中。

## 🔧 修复后的正确逻辑

### 输入格式
接收类似`测试第二agent.json`的JSON结构：
```json
{
  "report_guide": [
    {
      "title": "第一部分 标题",
      "goal": "部分目标描述",
      "sections": [
        {
          "subtitle": "一、章节标题",
          "how_to_write": "详细的写作指导..."
        }
      ]
    }
  ]
}
```

### 处理流程
1. **遍历结构**: 逐个处理每个part的每个section
2. **ReAct循环**: 基于`subtitle`和`how_to_write`进行智能检索
3. **质量评估**: 评估检索结果是否满足写作指导要求
4. **迭代优化**: 根据质量评分决定是否继续检索
5. **结果添加**: 将检索数据添加到`retrieved_data`字段

### 输出格式
生成类似`第二agent的输出.json`的结构：
```json
{
  "report_guide": [
    {
      "title": "第一部分 标题",
      "goal": "部分目标描述", 
      "sections": [
        {
          "subtitle": "一、章节标题",
          "how_to_write": "详细的写作指导...",
          "retrieved_data": "检索到的相关数据内容..."
        }
      ]
    }
  ]
}
```

## 🚀 快速开始

### 1. 基本使用
```python
from react_agent import ReactAgent

# 创建客户端（实际使用时替换为真实客户端）
client = YourClient()

# 创建Agent
agent = ReactAgent(client)

# 读取输入数据
with open('测试第二agent.json', 'r', encoding='utf-8') as f:
    input_data = json.load(f)

# 处理数据
result = agent.process_report_guide(input_data)

# 保存结果
with open('output.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
```

### 2. 运行脚本
```bash
python run_react_agent.py
```

## 🔄 ReAct循环详解

### REASON (推理阶段)
- 分析当前章节的信息需求
- 评估之前检索策略的效果
- 制定下一步检索策略

### ACT (行动阶段)
- 基于推理结果生成查询关键词
- 选择最适合的检索策略
- 避免重复无效的查询

### OBSERVE (观察阶段)
- 执行RAG检索获取结果
- 评估结果质量（0-1评分）
- 记录检索到的数据

### REFLECT (反思阶段)
- 判断质量是否达到阈值
- 决定是否继续迭代
- 防止无效循环

## ⚙️ 配置参数

```python
agent = ReactAgent(client)

# 调整ReAct参数
agent.max_iterations = 5        # 最大迭代次数
agent.quality_threshold = 0.7   # 质量阈值
agent.min_confidence = 0.6      # 最小置信度
```

## 📊 检索策略

| 策略 | 描述 | 使用场景 |
|-----|------|----------|
| direct | 直接关键词搜索 | 首次尝试 |
| contextual | 结合上下文查询 | 需要背景信息 |
| semantic | 语义相关概念 | 扩展相关内容 |
| specific | 具体细节案例 | 需要详细数据 |
| alternative | 同义词相关概念 | 前面策略效果不佳 |

## 🔍 质量评估维度

1. **相关性(0-1)**: 与章节标题和写作指导的匹配程度
2. **完整性(0-1)**: 是否涵盖写作指导中的关键信息点
3. **实用性(0-1)**: 是否包含可直接用于写作的具体内容
4. **准确性(0-1)**: 信息是否准确可信，符合专业要求

## 📁 文件结构

```
section_writer_agent/
├── react_agent.py              # 核心ReAct Agent实现
├── run_react_agent.py          # 运行脚本
├── universal_react_tools.py    # RAG检索工具
├── test_react_logic.py         # 逻辑测试脚本
├── README_REACT_AGENT.md       # 本文档
└── __init__.py                 # 模块初始化
```

## 🧪 测试验证

### 运行测试
```bash
python test_react_logic.py
```

### 测试内容
- ✅ JSON结构解析
- ✅ ReAct循环执行
- ✅ 检索数据添加
- ✅ 输出格式验证

## 📈 性能统计

Agent提供详细的性能统计信息：
```python
stats = agent.get_performance_stats(state)
# 返回：
# {
#   'total_iterations': 3,
#   'queries_attempted': 3,
#   'results_collected': 8,
#   'quality_progression': [0.45, 0.65, 0.75],
#   'final_quality': 0.75,
#   'strategies_used': ['direct', 'contextual', 'specific']
# }
```

## ⚠️ 注意事项

1. **真实客户端**: 实际使用时需要替换模拟客户端为真实的API客户端
2. **RAG工具**: 确保`universal_react_tools.py`中的RAG检索器配置正确
3. **质量阈值**: 根据实际需要调整质量阈值和迭代次数
4. **文件路径**: 确保输入文件路径正确

## 🔄 与之前版本的差异

| 方面 | 之前版本 | 修复后版本 |
|-----|----------|------------|
| 输入格式 | SectionInfo对象 | JSON结构 |
| 处理方式 | 单个章节 | 完整文档结构 |
| 输出格式 | 文本内容 | JSON+retrieved_data |
| 数据流 | title+writing_guidance → 文本 | subtitle+how_to_write → JSON |

## 🎯 核心优势

1. **智能检索**: 基于写作指导进行精准检索
2. **质量控制**: 多维度评估确保结果质量
3. **自适应优化**: 根据反馈调整检索策略
4. **结构化输出**: 保持原有JSON结构并添加数据
5. **可扩展性**: 支持不同类型的文档结构

## 🔧 故障排除

### 常见问题
1. **导入错误**: 确保所有依赖文件在正确位置
2. **编码问题**: 使用UTF-8编码处理中文内容
3. **内存不足**: 大文档可考虑分批处理
4. **质量过低**: 调整质量阈值或增加迭代次数

### 调试技巧
- 启用详细日志: `logging.basicConfig(level=logging.DEBUG)`
- 使用测试脚本验证逻辑
- 检查中间结果文件 