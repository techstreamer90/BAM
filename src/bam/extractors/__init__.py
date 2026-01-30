"""
BAM Extractors

Extractors parse specific file formats and produce structured data
for ingestion into BAM graph models.
"""

from .base import BaseExtractor, ExtractionResult
from .systemverilog import SystemVerilogExtractor

__all__ = [
    "BaseExtractor",
    "ExtractionResult",
    "SystemVerilogExtractor",
]
