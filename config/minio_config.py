#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinIO对象存储配置和客户端

提供文档上传到MinIO的功能，支持文件存储和URL生成
"""

import os
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class MinIOConfig:
    """MinIO配置类"""
    
    def __init__(self):
        # MinIO服务器配置
        self.endpoint = os.getenv('MINIO_ENDPOINT', '43.139.19.144:9000')
        self.access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self.secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
        self.secure = os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        
        # 存储桶配置
        self.bucket_name = os.getenv('MINIO_BUCKET_NAME', 'gauz-documents')
        self.region = os.getenv('MINIO_REGION', 'us-east-1')
        
        # URL有效期配置（默认7天=168小时；预签名模式有效）
        self.url_expiry_hours = int(os.getenv('MINIO_URL_EXPIRY_HOURS', '168'))
        
        # 文件路径前缀
        self.path_prefix = os.getenv('MINIO_PATH_PREFIX', 'documents')

        # 公开桶直链配置
        # 当 public_bucket 为 True 时，返回永久直链而非预签名URL
        self.public_bucket = os.getenv('MINIO_PUBLIC_BUCKET', 'false').lower() == 'true'
        # 可选：自定义直链基址（如走反向代理/CDN）；若未配置则使用 endpoint 推导
        # 示例：MINIO_PUBLIC_BASE_URL=http://43.139.19.144:9000
        self.public_base_url = os.getenv('MINIO_PUBLIC_BASE_URL', '').strip()

class MinIOClient:
    """MinIO客户端管理类"""
    
    def __init__(self):
        self.config = MinIOConfig()
        self.client: Optional[Minio] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化MinIO客户端"""
        try:
            self.client = Minio(
                endpoint=self.config.endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.secure
            )
            
            # 确保存储桶存在
            self._ensure_bucket_exists()
            
            logger.info(f"✅ MinIO客户端初始化成功")
            logger.info(f"   服务器: {self.config.endpoint}")
            logger.info(f"   存储桶: {self.config.bucket_name}")
            
        except Exception as e:
            logger.error(f"❌ MinIO客户端初始化失败: {e}")
            self.client = None
    
    def _ensure_bucket_exists(self):
        """确保存储桶存在"""
        if not self.client:
            return
        
        try:
            # 检查存储桶是否存在
            if not self.client.bucket_exists(self.config.bucket_name):
                # 创建存储桶
                self.client.make_bucket(
                    bucket_name=self.config.bucket_name,
                    location=self.config.region
                )
                logger.info(f"📁 创建存储桶: {self.config.bucket_name}")
            else:
                logger.info(f"📁 存储桶已存在: {self.config.bucket_name}")
                
        except S3Error as e:
            logger.error(f"❌ 存储桶操作失败: {e}")
            raise
    
    def is_available(self) -> bool:
        """检查MinIO服务是否可用"""
        if not self.client:
            return False
        
        try:
            # 尝试列出存储桶来测试连接
            self.client.bucket_exists(self.config.bucket_name)
            return True
        except Exception as e:
            logger.warning(f"⚠️ MinIO服务不可用: {e}")
            return False
    
    def upload_file(self, file_path: str, object_name: Optional[str] = None) -> Optional[str]:
        """
        上传文件到MinIO
        
        Args:
            file_path: 本地文件路径
            object_name: MinIO中的对象名称，如果为None则自动生成
            
        Returns:
            上传成功返回对象名称，失败返回None
        """
        if not self.client or not self.is_available():
            logger.error("❌ MinIO客户端不可用")
            return None
        
        if not os.path.exists(file_path):
            logger.error(f"❌ 文件不存在: {file_path}")
            return None
        
        try:
            # 生成对象名称
            if object_name is None:
                file_path_obj = Path(file_path)
                timestamp = file_path_obj.stem.split('_')[-1] if '_' in file_path_obj.stem else 'default'
                object_name = f"{self.config.path_prefix}/{timestamp}/{file_path_obj.name}"
            
            # 上传文件
            self.client.fput_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name,
                file_path=file_path
            )
            
            logger.info(f"✅ 文件上传成功: {object_name}")
            return object_name
            
        except S3Error as e:
            logger.error(f"❌ 文件上传失败: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 上传过程异常: {e}")
            return None
    
    def get_download_url(self, object_name: str) -> Optional[str]:
        """
        获取文件的公开直链URL（仅支持公开桶场景）
        
        Args:
            object_name: MinIO中的对象名称
            
        Returns:
            公开直链URL，失败返回None
        """
        if not self.client or not self.is_available():
            logger.error("❌ MinIO客户端不可用")
            return None
        
        try:
            scheme = 'https' if self.config.secure else 'http'
            if self.config.public_base_url:
                base = self.config.public_base_url.rstrip('/')
                if base.endswith(f"/{self.config.bucket_name}"):
                    direct_url = f"{base}/{object_name}"
                else:
                    direct_url = f"{base}/{self.config.bucket_name}/{object_name}"
            else:
                direct_url = f"{scheme}://{self.config.endpoint}/{self.config.bucket_name}/{object_name}"
            logger.info(f"🔗 生成直链URL: {direct_url}")
            return direct_url
        except Exception as e:
            logger.error(f"❌ URL生成异常: {e}")
            return None
    
    def upload_and_get_url(self, file_path: str, object_name: Optional[str] = None) -> Optional[str]:
        """
        上传文件并获取下载URL（一体化操作）
        
        Args:
            file_path: 本地文件路径
            object_name: MinIO中的对象名称
            
        Returns:
            下载URL，失败返回None
        """
        # 上传文件
        uploaded_object_name = self.upload_file(file_path, object_name)
        if not uploaded_object_name:
            return None
        
        # 获取下载URL
        return self.get_download_url(uploaded_object_name)
    
    def delete_file(self, object_name: str) -> bool:
        """
        删除MinIO中的文件
        
        Args:
            object_name: MinIO中的对象名称
            
        Returns:
            删除成功返回True，失败返回False
        """
        if not self.client or not self.is_available():
            return False
        
        try:
            self.client.remove_object(
                bucket_name=self.config.bucket_name,
                object_name=object_name
            )
            logger.info(f"🗑️ 文件删除成功: {object_name}")
            return True
            
        except S3Error as e:
            logger.error(f"❌ 文件删除失败: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 删除过程异常: {e}")
            return False
    
    def list_files(self, prefix: Optional[str] = None) -> list:
        """
        列出存储桶中的文件
        
        Args:
            prefix: 文件名前缀过滤
            
        Returns:
            文件对象列表
        """
        if not self.client or not self.is_available():
            return []
        
        try:
            objects = self.client.list_objects(
                bucket_name=self.config.bucket_name,
                prefix=prefix or self.config.path_prefix
            )
            
            return [obj.object_name for obj in objects]
            
        except S3Error as e:
            logger.error(f"❌ 列出文件失败: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ 列表操作异常: {e}")
            return []

# 全局MinIO客户端实例
minio_client = MinIOClient()

def get_minio_client() -> MinIOClient:
    """获取全局MinIO客户端实例"""
    return minio_client

def upload_document_files(file_paths: Dict[str, str], task_id: str) -> Dict[str, str]:
    """
    批量上传文档文件到MinIO
    
    Args:
        file_paths: 文件类型到文件路径的映射
        task_id: 任务ID，用于生成对象名称
        
    Returns:
        文件类型到下载URL的映射
    """
    client = get_minio_client()
    upload_results = {}
    
    if not client.is_available():
        logger.warning("⚠️ MinIO不可用，跳过文件上传")
        return {}
    
    for file_type, file_path in file_paths.items():
        if file_type == 'output_directory':
            continue
        
        if not os.path.exists(file_path):
            logger.warning(f"⚠️ 文件不存在，跳过: {file_path}")
            continue
        
        # 生成对象名称
        file_name = os.path.basename(file_path)
        object_name = f"documents/{task_id}/{file_type}_{file_name}"
        
        # 上传并获取URL
        download_url = client.upload_and_get_url(file_path, object_name)
        if download_url:
            upload_results[file_type] = download_url
            logger.info(f"📤 {file_type} 上传成功")
        else:
            logger.error(f"❌ {file_type} 上传失败: {file_path}")
    
    logger.info(f"📊 批量上传完成: {len(upload_results)}/{len([k for k in file_paths.keys() if k != 'output_directory'])} 个文件成功")
    
    return upload_results 