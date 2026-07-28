"""
services/workflow_registry.py — the single, shared place that knows which
business modules run on the Workflow Engine and how to resolve a
(record_type, record_id) pair into display data (title, record number,
route, icon).

This is the one deliberately module-aware component in the whole Universal
Workflow Inbox feature. Everything downstream of it — the Inbox route, the
Dashboard's pending-approvals widget, the notification bell — reads this
same registry instead of hardcoding its own per-module list, so adding a
future module is exactly one new ModuleDescriptor entry here plus a
qms_workflow_templates row (services/workflow_engine.py's STATUS_APPLIERS)
— no new UI code, no new route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ModuleDescriptor:
    record_type: str
    workflow_key: str
    get_record: Callable[[int], dict | None]
    number_field: str
    title_field: str
    route_prefix: str
    icon: str  # lucide icon name, used for the Inbox's module badge


def _registry() -> dict[str, ModuleDescriptor]:
    # Imported lazily so this module has no import-time dependency on every
    # business module's database layer (avoids import-order issues and
    # keeps this file cheap to import from anywhere).
    from pharmagpt import qms_deviation_database as ddb
    from pharmagpt import qms_capa_database as capadb
    from pharmagpt import qms_change_control_database as ccdb
    from pharmagpt import qms_document_database as qdb

    return {
        "deviation": ModuleDescriptor(
            "deviation", "DEVIATION_LIFECYCLE_V2", ddb.get_deviation,
            "deviation_number", "title", "/qms/deviations", "alert-triangle",
        ),
        "capa": ModuleDescriptor(
            "capa", "CAPA_WORKFLOW_V1", capadb.get_capa,
            "capa_number", "title", "/qms/capa", "wrench",
        ),
        "change_control": ModuleDescriptor(
            "change_control", "CHANGE_CONTROL_WORKFLOW_V1", ccdb.get_change_control,
            "cc_number", "title", "/qms/change-control", "git-branch",
        ),
        "document": ModuleDescriptor(
            "document", "DOCUMENT_WORKFLOW_V1", qdb.get_document,
            "doc_number", "title", "/qms/documents", "file-text",
        ),
    }


MODULE_REGISTRY: dict[str, ModuleDescriptor] = _registry()


def describe(record_type: str) -> ModuleDescriptor | None:
    return MODULE_REGISTRY.get(record_type)
