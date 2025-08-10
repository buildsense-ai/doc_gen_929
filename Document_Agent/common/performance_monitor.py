#!/usr/bin/env python3
"""
Document_Agent 性能监控系统

提供全局性能监控、报告生成和优化建议
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class SystemPerformanceReport:
    """系统性能报告"""
    timestamp: datetime = field(default_factory=datetime.now)
    agents_status: Dict[str, Any] = field(default_factory=dict)
    global_metrics: Dict[str, Any] = field(default_factory=dict)
    optimization_suggestions: List[str] = field(default_factory=list)
    efficiency_score: float = 0.0
    
class DocumentAgentPerformanceMonitor:
    """文档生成系统性能监控器"""
    
    def __init__(self, concurrency_manager):
        self.concurrency_manager = concurrency_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.monitoring_start_time = time.time()
        
        # 监控配置
        self.performance_thresholds = {
            'excellent_success_rate': 0.95,
            'good_success_rate': 0.85,
            'poor_success_rate': 0.7,
            'max_acceptable_delay': 10.0,
            'high_delay_threshold': 5.0
        }
        
        self.logger.info("Document Agent 性能监控系统已启动")
    
    def generate_comprehensive_report(self) -> SystemPerformanceReport:
        """生成综合性能报告"""
        report = SystemPerformanceReport()
        
        # 获取所有Agent的性能数据
        global_report = self.concurrency_manager.get_performance_report()
        
        if 'agents' in global_report:
            report.agents_status = global_report['agents']
            report.global_metrics = global_report.get('summary', {})
        
        # 计算效率评分
        report.efficiency_score = self._calculate_efficiency_score(report.agents_status)
        
        # 生成优化建议
        report.optimization_suggestions = self._generate_global_optimization_suggestions(report.agents_status)
        
        return report
    
    def _calculate_efficiency_score(self, agents_status: Dict[str, Any]) -> float:
        """计算系统整体效率评分（0-100分）"""
        if not agents_status:
            return 0.0
        
        scores = []
        
        for agent_name, status in agents_status.items():
            agent_score = 0.0
            
            # 成功率评分（40%权重）
            success_rate = status.get('recent_success_rate', 0)
            if success_rate >= self.performance_thresholds['excellent_success_rate']:
                success_score = 100
            elif success_rate >= self.performance_thresholds['good_success_rate']:
                success_score = 80
            elif success_rate >= self.performance_thresholds['poor_success_rate']:
                success_score = 60
            else:
                success_score = max(0, success_rate * 60)
            
            agent_score += success_score * 0.4
            
            # 延迟评分（30%权重）
            current_delay = status.get('current_delay', 10)
            if current_delay <= 1.0:
                delay_score = 100
            elif current_delay <= self.performance_thresholds['high_delay_threshold']:
                delay_score = 80
            elif current_delay <= self.performance_thresholds['max_acceptable_delay']:
                delay_score = 60
            else:
                delay_score = max(20, 60 - (current_delay - 10) * 4)
            
            agent_score += delay_score * 0.3
            
            # 性能等级评分（20%权重）
            performance_level = status.get('performance_level', 'poor')
            level_scores = {
                'excellent': 100,
                'good': 80,
                'fair': 60,
                'poor': 30
            }
            agent_score += level_scores.get(performance_level, 30) * 0.2
            
            # 趋势评分（10%权重）
            trend = status.get('trend', 'stable')
            trend_scores = {
                'improving': 100,
                'stable': 75,
                'declining': 40
            }
            agent_score += trend_scores.get(trend, 50) * 0.1
            
            scores.append(agent_score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _generate_global_optimization_suggestions(self, agents_status: Dict[str, Any]) -> List[str]:
        """生成全局优化建议"""
        suggestions = []
        
        if not agents_status:
            suggestions.append("❌ 无法获取Agent状态，请检查智能速率控制是否正确配置")
            return suggestions
        
        # 分析各Agent状态
        poor_performers = []
        high_delay_agents = []
        declining_agents = []
        
        for agent_name, status in agents_status.items():
            success_rate = status.get('recent_success_rate', 0)
            current_delay = status.get('current_delay', 0)
            trend = status.get('trend', 'stable')
            performance_level = status.get('performance_level', 'poor')
            
            if performance_level == 'poor':
                poor_performers.append(agent_name)
            
            if current_delay > self.performance_thresholds['high_delay_threshold']:
                high_delay_agents.append((agent_name, current_delay))
            
            if trend == 'declining':
                declining_agents.append(agent_name)
        
        # 生成具体建议
        if poor_performers:
            suggestions.append(f"🔧 性能较差的Agent ({', '.join(poor_performers)})：建议检查网络连接和API服务状态")
        
        if high_delay_agents:
            high_delay_info = ', '.join([f"{name}({delay:.1f}s)" for name, delay in high_delay_agents])
            suggestions.append(f"⏰ 高延迟Agent ({high_delay_info})：考虑调整基础延迟配置或检查API响应时间")
        
        if declining_agents:
            suggestions.append(f"📉 性能下降的Agent ({', '.join(declining_agents)})：建议监控错误日志，可能需要重启或调整配置")
        
        # 全局优化建议
        avg_success_rate = sum(s.get('recent_success_rate', 0) for s in agents_status.values()) / len(agents_status)
        if avg_success_rate < self.performance_thresholds['good_success_rate']:
            suggestions.append("📊 整体成功率偏低：建议启用更保守的速率控制策略")
        elif avg_success_rate >= self.performance_thresholds['excellent_success_rate']:
            suggestions.append("🚀 整体性能优秀：可以考虑启用更激进的优化策略以提高效率")
        
        # 错误分析
        total_errors = {}
        for status in agents_status.values():
            for error_type, count in status.get('error_breakdown', {}).items():
                total_errors[error_type] = total_errors.get(error_type, 0) + count
        
        if total_errors:
            max_error_type = max(total_errors.items(), key=lambda x: x[1])
            if max_error_type[1] > 5:
                suggestions.append(f"🚨 频繁出现 {max_error_type[0]} 错误({max_error_type[1]}次)：建议检查对应的服务配置")
        
        if not suggestions:
            suggestions.append("✅ 系统运行状态良好，无需特殊优化")
        
        return suggestions
    
    def print_performance_dashboard(self):
        """打印性能仪表盘"""
        report = self.generate_comprehensive_report()
        
        print("\n" + "="*80)
        print("📊 Document Agent 智能速率控制性能仪表盘")
        print("="*80)
        print(f"📅 报告时间: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 系统效率评分: {report.efficiency_score:.1f}/100")
        
        # 全局指标
        if report.global_metrics:
            print(f"\n🌍 全局指标:")
            print(f"   总请求数: {report.global_metrics.get('total_requests', 0)}")
            print(f"   平均成功率: {report.global_metrics.get('avg_success_rate', 0):.1%}")
            print(f"   平均延迟: {report.global_metrics.get('avg_delay', 0):.2f}秒")
            print(f"   整体性能: {report.global_metrics.get('overall_performance', 'unknown')}")
            print(f"   活跃Agent数: {report.global_metrics.get('active_agents', 0)}")
        
        # 各Agent详细状态
        print(f"\n🤖 各Agent详细状态:")
        for agent_name, status in report.agents_status.items():
            performance_icons = {
                'excellent': '🚀',
                'good': '⚡',
                'fair': '⚠️',
                'poor': '🐌'
            }
            
            trend_icons = {
                'improving': '📈',
                'stable': '➡️',
                'declining': '📉'
            }
            
            perf_icon = performance_icons.get(status.get('performance_level', 'poor'), '❓')
            trend_icon = trend_icons.get(status.get('trend', 'stable'), '❓')
            
            print(f"   {perf_icon} {agent_name}:")
            print(f"      成功率: {status.get('recent_success_rate', 0):.1%} (目标: {status.get('target_success_rate', 0.95):.0%})")
            print(f"      当前延迟: {status.get('current_delay', 0):.2f}s")
            print(f"      自适应因子: {status.get('adaptive_factor', 1.0):.2f}")
            print(f"      趋势: {trend_icon} {status.get('trend', 'unknown')}")
            
            if status.get('error_breakdown'):
                error_summary = ', '.join([f"{k}:{v}" for k, v in status['error_breakdown'].items()])
                print(f"      错误分布: {error_summary}")
        
        # 优化建议
        print(f"\n💡 优化建议:")
        for i, suggestion in enumerate(report.optimization_suggestions, 1):
            print(f"   {i}. {suggestion}")
        
        print("="*80)
        
        return report
    
    def export_performance_data(self, filepath: str):
        """导出性能数据到文件"""
        report = self.generate_comprehensive_report()
        
        export_data = {
            "timestamp": report.timestamp.isoformat(),
            "efficiency_score": report.efficiency_score,
            "global_metrics": report.global_metrics,
            "agents_status": report.agents_status,
            "optimization_suggestions": report.optimization_suggestions,
            "monitoring_duration": time.time() - self.monitoring_start_time
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"性能数据已导出到: {filepath}")
        
        return filepath
    
    def get_alert_conditions(self) -> List[str]:
        """检查告警条件"""
        alerts = []
        report = self.generate_comprehensive_report()
        
        # 系统级告警
        if report.efficiency_score < 50:
            alerts.append(f"🚨 CRITICAL: 系统效率评分过低 ({report.efficiency_score:.1f}/100)")
        elif report.efficiency_score < 70:
            alerts.append(f"⚠️  WARNING: 系统效率评分偏低 ({report.efficiency_score:.1f}/100)")
        
        # Agent级告警
        for agent_name, status in report.agents_status.items():
            success_rate = status.get('recent_success_rate', 0)
            current_delay = status.get('current_delay', 0)
            
            if success_rate < self.performance_thresholds['poor_success_rate']:
                alerts.append(f"🚨 CRITICAL: {agent_name} 成功率过低 ({success_rate:.1%})")
            
            if current_delay > self.performance_thresholds['max_acceptable_delay']:
                alerts.append(f"⚠️  WARNING: {agent_name} 延迟过高 ({current_delay:.1f}s)")
        
        return alerts 