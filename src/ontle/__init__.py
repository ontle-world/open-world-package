"""ONTLE, the reference implementation of Open World Packages (OWP).

The names in `__all__` are the Python API other tools may call; every other module and function is internal and may
change in any release. The API itself may still change while OWP is in alpha (see CHANGELOG.md).
"""
__version__ = "0.2.0a6"

from .core import OWPError, ValidationResult, deterministic_pack, inspect_package, load_manifest, validate_package, verify_archive  # noqa: E402
from .ews import check_ews, compile_ews  # noqa: E402
from .kgcheck import KgReport, check_bindings, check_knowledge_graphs  # noqa: E402
from .ontodiff import OntologyDiff, diff_ontologies  # noqa: E402
from .ontology import build_term_index, export_rdf  # noqa: E402
from .report import package_report  # noqa: E402
from .resolve import Resolution, resolve_package, validate_resolved  # noqa: E402

__all__ = [
    "__version__", "OWPError",
    # packages: validate, resolve, inspect, pack
    "load_manifest", "validate_package", "ValidationResult", "validate_resolved", "resolve_package", "Resolution",
    "inspect_package", "package_report", "deterministic_pack", "verify_archive",
    # Effective World State
    "compile_ews", "check_ews",
    # ontologies and knowledge graphs (RDF needs the rdf extra; SHACL the shacl extra)
    "export_rdf", "build_term_index", "check_knowledge_graphs", "check_bindings", "KgReport", "diff_ontologies", "OntologyDiff",
]
