"""
BAM Extractors

Extractors parse specific file formats and produce structured data
for ingestion into BAM graph models.

Architecture:
    Stage 1: Source-specific extractors → Intermediate Format
    Stage 2: Intermediate Format → BAM Sketch (color ingestion)

The intermediate format is the contract between extraction and ingestion.
Source mappings (configured during sketch design) tell extractors how
to produce the intermediate format for a specific project.
"""

from .base import BaseExtractor, ExtractionResult
from .intermediate import (
    IntermediateData,
    IntermediateNode,
    IntermediateEdge,
    SourceMapping,
    validate_against_sketch,
    INTERMEDIATE_FORMAT_VERSION,
)
from .systemverilog import SystemVerilogExtractor
from .requirements import RequirementsExtractor
from .ingest import IntermediateIngester, IngestionResult, ingest_intermediate

__all__ = [
    # Base
    "BaseExtractor",
    "ExtractionResult",
    # Intermediate format
    "IntermediateData",
    "IntermediateNode",
    "IntermediateEdge",
    "SourceMapping",
    "validate_against_sketch",
    "INTERMEDIATE_FORMAT_VERSION",
    # Extractors
    "SystemVerilogExtractor",
    "RequirementsExtractor",
    # Ingestion (Stage 2)
    "IntermediateIngester",
    "IngestionResult",
    "ingest_intermediate",
]
