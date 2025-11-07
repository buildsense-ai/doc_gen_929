# 模板数据库集成说明

## 功能概述

系统已集成 MySQL 数据库，用于自动保存和管理自建模板。

## 配置说明

### 1. 环境变量配置

在 `.env` 文件中已配置 MySQL 连接信息：

```env
# ===== MySQL数据库配置 =====
MYSQL_HOST=gz-cdb-e0aa423v.sql.tencentcdb.com
MYSQL_PORT=20236
MYSQL_USER=root
MYSQL_PASSWORD=Aa@114514
MYSQL_DATABASE=mysql_templates
MYSQL_CHARSET=utf8mb4
```

### 2. 数据库表结构

```sql
CREATE TABLE `report_guide_templates` (
  `guide_id` VARCHAR(64) PRIMARY KEY COMMENT '模板ID',
  `template_name` VARCHAR(255) NOT NULL COMMENT '模板名称',
  `report_guide` TEXT NOT NULL COMMENT '模板内容（JSON格式）',
  `guide_summary` TEXT COMMENT '模板摘要',
  `usage_frequency` INT DEFAULT 0 COMMENT '使用频率',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `last_updated` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `project_id` VARCHAR(64) DEFAULT NULL COMMENT '项目ID，用于多项目隔离',
  
  INDEX `idx_template_name` (`template_name`),
  INDEX `idx_project_id` (`project_id`),
  INDEX `idx_created_at` (`created_at`),
  FULLTEXT INDEX `idx_fulltext_search` (`template_name`, `guide_summary`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报告模板表';
```

## 安装依赖

```bash
pip install -r requirements.txt
```

主要新增依赖：
- `pymysql>=1.1.0` - MySQL 数据库客户端

## 功能说明

### 1. 自动保存模板

当通过以下接口创建新模板时，系统会自动保存到数据库：

**接口：** `/smart_generate_document`

**请求示例：**
```json
{
  "query": "生成一份用户操作手册",
  "project_name": "医灵古庙",
  "project_id": "proj_123456",
  "enable_review_and_regeneration": false,
  "guide_id": null  // null 或 "" 表示创建新模板
}
```

**自动保存逻辑：**
- ✅ 当 `guide_id` 为 `null` 或 `""` 时，创建新模板并自动保存
- ✅ 保存时会关联 `project_id`（如果提供）
- ✅ 自动生成模板摘要

### 2. 使用已有模板

当使用已有模板时，系统会自动增加使用频率：

**请求示例：**
```json
{
  "query": "生成报告",
  "project_name": "医灵古庙",
  "project_id": "proj_123456",
  "guide_id": "guide_20241104_120000"  // 指定已有模板ID
}
```

**自动更新逻辑：**
- ✅ 每次使用模板，`usage_frequency` 字段 +1
- ✅ 更新 `last_updated` 时间戳

### 3. 模板查询接口

#### 3.1 根据ID获取模板

```http
GET /templates/{guide_id}
```

**响应示例：**
```json
{
  "success": true,
  "message": "成功获取模板: guide_20241104_120000",
  "data": {
    "guide_id": "guide_20241104_120000",
    "template_name": "用户操作手册模板",
    "report_guide": { /* 完整的模板JSON */ },
    "guide_summary": "根据需求'生成用户操作手册'自动生成的模板，包含 5 个章节",
    "usage_frequency": 10,
    "created_at": "2024-11-04T12:00:00",
    "last_updated": "2024-11-04T15:30:00",
    "project_id": "proj_123456"
  }
}
```

#### 3.2 搜索模板

```http
POST /templates/search
```

**请求体：**
```json
{
  "project_id": "proj_123456",  // 可选
  "keyword": "用户手册",         // 可选
  "limit": 10                   // 返回数量
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "成功找到 3 个模板",
  "data": {
    "templates": [
      {
        "guide_id": "guide_001",
        "template_name": "用户操作手册",
        "guide_summary": "用户操作手册模板...",
        "usage_frequency": 15,
        "created_at": "2024-11-04T10:00:00",
        "last_updated": "2024-11-04T15:00:00",
        "project_id": "proj_123456"
      }
    ],
    "count": 3,
    "query": {
      "project_id": "proj_123456",
      "keyword": "用户手册",
      "limit": 10
    }
  }
}
```

#### 3.3 获取项目模板列表

```http
GET /templates/project/{project_id}?limit=10
```

**响应示例：**
```json
{
  "success": true,
  "message": "成功获取项目 proj_123456 的模板",
  "data": {
    "templates": [ /* 模板列表 */ ],
    "count": 5,
    "project_id": "proj_123456"
  }
}
```

## 项目隔离

系统支持多项目隔离：

- ✅ 每个模板可关联 `project_id`
- ✅ 查询时可按项目过滤
- ✅ 同一模板可在不同项目中使用

## 使用流程示例

### 场景1：首次创建模板

```bash
# 1. 创建新模板
POST /smart_generate_document
{
  "query": "生成项目可行性研究报告",
  "project_name": "新项目A",
  "project_id": "proj_001",
  "guide_id": null  # 创建新模板
}

# 系统自动：
# ✅ 生成文档结构
# ✅ 保存模板到数据库
# ✅ 返回 template_saved 信息
```

### 场景2：复用已有模板

```bash
# 1. 搜索项目的模板
POST /templates/search
{
  "project_id": "proj_001",
  "keyword": "可行性"
}

# 2. 使用找到的模板
POST /smart_generate_document
{
  "query": "生成新的可行性报告",
  "project_name": "新项目A",
  "project_id": "proj_001",
  "guide_id": "guide_20241104_120000"  # 使用已有模板
}

# 系统自动：
# ✅ 使用指定模板
# ✅ 使用频率 +1
```

## 注意事项

1. **配置安全**：数据库配置已放在 `.env` 文件中，确保该文件不被提交到 Git
2. **错误处理**：模板保存失败不会影响文档生成主流程
3. **连接管理**：数据库连接采用单例模式，自动重连
4. **字符集**：使用 `utf8mb4` 支持完整的 Unicode 字符

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8002/docs
- ReDoc: http://localhost:8002/redoc

