"""
运行ReAct Agent处理报告指南
此版本调用一个封装了并行逻辑的ReactAgent，使得主流程非常简洁。
"""

import json
import logging
import sys
import os
from datetime import datetime

# --- 代码修复开始 ---
# 解决 ModuleNotFoundError 的关键步骤。
# 这会将项目的根目录添加到Python的搜索路径中，
# 使得解释器能够找到 'clients' 和 'react_agent' 等模块。
# 请根据您的实际项目文件结构，调整 '..' 的层级。
# 例如，如果 'clients' 目录在上一级，则使用 '..'。
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(project_root)
# --- 代码修复结束 ---

from react_agent import EnhancedReactAgent # 导入我们恢复后的ReactAgent
from clients.openrouter_client import OpenRouterClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('react_agent_internal_parallel.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main():
    """主函数"""
    
    print("🤖 ReAct Agent - JSON报告指南处理器 (内部并行版)")
    print("=" * 60)
    
    input_file = "E:\\项目代码\\Gauz文档Agent\\第一agent的输出.json"
    
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在: {input_file}")
        return
    
    try:
        print(f"📖 读取输入文件: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
        
        print("🔗 初始化OpenRouter客户端和ReactAgent...")
        client = OpenRouterClient()
        agent = EnhancedReactAgent(client)
        
        print(f"🚀 开始处理报告指南 (Agent将内部并行执行)...")
        start_time = datetime.now()
        
        # --- 调用非常简单 ---
        result_data = agent.process_report_guide(input_data)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        print(f"\n⏱️ 所有章节处理完成，总耗时: {processing_time:.2f}秒")
        
        # --- 后续处理和保存 ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"react_output_internal_parallel_{timestamp}.json"
        
        print(f"💾 保存结果到: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
            
        print(f"\n✅ 处理完成! 输出文件: {output_file}")
        
    except Exception as e:
        print(f"❌ 处理过程中出现未知错误: {e}")
        logging.error(f"主程序错误: {e}", exc_info=True)

if __name__ == "__main__":
    main()
