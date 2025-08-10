"""
客户端包初始化
"""

from .openrouter_client import OpenRouterClient
from .external_api_client import ExternalAPIClient, get_external_api_client

__all__ = ['OpenRouterClient', 'ExternalAPIClient', 'get_external_api_client'] 