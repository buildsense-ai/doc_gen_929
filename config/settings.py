"""
多Agent文档生成系统配置 - 智能速率控制增强版
"""

import logging
from typing import Dict, Any, Optional
import sys
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# 添加Document_Agent路径以导入高级速率控制器
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Document_Agent'))

# 优先加载根目录下的.env，确保API密钥和其他配置在第一次读取前就位
_project_root = os.path.dirname(os.path.dirname(__file__))
_env_path = os.path.join(_project_root, '.env')
if load_dotenv and os.path.exists(_env_path):
    load_dotenv(dotenv_path=_env_path, override=True)

# 系统配置
SYSTEM_CONFIG = {
    # OpenRouter配置
    'openrouter': {
        'api_key': os.getenv('OPENROUTER_API_KEY', ''),
        'base_url': 'https://openrouter.ai/api/v1',
        'model': 'google/gemini-2.5-flash',
        'max_tokens': 10000,
        'temperature': 0.7,
        'timeout': 30
    },
    
    # 日志配置
    'logging': {
        'level': logging.INFO,
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file_path': None  # 设置为None表示只输出到控制台
    },
    
    # 智能速率控制配置（升级版）
    'smart_rate_control': {
        'enabled': True,  # 启用智能速率控制
        'orchestrator_agent': {
            'base_delay': 0.8,           # 基础延迟0.8秒（原来是4秒）
            'min_delay': 0.1,            # 最小延迟0.1秒
            'max_delay': 20.0,           # 最大延迟20秒
            'aggressive_mode': True,     # 启用激进模式
            'target_success_rate': 0.98, # 目标成功率98%
            'window_size': 30,           # 编排任务较少，窗口小一些
            'max_workers': 12,
            'description': '编排代理 - 智能速率控制，按大章节并行生成写作指导'
        },
        'react_agent': {
            'base_delay': 1.0,           # 基础延迟1秒
            'min_delay': 0.2,            # 最小延迟0.2秒
            'max_delay': 15.0,           # 最大延迟15秒
            'aggressive_mode': True,     # 启用激进模式
            'target_success_rate': 0.90, # 目标成功率90%（RAG查询容忍度高一些）
            'window_size': 50,           # RAG查询较多
            'max_workers': 12,
            'description': '检索代理 - 智能速率控制，按子章节并行执行ReAct循环'
        },
        'content_generator_agent': {
            'base_delay': 1.2,           # 基础延迟1.2秒（内容生成更谨慎）
            'min_delay': 0.3,            # 最小延迟0.3秒
            'max_delay': 25.0,           # 最大延迟25秒
            'aggressive_mode': False,    # 内容生成使用保守模式
            'target_success_rate': 0.95, # 目标成功率95%
            'window_size': 50,           # 内容生成任务较多
            'max_workers': 12,
            'description': '内容生成代理 - 智能速率控制，按子章节并行生成内容'
        }
    },
    
    # # 兼容性：保留旧配置（将被逐步废弃）
    # 'concurrency': {
    #     'orchestrator_agent': {
    #         'max_workers': 5,
    #         'description': '编排代理 - 按大章节并行生成写作指导'
    #     },
    #     'react_agent': {
    #         'max_workers': 5,
    #         'description': '检索代理 - 按子章节并行执行ReAct循环'
    #     },
    #     'content_generator_agent': {
    #         'max_workers': 12,
    #         'description': '内容生成代理 - 按子章节并行生成内容'
    #     },
    #     'rate_limiting': {
    #         'delay_between_requests': 4,  # 秒
    #         'description': '请求间隔控制，防止API超限'
    #     }
    # },
    
    # 文档生成配置
    'generation': {
        'max_sections': 50,
        'default_section_length': 1000,
        'parallel_generation': False,
        'max_retries': 3
    },
    
    # 质量控制配置
    'quality': {
        'min_quality_score': 0.8,
        'max_improvement_attempts': 3,
        'quality_dimensions': {
            'length': 0.15,
            'completeness': 0.25,
            'coherence': 0.20,
            'accuracy': 0.25,
            'readability': 0.15
        }
    },
    
    # Agent配置
    'agents': {
        'orchestrator': {
            'max_outline_depth': 4,
            'min_sections_per_chapter': 2,
            'max_sections_per_chapter': 10
        },
        'section_writer': {
            'max_query_rounds': 3,
            'max_queries_per_round': 5,
            'context_relevance_threshold': 0.7
        },
        'content_generator': {
            'max_content_length': 5000,
            'min_content_length': 200,
            'quality_check_rounds': 2
        }
    }
}


class SmartConcurrencyManager:
    """增强的智能并发管理器 - 集成高级速率控制"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or SYSTEM_CONFIG
        from threading import Lock
        self._locks = {}  # 为每个Agent创建独立的锁
        self._rate_limiters = {}  # 存储各个Agent的智能速率控制器
        
        # 初始化智能速率控制器
        self._initialize_smart_rate_limiters()
    
    def _initialize_smart_rate_limiters(self):
        """初始化智能速率控制器"""
        smart_config = self.config.get('smart_rate_control', {})
        
        if not smart_config.get('enabled', False):
            return
        
        try:
            from common.advanced_rate_limiter import DocumentAgentRateLimiter
            
            for agent_name, agent_config in smart_config.items():
                if agent_name == 'enabled':
                    continue
                    
                if isinstance(agent_config, dict) and 'base_delay' in agent_config:
                    rate_limiter = DocumentAgentRateLimiter(
                        agent_type=agent_name,
                        base_delay=agent_config.get('base_delay', 1.0),
                        min_delay=agent_config.get('min_delay', 0.1),
                        max_delay=agent_config.get('max_delay', 30.0),
                        window_size=agent_config.get('window_size', 50),
                        aggressive_mode=agent_config.get('aggressive_mode', False)
                    )
                    self._rate_limiters[agent_name] = rate_limiter
                    
        except ImportError:
            # 如果无法导入高级速率控制器，继续使用旧版本
            pass
    
    def get_rate_limiter(self, agent_name: str):
        """获取指定Agent的智能速率控制器"""
        return self._rate_limiters.get(agent_name)
    
    def has_smart_rate_control(self, agent_name: str) -> bool:
        """检查指定Agent是否启用了智能速率控制"""
        return agent_name in self._rate_limiters
    
    def get_max_workers(self, agent_name: str) -> int:
        """获取指定Agent的最大线程数"""
        # 优先从智能速率控制配置获取
        smart_config = self.config.get('smart_rate_control', {})
        if agent_name in smart_config and 'max_workers' in smart_config[agent_name]:
            return smart_config[agent_name]['max_workers']
        
        # 兼容性：从旧配置获取
        agent_config = self.config.get('concurrency', {}).get(agent_name, {})
        return agent_config.get('max_workers', 1)
    
    def set_max_workers(self, agent_name: str, max_workers: int):
        """设置指定Agent的最大线程数"""
        # 更新智能速率控制配置
        smart_config = self.config.setdefault('smart_rate_control', {})
        if agent_name not in smart_config:
            smart_config[agent_name] = {}
        smart_config[agent_name]['max_workers'] = max_workers
        
        # 兼容性：同时更新旧配置
        concurrency_config = self.config.setdefault('concurrency', {})
        if agent_name not in concurrency_config:
            concurrency_config[agent_name] = {}
        concurrency_config[agent_name]['max_workers'] = max_workers
    
    def get_rate_limit_delay(self, agent_name: str = None) -> float:
        """获取请求间隔时间"""
        if agent_name and self.has_smart_rate_control(agent_name):
            # 使用智能速率控制器的动态延迟
            rate_limiter = self.get_rate_limiter(agent_name)
            if rate_limiter:
                return rate_limiter.get_delay()
        
        # 兼容性：返回固定延迟
        return self.config.get('concurrency', {}).get('rate_limiting', {}).get('delay_between_requests', 4)
    
    def set_rate_limit_delay(self, delay: float, agent_name: str = None):
        """设置请求间隔时间"""
        if agent_name and self.has_smart_rate_control(agent_name):
            # 对智能速率控制器，这里可以调整基础延迟
            smart_config = self.config.setdefault('smart_rate_control', {})
            if agent_name in smart_config:
                smart_config[agent_name]['base_delay'] = delay
        
        # 兼容性：更新旧配置
        if 'rate_limiting' not in self.config.setdefault('concurrency', {}):
            self.config['concurrency']['rate_limiting'] = {}
        self.config['concurrency']['rate_limiting']['delay_between_requests'] = delay
    
    def record_api_request(self, agent_name: str, success: bool, response_time: float = 0.0, 
                          status_code: int = None, error_type: str = None):
        """记录API请求结果到智能速率控制器"""
        rate_limiter = self.get_rate_limiter(agent_name)
        if rate_limiter:
            # 转换错误类型
            error_type_enum = None
            if error_type:
                from common.advanced_rate_limiter import ErrorType
                error_type_mapping = {
                    'rate_limit': ErrorType.RATE_LIMIT,
                    'server_error': ErrorType.SERVER_ERROR,
                    'timeout': ErrorType.TIMEOUT,
                    'network': ErrorType.NETWORK,
                    'client_error': ErrorType.CLIENT_ERROR,
                    'unknown': ErrorType.UNKNOWN
                }
                error_type_enum = error_type_mapping.get(error_type, ErrorType.UNKNOWN)
            
            rate_limiter.record_request(
                success=success,
                response_time=response_time,
                status_code=status_code,
                error_type=error_type_enum
            )
    
    def get_performance_report(self, agent_name: str = None) -> Dict[str, Any]:
        """获取性能报告"""
        if agent_name:
            rate_limiter = self.get_rate_limiter(agent_name)
            if rate_limiter:
                return rate_limiter.get_performance_report()
            else:
                return {"error": f"Agent {agent_name} 未启用智能速率控制"}
        
        # 获取所有Agent的性能报告
        reports = {}
        for agent_name, rate_limiter in self._rate_limiters.items():
            reports[agent_name] = rate_limiter.get_performance_report()
        
        return {
            "agents": reports,
            "summary": self._generate_global_summary(reports)
        }
    
    def _generate_global_summary(self, reports: Dict[str, Any]) -> Dict[str, Any]:
        """生成全局性能总结"""
        if not reports:
            return {}
        
        total_requests = sum(r.get('window_requests', 0) for r in reports.values())
        avg_success_rate = sum(r.get('recent_success_rate', 0) for r in reports.values()) / len(reports)
        avg_delay = sum(r.get('current_delay', 0) for r in reports.values()) / len(reports)
        
        performance_levels = [r.get('performance_level', 'unknown') for r in reports.values()]
        overall_performance = 'poor'
        if all(level in ['excellent', 'good'] for level in performance_levels):
            overall_performance = 'excellent'
        elif any(level == 'good' for level in performance_levels):
            overall_performance = 'good'
        elif any(level == 'fair' for level in performance_levels):
            overall_performance = 'fair'
        
        return {
            "total_requests": total_requests,
            "avg_success_rate": avg_success_rate,
            "avg_delay": avg_delay,
            "overall_performance": overall_performance,
            "active_agents": len(reports)
        }
    
    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有并发设置"""
        return self.config.copy()
    
    def update_settings(self, new_settings: Dict[str, Any]):
        """批量更新并发设置"""
        self.config.update(new_settings)
        # 重新初始化智能速率控制器
        self._initialize_smart_rate_limiters()
    
    def get_lock(self, agent_name: str):
        """获取指定Agent的线程锁"""
        from threading import Lock
        if agent_name not in self._locks:
            self._locks[agent_name] = Lock()
        return self._locks[agent_name]
    
    def print_settings(self):
        """打印当前并发设置"""
        print("🔧 智能并发管理设置:")
        print("=" * 60)
        
        smart_config = self.config.get('smart_rate_control', {})
        if smart_config.get('enabled', False):
            print("🚀 智能速率控制: 已启用")
            for agent_name, agent_config in smart_config.items():
                if agent_name == 'enabled':
                    continue
                if isinstance(agent_config, dict):
                    max_workers = agent_config.get('max_workers', 1)
                    base_delay = agent_config.get('base_delay', 1.0)
                    target_rate = agent_config.get('target_success_rate', 0.95)
                    aggressive = "激进" if agent_config.get('aggressive_mode', False) else "保守"
                    description = agent_config.get('description', '')
                    
                    print(f"🧵 {agent_name}: {max_workers}线程 | 基础延迟:{base_delay}s | 目标成功率:{target_rate:.0%} | {aggressive}模式")
                    print(f"   📝 {description}")
        else:
            print("⚠️  智能速率控制: 已禁用，使用传统模式")
            # 显示传统配置
            concurrency_config = self.config.get('concurrency', {})
            for agent_name, settings in concurrency_config.items():
                if agent_name == 'rate_limiting':
                    delay = settings.get('delay_between_requests', 4)
                    print(f"⏱️  请求间隔: {delay}秒")
                elif 'max_workers' in settings:
                    max_workers = settings['max_workers']
                    description = settings.get('description', '')
                    print(f"🧵 {agent_name}: {max_workers} 线程 - {description}")
        
        print("=" * 60)

    def enable_smart_rate_control(self):
        """启用智能速率控制"""
        self.config.setdefault('smart_rate_control', {})['enabled'] = True
        self._initialize_smart_rate_limiters()
        print("✅ 智能速率控制已启用")

    def disable_smart_rate_control(self):
        """禁用智能速率控制"""
        self.config.setdefault('smart_rate_control', {})['enabled'] = False
        self._rate_limiters.clear()
        print("⚠️  智能速率控制已禁用")


# 兼容性：保留旧的ConcurrencyManager作为别名
ConcurrencyManager = SmartConcurrencyManager


def get_config() -> Dict[str, Any]:
    """获取系统配置"""
    return SYSTEM_CONFIG

def get_concurrency_manager() -> SmartConcurrencyManager:
    """获取智能并发管理器实例"""
    return SmartConcurrencyManager()

def setup_logging():
    """设置日志系统 - 支持UTF-8编码"""
    config = SYSTEM_CONFIG['logging']
    
    # 预保存需保留的特殊handler（来自API服务的SSE桥接），避免后续force=True清空后丢失
    try:
        existing_handlers = list(logging.getLogger().handlers)
        preserved_handlers = [
            h for h in existing_handlers
            if h.__class__.__name__ in ("TaskLogHandler", "TaskScopedHandler")
        ]
    except Exception:
        preserved_handlers = []

    # 创建formatter
    formatter = logging.Formatter(config['format'])
    
    # 创建handlers
    handlers = []
    
    # 文件handler（如果指定了文件路径）
    if config['file_path']:
        file_handler = logging.FileHandler(
            config['file_path'], 
            mode='a', 
            encoding='utf-8'  # 支持UTF-8编码
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # 控制台handler（固定到原始stdout，避免运行时替换sys.stdout导致控制台日志丢失）
    console_handler = logging.StreamHandler(getattr(sys, '__stdout__', sys.stdout))
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=config['level'],
        handlers=handlers,
        force=True  # 强制重新配置日志
    )
    # 重新附加被保留的特殊handler
    try:
        root_logger = logging.getLogger()
        for h in preserved_handlers:
            try:
                root_logger.addHandler(h)
            except Exception:
                pass
    except Exception:
        pass
    
    # 获取根日志记录器并设置立即刷新
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.flush()
        # 设置立即刷新，确保多线程环境下日志及时显示
        if hasattr(handler, 'stream'):
            handler.stream.flush()
    
    # 设置第三方库日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING) 
