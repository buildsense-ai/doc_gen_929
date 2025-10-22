"""
OpenRouter客户端 - 连接模型
"""

import requests
import json
import logging
import time
import ssl
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
from config.settings import get_config

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(InsecureRequestWarning)

class OpenRouterClient:
    """
    OpenRouter客户端
    
    用于连接OpenRouter平台的DeepSeek模型
    增强版：支持SSL错误处理、重试机制和连接优化
    """
    
    def __init__(self):
        self.config = get_config()['openrouter']
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # OpenRouter需要有效的API密钥；没有密钥时立即提示，避免无意义的请求
        self.api_key = (self.config.get("api_key") or "").strip()
        if not self.api_key:
            raise RuntimeError(
                "OpenRouter API 密钥未配置。请在环境变量 OPENROUTER_API_KEY 或 .env 文件中设置有效的密钥。"
            )
        
        # 设置请求头
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://github.com/your-repo',  # 可选：添加引用来源
            'X-Title': 'Gauz-Document-Agent',  # 可选：添加应用标题
            'Connection': 'keep-alive',  # 保持连接
            'User-Agent': 'Gauz-Document-Agent/1.0'  # 添加User-Agent
        }
        
        # 创建会话并配置重试策略
        self.session = self._create_robust_session()
        
    def _create_robust_session(self):
        """
        创建具有robust配置的请求会话
        
        Returns:
            requests.Session: 配置好的会话对象
        """
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 总重试次数
            backoff_factor=1,  # 重试间隔倍数
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
            allowed_methods=["POST"],  # 允许重试的HTTP方法
        )
        
        # 创建适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,  # 连接池大小
            pool_maxsize=10,  # 最大连接数
            pool_block=False  # 非阻塞
        )
        
        # 挂载适配器
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置请求头
        session.headers.update(self.headers)
        
        return session
        
    def generate(self, prompt: str, max_tokens: Optional[int] = None, 
                temperature: Optional[float] = None, max_retries: int = 3) -> str:
        """
        生成文本 (增强版：支持SSL错误重试和更robust的错误处理)
        
        Args:
            prompt: 输入提示
            max_tokens: 最大token数
            temperature: 温度参数
            max_retries: 最大重试次数
            
        Returns:
            str: 生成的文本
        """
        
        # 准备请求数据
        data = {
            'model': self.config['model'],
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'max_tokens': max_tokens or self.config['max_tokens'],
            'temperature': temperature or self.config['temperature']
        }
        
        self.logger.info(f"Sending request to OpenRouter: {self.config['model']}")
        
        for attempt in range(max_retries):
            try:
                # 发送请求
                response = self.session.post(
                    f"{self.config['base_url']}/chat/completions",
                    json=data,
                    timeout=(30, self.config['timeout']),  # (连接超时, 读取超时)
                    verify=True,  # 验证SSL证书
                    stream=False
                )
                
                # 检查响应状态
                if response.status_code != 200:
                    error_msg = f"OpenRouter API error: {response.status_code} - {response.text}"
                    self.logger.error(error_msg)
                    
                    # 对于某些错误状态码，直接返回而不重试
                    if response.status_code in [401, 403, 404]:
                        raise RuntimeError(
                            "OpenRouter API 身份验证失败，请确认 OPENROUTER_API_KEY 是否正确。"
                        )
                    
                    # 对于其他错误，如果不是最后一次尝试，则继续重试
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 递增等待时间
                        self.logger.info(f"等待 {wait_time} 秒后重试... (尝试 {attempt + 2}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        return f"API call failed after {max_retries} attempts: {response.status_code}"
                
                # 解析响应
                result = response.json()
                
                if 'choices' not in result or not result['choices']:
                    self.logger.error(f"OpenRouter response format error: {result}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        return "Response format error"
                
                content = result['choices'][0]['message']['content']
                
                # 记录使用情况
                if 'usage' in result:
                    usage = result['usage']
                    self.logger.info(f"Token usage: {usage}")
                
                self.logger.info(f"✅ OpenRouter API调用成功 (尝试 {attempt + 1}/{max_retries})")
                return content
                
            except requests.exceptions.SSLError as e:
                error_msg = f"SSL connection error (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                
                if attempt < max_retries - 1:
                    # SSL错误的特殊处理：重新创建session
                    self.logger.info("SSL错误，重新创建连接会话...")
                    self.session.close()
                    time.sleep(3)  # 等待更长时间
                    self.session = self._create_robust_session()
                    continue
                else:
                    return f"SSL connection failed after {max_retries} attempts: {e}"
                    
            except requests.exceptions.Timeout as e:
                error_msg = f"Request timeout (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    self.logger.info(f"超时错误，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Request timeout after {max_retries} attempts"
                    
            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3  # 连接错误等待更长时间
                    self.logger.info(f"连接错误，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Connection failed after {max_retries} attempts: {e}"
                    
            except requests.exceptions.RequestException as e:
                error_msg = f"Request exception (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    self.logger.info(f"请求异常，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Request exception after {max_retries} attempts: {e}"
                    
            except json.JSONDecodeError as e:
                error_msg = f"JSON parse error (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.warning(error_msg)
                
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                else:
                    return f"Response parse error after {max_retries} attempts"
                    
            except Exception as e:
                error_msg = f"Unexpected error (尝试 {attempt + 1}/{max_retries}): {e}"
                self.logger.error(error_msg)
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    self.logger.info(f"未知错误，等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"Unexpected error after {max_retries} attempts: {e}"
        
        # 如果所有重试都失败，返回错误信息
        return f"All {max_retries} attempts failed"
    
    def test_connection(self) -> bool:
        """
        测试连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            test_response = self.generate("Please reply 'success'", max_tokens=10)
            success = "success" in test_response.lower() or "ok" in test_response.lower()
            
            if success:
                self.logger.info("✅ OpenRouter连接测试成功")
            else:
                self.logger.warning(f"❌ OpenRouter连接测试失败: {test_response}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息
        
        Returns:
            Dict: 模型信息
        """
        return {
            'model': self.config['model'],
            'base_url': self.config['base_url'],
            'max_tokens': self.config['max_tokens'],
            'temperature': self.config['temperature'],
            'timeout': self.config['timeout']
        }
        
    def close(self):
        """
        关闭会话连接
        """
        if hasattr(self, 'session'):
            self.session.close()
            self.logger.info("OpenRouter客户端会话已关闭")
            
    def __del__(self):
        """
        析构函数：确保会话被正确关闭
        """
        self.close() 
