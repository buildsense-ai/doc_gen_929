#!/usr/bin/env python3
"""
Document_Agent高级智能速率控制系统

针对长文档生成系统优化的智能速率控制器
"""

import time
import threading
import logging
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import statistics
import json

class ErrorType(Enum):
    """错误类型枚举"""
    RATE_LIMIT = "rate_limit"      # 429 - 速率限制
    SERVER_ERROR = "server_error"   # 5xx - 服务器错误
    TIMEOUT = "timeout"            # 超时错误
    NETWORK = "network"            # 网络错误
    CLIENT_ERROR = "client_error"   # 4xx - 客户端错误
    UNKNOWN = "unknown"            # 未知错误

@dataclass
class RequestRecord:
    """请求记录"""
    timestamp: float
    success: bool
    error_type: Optional[ErrorType] = None
    response_time: float = 0.0
    status_code: Optional[int] = None
    agent_type: str = "unknown"

@dataclass
class RateLimitStats:
    """速率限制统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    current_delay: float = 0.0
    success_rate: float = 0.0
    error_breakdown: Dict[ErrorType, int] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)
    agent_type: str = "unknown"

class DocumentAgentRateLimiter:
    """文档生成专用智能速率控制器"""
    
    def __init__(self, 
                 agent_type: str = "unknown",
                 base_delay: float = 1.0,
                 min_delay: float = 0.1,
                 max_delay: float = 30.0,
                 window_size: int = 50,
                 time_window: int = 300,  # 5分钟
                 aggressive_mode: bool = False):
        """
        初始化文档生成专用速率控制器
        
        Args:
            agent_type: Agent类型标识
            base_delay: 基础延迟时间（秒）
            min_delay: 最小延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            window_size: 滑动窗口大小
            time_window: 时间窗口大小（秒）
            aggressive_mode: 是否启用激进模式（更快的调整）
        """
        self.agent_type = agent_type
        self.base_delay = base_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.window_size = window_size
        self.time_window = time_window
        self.aggressive_mode = aggressive_mode
        
        # 核心状态
        self.current_delay = base_delay
        self.adaptive_factor = 1.0
        
        # 请求历史记录（滑动窗口）
        self.request_history = deque(maxlen=window_size)
        
        # 时间窗口统计
        self.time_window_records = deque()
        
        # 错误统计
        self.error_counts = defaultdict(int)
        self.consecutive_errors = 0
        self.consecutive_successes = 0
        
        # 性能统计
        self.response_times = deque(maxlen=50)
        self.last_adjustment_time = time.time()
        
        # 线程安全
        self.lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(f"{__name__}.{agent_type}")
        
        # 统计信息
        self.stats = RateLimitStats(agent_type=agent_type)
        
        # 学习参数
        self.learning_rate = 0.1
        self.stability_threshold = 0.95  # 稳定性阈值
        
        # 文档生成特定配置
        self.document_generation_config = {
            'content_generator_agent': {
                'target_success_rate': 0.95,
                'max_delay_multiplier': 3.0,
                'response_time_weight': 0.3
            },
            'orchestrator_agent': {
                'target_success_rate': 0.98,
                'max_delay_multiplier': 2.0,
                'response_time_weight': 0.2
            },
            'react_agent': {
                'target_success_rate': 0.90,
                'max_delay_multiplier': 4.0,
                'response_time_weight': 0.4
            }
        }
        
        self.agent_config = self.document_generation_config.get(
            agent_type, 
            self.document_generation_config['content_generator_agent']
        )
        
        self.logger.info(f"文档生成智能速率控制器初始化: {agent_type}, base_delay={base_delay}s")

    def get_delay(self) -> float:
        """获取当前延迟时间"""
        with self.lock:
            # 清理过期记录
            self._cleanup_expired_records()
            
            # 计算当前延迟
            delay = self._calculate_adaptive_delay()
            
            # 应用限制
            delay = max(self.min_delay, min(self.max_delay, delay))
            
            self.current_delay = delay
            self.stats.current_delay = delay
            
            return delay

    def record_request(self, success: bool, response_time: float = 0.0, 
                      status_code: Optional[int] = None, 
                      error_type: Optional[ErrorType] = None):
        """记录请求结果"""
        with self.lock:
            timestamp = time.time()
            
            # 创建请求记录
            record = RequestRecord(
                timestamp=timestamp,
                success=success,
                error_type=error_type,
                response_time=response_time,
                status_code=status_code,
                agent_type=self.agent_type
            )
            
            # 添加到历史记录
            self.request_history.append(record)
            self.time_window_records.append(record)
            
            # 更新连续计数
            if success:
                self.consecutive_successes += 1
                self.consecutive_errors = 0
            else:
                self.consecutive_errors += 1
                self.consecutive_successes = 0
                if error_type:
                    self.error_counts[error_type] += 1
            
            # 记录响应时间
            if response_time > 0:
                self.response_times.append(response_time)
            
            # 更新统计信息
            self._update_stats()
            
            # 触发自适应调整
            self._adaptive_adjustment()
            
            self.logger.debug(f"记录请求: success={success}, delay={self.current_delay:.2f}s")

    def _calculate_adaptive_delay(self) -> float:
        """计算自适应延迟 - 针对文档生成优化"""
        if not self.request_history:
            return self.base_delay
        
        # 基础延迟计算
        base = self.base_delay * self.adaptive_factor
        
        # 成功率调整
        success_rate = self._get_recent_success_rate()
        success_adjustment = self._calculate_success_rate_adjustment(success_rate)
        
        # 错误类型调整
        error_adjustment = self._calculate_error_type_adjustment()
        
        # 响应时间调整（针对文档生成优化权重）
        response_time_adjustment = self._calculate_response_time_adjustment()
        
        # 连续错误调整
        consecutive_adjustment = self._calculate_consecutive_adjustment()
        
        # 时间趋势调整
        trend_adjustment = self._calculate_trend_adjustment()
        
        # 文档生成特定的权重配置
        response_weight = self.agent_config['response_time_weight']
        
        # 综合调整（针对文档生成优化）
        total_adjustment = (
            success_adjustment * 0.35 +           # 成功率权重提高
            error_adjustment * 0.25 +             # 错误类型权重
            response_time_adjustment * response_weight +  # 动态响应时间权重
            consecutive_adjustment * 0.15 +       # 连续性权重
            trend_adjustment * 0.1               # 趋势权重
        )
        
        # 应用调整
        adjusted_delay = base * (1 + total_adjustment)
        
        # 文档生成特定的最大延迟限制
        max_allowed = self.base_delay * self.agent_config['max_delay_multiplier']
        adjusted_delay = min(adjusted_delay, max_allowed)
        
        self.logger.debug(f"延迟计算({self.agent_type}): base={base:.2f}, 调整={total_adjustment:.3f}, 结果={adjusted_delay:.2f}")
        
        return adjusted_delay

    def _calculate_success_rate_adjustment(self, success_rate: float) -> float:
        """基于成功率计算调整系数 - 文档生成优化版"""
        target_rate = self.agent_config['target_success_rate']
        
        if success_rate >= target_rate:
            # 达到目标成功率：降低延迟
            excess = success_rate - target_rate
            max_excess = 1.0 - target_rate
            if max_excess > 0:
                return -0.3 * (excess / max_excess)
            return -0.1
        elif success_rate >= target_rate - 0.1:
            # 接近目标：小幅调整
            deficit = target_rate - success_rate
            return 0.1 * (deficit / 0.1)
        elif success_rate >= target_rate - 0.2:
            # 较低成功率：增加延迟
            deficit = target_rate - success_rate
            return 0.4 * (deficit / 0.2)
        else:
            # 很低成功率：大幅增加延迟
            deficit = target_rate - success_rate
            return 0.6 * min(1.0, deficit / 0.3)

    def _calculate_error_type_adjustment(self) -> float:
        """基于错误类型计算调整系数 - 文档生成优化版"""
        if not self.request_history:
            return 0.0
        
        recent_errors = [r for r in list(self.request_history)[-20:] if not r.success]
        if not recent_errors:
            return 0.0
        
        adjustment = 0.0
        
        # 文档生成系统的错误权重优化
        error_weights = {
            ErrorType.RATE_LIMIT: 1.0,     # 速率限制：最高优先级
            ErrorType.SERVER_ERROR: 0.5,    # 服务器错误：中等增加
            ErrorType.TIMEOUT: 0.4,         # 超时：中等增加（文档生成耗时长）
            ErrorType.NETWORK: 0.3,         # 网络错误：轻微增加
            ErrorType.CLIENT_ERROR: 0.1,    # 客户端错误：几乎不调整
            ErrorType.UNKNOWN: 0.3          # 未知错误：中等增加
        }
        
        for error in recent_errors:
            if error.error_type:
                weight = error_weights.get(error.error_type, 0.3)
                adjustment += weight
        
        return min(1.0, adjustment / len(recent_errors))

    def _calculate_response_time_adjustment(self) -> float:
        """基于响应时间计算调整系数 - 文档生成优化版"""
        if len(self.response_times) < 5:
            return 0.0
        
        avg_response_time = statistics.mean(self.response_times)
        recent_response_time = statistics.mean(list(self.response_times)[-5:])
        
        # 文档生成系统的响应时间阈值调整
        slow_threshold_multiplier = 2.0  # 2倍平均时间视为慢
        very_slow_threshold_multiplier = 3.0  # 3倍平均时间视为很慢
        
        if recent_response_time > avg_response_time * very_slow_threshold_multiplier:
            return 0.4  # 非常慢：大幅增加延迟
        elif recent_response_time > avg_response_time * slow_threshold_multiplier:
            return 0.2  # 较慢：中等增加延迟
        elif recent_response_time > avg_response_time * 1.3:
            return 0.1  # 稍慢：小幅增加
        elif recent_response_time < avg_response_time * 0.7:
            return -0.1  # 快速：可以减少延迟
        
        return 0.0

    def _calculate_consecutive_adjustment(self) -> float:
        """基于连续错误/成功计算调整系数 - 文档生成优化版"""
        if self.consecutive_errors >= 3:  # 文档生成降低连续错误阈值
            return 0.3 + (self.consecutive_errors - 3) * 0.1
        elif self.consecutive_errors >= 2:
            return 0.2
        elif self.consecutive_successes >= 15:  # 文档生成调整成功阈值
            return -0.2
        elif self.consecutive_successes >= 8:
            return -0.1
        
        return 0.0

    def _calculate_trend_adjustment(self) -> float:
        """基于趋势计算调整系数"""
        if len(self.request_history) < 10:
            return 0.0
        
        recent_records = list(self.request_history)[-10:]
        first_half_success = sum(1 for r in recent_records[:5] if r.success) / 5
        second_half_success = sum(1 for r in recent_records[5:] if r.success) / 5
        
        trend = second_half_success - first_half_success
        
        # 趋势改善：降低延迟，趋势恶化：增加延迟
        return -trend * 0.15  # 文档生成降低趋势影响

    def _adaptive_adjustment(self):
        """自适应调整adaptive_factor"""
        current_time = time.time()
        
        # 至少间隔5秒才调整
        if current_time - self.last_adjustment_time < 5:
            return
        
        success_rate = self._get_recent_success_rate()
        target_rate = self.agent_config['target_success_rate']
        
        # 根据性能调整学习率
        if success_rate >= target_rate:
            # 性能良好：激进调整
            adjustment_rate = self.learning_rate * (2 if self.aggressive_mode else 1.2)
            self.adaptive_factor *= (1 - adjustment_rate * 0.5)
        elif success_rate < target_rate - 0.1:
            # 性能较差：保守调整
            adjustment_rate = self.learning_rate * 1.5
            self.adaptive_factor *= (1 + adjustment_rate)
        
        # 限制adaptive_factor范围
        self.adaptive_factor = max(0.2, min(3.0, self.adaptive_factor))
        self.last_adjustment_time = current_time
        
        self.logger.debug(f"自适应调整({self.agent_type}): factor={self.adaptive_factor:.3f}, success_rate={success_rate:.3f}")

    def _get_recent_success_rate(self) -> float:
        """获取最近的成功率"""
        if not self.request_history:
            return 1.0
        
        recent_count = min(15, len(self.request_history))  # 文档生成使用较小窗口
        recent_records = list(self.request_history)[-recent_count:]
        successes = sum(1 for r in recent_records if r.success)
        
        return successes / recent_count

    def _cleanup_expired_records(self):
        """清理过期的时间窗口记录"""
        current_time = time.time()
        cutoff_time = current_time - self.time_window
        
        while self.time_window_records and self.time_window_records[0].timestamp < cutoff_time:
            self.time_window_records.popleft()

    def _update_stats(self):
        """更新统计信息"""
        self.stats.total_requests = len(self.request_history)
        self.stats.successful_requests = sum(1 for r in self.request_history if r.success)
        self.stats.failed_requests = self.stats.total_requests - self.stats.successful_requests
        
        if self.stats.total_requests > 0:
            self.stats.success_rate = self.stats.successful_requests / self.stats.total_requests
        
        if self.response_times:
            self.stats.avg_response_time = statistics.mean(self.response_times)
        
        # 错误分类统计
        self.stats.error_breakdown = dict(self.error_counts)
        self.stats.last_updated = time.time()

    def get_stats(self) -> RateLimitStats:
        """获取统计信息"""
        with self.lock:
            return self.stats

    def get_performance_report(self) -> Dict:
        """获取性能报告"""
        with self.lock:
            self._cleanup_expired_records()
            
            recent_success_rate = self._get_recent_success_rate()
            window_requests = len(self.time_window_records)
            
            # 计算趋势
            trend = "stable"
            if len(self.request_history) >= 10:
                old_success = sum(1 for r in list(self.request_history)[-10:-5] if r.success) / 5
                new_success = sum(1 for r in list(self.request_history)[-5:] if r.success) / 5
                diff = new_success - old_success
                
                if diff > 0.1:
                    trend = "improving"
                elif diff < -0.1:
                    trend = "declining"
            
            return {
                "agent_type": self.agent_type,
                "current_delay": self.current_delay,
                "adaptive_factor": self.adaptive_factor,
                "recent_success_rate": recent_success_rate,
                "overall_success_rate": self.stats.success_rate,
                "consecutive_errors": self.consecutive_errors,
                "consecutive_successes": self.consecutive_successes,
                "window_requests": window_requests,
                "avg_response_time": self.stats.avg_response_time,
                "error_breakdown": dict(self.error_counts),
                "trend": trend,
                "performance_level": self._assess_performance_level(),
                "recommendations": self._generate_recommendations(),
                "target_success_rate": self.agent_config['target_success_rate']
            }

    def _assess_performance_level(self) -> str:
        """评估性能水平"""
        success_rate = self._get_recent_success_rate()
        target_rate = self.agent_config['target_success_rate']
        
        if success_rate >= target_rate:
            return "excellent"
        elif success_rate >= target_rate - 0.05:
            return "good"
        elif success_rate >= target_rate - 0.15:
            return "fair"
        else:
            return "poor"

    def _generate_recommendations(self) -> List[str]:
        """生成优化建议 - 文档生成系统专用"""
        recommendations = []
        success_rate = self._get_recent_success_rate()
        target_rate = self.agent_config['target_success_rate']
        
        if success_rate < target_rate - 0.1:
            recommendations.append(f"成功率({success_rate:.1%})低于目标({target_rate:.1%})，建议增加延迟")
            
        if self.consecutive_errors > 3:
            recommendations.append("连续错误较多，检查网络或API服务状态")
            
        if ErrorType.RATE_LIMIT in self.error_counts and self.error_counts[ErrorType.RATE_LIMIT] > 2:
            recommendations.append("频繁遇到速率限制，建议增加基础延迟")
            
        if self.current_delay > self.base_delay * 5:
            recommendations.append("延迟时间过长，检查API服务性能")
            
        if len(self.response_times) > 8:
            avg_response = statistics.mean(self.response_times)
            if avg_response > 15:  # 文档生成允许更长响应时间
                recommendations.append("响应时间过长，考虑优化请求内容或检查网络")
        
        if success_rate >= target_rate and self.current_delay > self.base_delay * 1.5:
            recommendations.append("性能良好，可以考虑降低延迟提高效率")
        
        if not recommendations:
            recommendations.append("系统运行良好")
            
        return recommendations

    def reset(self):
        """重置速率控制器状态"""
        with self.lock:
            self.current_delay = self.base_delay
            self.adaptive_factor = 1.0
            self.request_history.clear()
            self.time_window_records.clear()
            self.error_counts.clear()
            self.consecutive_errors = 0
            self.consecutive_successes = 0
            self.response_times.clear()
            self.last_adjustment_time = time.time()
            self.stats = RateLimitStats(agent_type=self.agent_type)
            
            self.logger.info(f"速率控制器已重置: {self.agent_type}")

    def export_config(self) -> Dict:
        """导出当前配置"""
        return {
            "agent_type": self.agent_type,
            "base_delay": self.base_delay,
            "min_delay": self.min_delay,
            "max_delay": self.max_delay,
            "window_size": self.window_size,
            "time_window": self.time_window,
            "aggressive_mode": self.aggressive_mode,
            "current_adaptive_factor": self.adaptive_factor,
            "learning_rate": self.learning_rate,
            "stability_threshold": self.stability_threshold,
            "agent_config": self.agent_config
        }

    def save_state(self, filepath: str):
        """保存状态到文件"""
        state = {
            "config": self.export_config(),
            "stats": {
                "total_requests": self.stats.total_requests,
                "success_rate": self.stats.success_rate,
                "avg_response_time": self.stats.avg_response_time,
                "error_breakdown": self.stats.error_breakdown
            },
            "timestamp": time.time()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"状态已保存到: {filepath}") 