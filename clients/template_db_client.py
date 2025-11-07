"""
模板数据库客户端
用于管理报告模板的 CRUD 操作
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
from config.mysql_config import get_mysql_config


class TemplateDBClient:
    """模板数据库客户端"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config = get_mysql_config()
        self._connection = None
    
    def _get_connection(self):
        """获取数据库连接（带重连机制）"""
        try:
            if self._connection is None or not self._connection.open:
                self.logger.info("🔌 正在连接 MySQL 数据库...")
                self._connection = pymysql.connect(
                    host=self.config["host"],
                    port=self.config["port"],
                    user=self.config["user"],
                    password=self.config["password"],
                    database=self.config["database"],
                    charset=self.config["charset"],
                    cursorclass=DictCursor
                )
                self.logger.info("✅ MySQL 数据库连接成功")
            return self._connection
        except Exception as e:
            self.logger.error(f"❌ MySQL 连接失败: {e}")
            raise
    
    def save_template(
        self,
        guide_id: str,
        template_name: str,
        report_guide: Dict[str, Any],
        guide_summary: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> bool:
        """
        保存模板到数据库
        
        Args:
            guide_id: 模板ID
            template_name: 模板名称
            report_guide: 模板内容（Dict，会转为JSON）
            guide_summary: 模板摘要（可选）
            project_id: 项目ID（可选）
            
        Returns:
            bool: 是否保存成功
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 将 Dict 转换为 JSON 字符串
            report_guide_json = json.dumps(report_guide, ensure_ascii=False)
            
            # 插入或更新模板
            sql = """
                INSERT INTO report_guide_templates 
                (guide_id, template_name, report_guide, guide_summary, project_id, created_at, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    template_name = VALUES(template_name),
                    report_guide = VALUES(report_guide),
                    guide_summary = VALUES(guide_summary),
                    project_id = VALUES(project_id),
                    last_updated = NOW()
            """
            
            cursor.execute(sql, (guide_id, template_name, report_guide_json, guide_summary, project_id))
            conn.commit()
            
            self.logger.info(f"✅ 模板保存成功: {guide_id} - {template_name}")
            if project_id:
                self.logger.info(f"   项目ID: {project_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 保存模板失败: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
    
    def get_template_by_id(self, guide_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取模板
        
        Args:
            guide_id: 模板ID
            
        Returns:
            Dict: 模板数据，如果不存在返回 None
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = """
                SELECT guide_id, template_name, report_guide, guide_summary, 
                       usage_frequency, created_at, last_updated, project_id
                FROM report_guide_templates
                WHERE guide_id = %s
            """
            
            cursor.execute(sql, (guide_id,))
            result = cursor.fetchone()
            
            if result:
                # 将 JSON 字符串转回 Dict
                result['report_guide'] = json.loads(result['report_guide'])
                self.logger.info(f"✅ 获取模板成功: {guide_id}")
                return result
            else:
                self.logger.warning(f"⚠️ 模板不存在: {guide_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ 获取模板失败: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    def get_templates_by_project(self, project_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取指定项目的模板列表
        
        Args:
            project_id: 项目ID
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 模板列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = """
                SELECT guide_id, template_name, guide_summary, 
                       usage_frequency, created_at, last_updated, project_id
                FROM report_guide_templates
                WHERE project_id = %s
                ORDER BY last_updated DESC
                LIMIT %s
            """
            
            cursor.execute(sql, (project_id, limit))
            results = cursor.fetchall()
            
            self.logger.info(f"✅ 获取项目模板成功: {project_id} (共 {len(results)} 个)")
            return results
            
        except Exception as e:
            self.logger.error(f"❌ 获取项目模板失败: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def increment_usage(self, guide_id: str) -> bool:
        """
        增加模板使用频率
        
        Args:
            guide_id: 模板ID
            
        Returns:
            bool: 是否更新成功
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            sql = """
                UPDATE report_guide_templates
                SET usage_frequency = usage_frequency + 1,
                    last_updated = NOW()
                WHERE guide_id = %s
            """
            
            cursor.execute(sql, (guide_id,))
            conn.commit()
            
            self.logger.info(f"✅ 模板使用频率+1: {guide_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 更新使用频率失败: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
    
    def search_templates(
        self,
        keyword: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索模板
        
        Args:
            keyword: 搜索关键词（可选）
            project_id: 项目ID过滤（可选）
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 模板列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if project_id:
                conditions.append("project_id = %s")
                params.append(project_id)
            
            if keyword:
                conditions.append("(template_name LIKE %s OR guide_summary LIKE %s)")
                keyword_pattern = f"%{keyword}%"
                params.extend([keyword_pattern, keyword_pattern])
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            sql = f"""
                SELECT guide_id, template_name, guide_summary, 
                       usage_frequency, created_at, last_updated, project_id
                FROM report_guide_templates
                WHERE {where_clause}
                ORDER BY usage_frequency DESC, last_updated DESC
                LIMIT %s
            """
            
            params.append(limit)
            cursor.execute(sql, params)
            results = cursor.fetchall()
            
            self.logger.info(f"✅ 搜索模板成功 (共 {len(results)} 个)")
            return results
            
        except Exception as e:
            self.logger.error(f"❌ 搜索模板失败: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def close(self):
        """关闭数据库连接"""
        if self._connection and self._connection.open:
            self._connection.close()
            self.logger.info("🔌 MySQL 连接已关闭")


# 全局单例
_template_db_client = None

def get_template_db_client() -> TemplateDBClient:
    """获取模板数据库客户端单例"""
    global _template_db_client
    if _template_db_client is None:
        _template_db_client = TemplateDBClient()
    return _template_db_client

