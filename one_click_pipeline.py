#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键式多Agent文档流水线

串联 OrchestratorAgent → SectionWriterAgent → ContentGeneratorAgent → FinalReviewAgent
可选启用：评审 + 针对性再生 + JSON层合并 + 重渲染。
"""

from __future__ import annotations

import os
import sys
import json
import shutil
from datetime import datetime
from typing import Dict, Any, Optional

# 确保项目根目录在路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from clients.openrouter_client import OpenRouterClient
from Document_Agent.orchestrator_agent import OrchestratorAgent
from Document_Agent.section_writer_agent import ReactAgent
from Document_Agent.content_generator_agent import MainDocumentGenerator
from Document_Agent.final_review_agent.document_reviewer import DocumentReviewer
from Document_Agent.final_review_agent.regenerate_sections import DocumentRegenerator
from Document_Agent.final_review_agent.json_merger import JSONDocumentMerger


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _derive_paths_from_generated_json(generated_json_path: str) -> Dict[str, str]:
    """
    由生成器返回的 JSON 路径，推导对应的 Markdown 路径。
    约定：
      JSON:  生成文档的依据_完成_{ts}.json
      MD:    完整版文档_{ts}.md
    """
    base = os.path.basename(generated_json_path)
    ts = base.replace("生成文档的依据_完成_", "").replace(".json", "")
    md_name = f"完整版文档_{ts}.md"
    return {
        "timestamp": ts,
        "md_name": md_name,
    }


def one_click_generate_document(
    user_query: str,
    project_name: str = "默认项目",
    output_dir: str = "outputs",
    enable_review_and_regeneration: bool = True,
    guide_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    一键执行端到端文档生成：结构→检索→成文（必选），评审→再生→合并（可选）。

    Args:
        user_query: 文档生成需求描述
        project_name: 项目名（用于检索标识）
        output_dir: 输出目录（所有中间/最终文件将集中到此目录）
        enable_review_and_regeneration: 是否启用评审+再生+合并
        guide_id: 可选的模板ID，如果提供则使用指定模板

    Returns:
        包含各阶段关键产物路径与统计信息的字典
    """

    _ensure_dir(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 初始化客户端与各Agent
    llm_client = OpenRouterClient()
    orchestrator = OrchestratorAgent(llm_client)
    section_writer = ReactAgent(llm_client)
    content_generator = MainDocumentGenerator()
    reviewer = DocumentReviewer()
    regenerator = DocumentRegenerator()

    results: Dict[str, Any] = {
        "output_directory": output_dir,
        "timestamp": timestamp,
        "user_query": user_query,
        "project": project_name,
        "stages": {},
    }

    # 阶段1：结构 + 写作指导
    guide = orchestrator.generate_complete_guide(user_query, guide_id=guide_id)
    step1_path = os.path.join(output_dir, f"step1_document_guide_{timestamp}.json")
    with open(step1_path, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)
    results["stages"]["structure_and_guides"] = {"file": step1_path}

    # 阶段2：检索增强
    enriched = section_writer.process_report_guide(guide, project_name)
    step2_path = os.path.join(output_dir, f"step2_enriched_guide_{timestamp}.json")
    with open(step2_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    results["stages"]["retrieval_enrichment"] = {"file": step2_path}

    # 阶段3：内容生成（生成器写入当前工作目录，需要搬运到 output_dir）
    generation_input = os.path.join(output_dir, f"生成文档的依据_{timestamp}.json")
    with open(generation_input, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    gen_json_path_cwd = content_generator.generate_document(generation_input)
    # 推导 MD 文件名
    name_info = _derive_paths_from_generated_json(gen_json_path_cwd)
    gen_md_name = name_info["md_name"]

    # 将生成器在 CWD 产出的文件搬到 output_dir
    src_json = os.path.abspath(gen_json_path_cwd)
    src_md = os.path.abspath(gen_md_name)
    dst_json = os.path.join(output_dir, os.path.basename(src_json))
    dst_md = os.path.join(output_dir, os.path.basename(src_md))
    if os.path.exists(src_json):
        shutil.move(src_json, dst_json)
    if os.path.exists(src_md):
        shutil.move(src_md, dst_md)

    results["stages"]["content_generation"] = {
        "json": dst_json,
        "markdown": dst_md,
    }

    # 可选：评审 + 再生 + 合并
    if not enable_review_and_regeneration:
        results["final_document"] = dst_md
        return results

    # 阶段4：质量评审（简化版，输出 subtitle + suggestion）
    with open(dst_md, "r", encoding="utf-8") as f:
        md_content = f.read()
    document_title = os.path.splitext(os.path.basename(dst_md))[0]
    issues = reviewer.analyze_document_simple(md_content, dst_md, document_title)
    issues_file = os.path.join(output_dir, f"quality_issues_{timestamp}.json")
    with open(issues_file, "w", encoding="utf-8") as f:
        json.dump(issues or [], f, ensure_ascii=False, indent=2)
    results["stages"]["quality_review"] = {"issues_file": issues_file, "issues": len(issues or [])}

    if not issues:
        # 无问题，直接返回
        results["final_document"] = dst_md
        return results

    # 阶段5：针对性再生
    regen_dir = os.path.join(output_dir, "regenerated_outputs")
    _ensure_dir(regen_dir)
    # 再生阶段严格以 JSON 为准，传入 JSON 源以便直接按 subtitle 从 JSON 取原文
    regen_results = regenerator.regenerate_document_sections(issues_file, dst_json, output_dir=regen_dir)
    regen_json = os.path.join(regen_dir, f"regenerated_sections_{timestamp}.json")
    with open(regen_json, "w", encoding="utf-8") as f:
        json.dump(regen_results, f, ensure_ascii=False, indent=2)
    results["stages"]["regeneration"] = {"file": regen_json, "sections": len(regen_results or {})}

    # 阶段6：JSON层合并 + 重渲染
    merger = JSONDocumentMerger(original_json_path=dst_json, regenerated_json_path=regen_json)
    merger.load_original_json()
    merger.load_regenerated_sections()
    merged_data = merger.merge_json_documents()

    merged_json = os.path.join(output_dir, f"merged_document_{timestamp}.json")
    merger.save_merged_json(merged_data, merged_json)
    merged_md = os.path.join(output_dir, f"merged_document_{timestamp}.md")
    merger.convert_to_markdown(merged_data, merged_md)
    merger.generate_summary_report(merged_json, merged_md)

    results["stages"]["merge_and_render"] = {
        "merged_json": merged_json,
        "merged_markdown": merged_md,
        "summary": merged_md.replace(".md", "_summary.md"),
    }
    results["final_document"] = merged_md

    return results


__all__ = [
    "one_click_generate_document",
]


