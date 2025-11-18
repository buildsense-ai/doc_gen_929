"""
Sequence Document Generator
===========================

This package implements the Redis-driven sequential document generation
pipeline that interoperates with the existing Gauz Document Agent
components (ReactAgent, ContentGeneratorAgent, etc.).
"""

from .pipeline import run_sequence_generation

__all__ = ["run_sequence_generation"]

