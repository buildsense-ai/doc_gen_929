# 简化文档生成器

一个基于JSON配置的智能文档生成器，专为结构化文档创建而设计。

## 核心功能

- **JSON驱动生成**：基于 `生成文档的依据.json` 自动生成文档
- **三线程并行处理**：同时处理多个章节，提高生成效率
- **智能内容生成**：严格遵循 `subtitle`、`how_to_write`、`retrieved_data` 三个字段
- **中文排版优化**：段落首行自动缩进两个字符
- **质量控制**：自动评分和内容改进机制

## 项目结构

```
agents/content_generator_agent/
├── main_generator.py        # 主程序入口
├── simple_agent.py         # 核心生成逻辑
├── __init__.py             # 包初始化
└── README.md               # 项目说明
```

## 使用方法

### 1. 准备JSON配置文件

确保项目根目录下存在 `生成文档的依据.json` 文件，格式如下：

```json
{
  "report_guide": [
    {
      "title": "第一部分 建设项目概况",
      "sections": [
        {
          "subtitle": "一、项目背景",
          "how_to_write": "写作指导内容...",
          "retrieved_data": "参考资料内容..."
        }
      ]
    }
  ]
}
```

### 2. 运行生成器

```bash
cd agents/content_generator_agent
python main_generator.py
```

### 3. 输出文件

程序会生成两个文件：
- `完整版文档_YYYYMMDD_HHMMSS.md` - 完整的markdown文档
- `生成文档的依据_完成_YYYYMMDD_HHMMSS.json` - 包含生成内容的JSON文件

## 技术特点

### 并行处理
- 使用3个线程同时处理不同章节
- 每4秒处理一个章节（API限流）
- 支持自动重试机制

### 质量控制
- **长度评分**（20%）：内容长度是否合适
- **完整性评分**（30%）：是否充分利用参考资料
- **结构性评分**（20%）：内容结构是否清晰
- **专业性评分**（30%）：语言表达是否专业

### 内容格式
- 段落格式清洁，无首行缩进
- 列表项正常显示
- 标题层级：`# 主标题` → `## 子标题`
- 内容清洁：自动移除重复标题

## 配置说明

### 环境要求
- Python 3.7+
- 支持的LLM API（通过 `simple_agent.py` 配置）

### 参数调整
- 线程数量：默认3个（可在 `main_generator.py` 中修改）
- 生成质量阈值：默认0.3（可在 `simple_agent.py` 中调整）
- 重试次数：默认3次

## 使用示例

```python
from main_generator import MainDocumentGenerator

# 创建生成器
generator = MainDocumentGenerator()

# 生成文档
doc_path = generator.generate_document("../../生成文档的依据.json")

print(f"文档已生成: {doc_path}")
```

## 注意事项

1. 确保JSON文件路径正确
2. 网络连接稳定（需要调用LLM API）
3. 生成过程中避免中断程序
4. 大型文档可能需要较长时间完成

## 更新日志

- v2.1: 去除首行缩进，优化文档美观性
- v2.0: 简化为单一完整版输出，优化中文排版
- v1.0: 初始版本，支持完整版和简洁版双输出 