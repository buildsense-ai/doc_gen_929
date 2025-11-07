"""
MySQL 数据库配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

def get_mysql_config() -> dict:
    """
    获取 MySQL 配置
    从环境变量中读取数据库连接信息
    """
    # 从环境变量读取配置
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_port = os.getenv("MYSQL_PORT")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_database = os.getenv("MYSQL_DATABASE")
    mysql_charset = os.getenv("MYSQL_CHARSET", "utf8mb4")
    
    # 检查必需的配置项
    if not all([mysql_host, mysql_port, mysql_user, mysql_password, mysql_database]):
        raise ValueError(
            "MySQL配置不完整，请检查 .env 文件中的以下配置项:\n"
            "MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE"
        )
    
    return {
        "host": mysql_host,
        "port": int(mysql_port),
        "user": mysql_user,
        "password": mysql_password,
        "database": mysql_database,
        "charset": mysql_charset,
    }

