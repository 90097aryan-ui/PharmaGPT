"""
facility_database.py — SQLite CRUD for the Facility entity (PharmaGPT
Greenfield Facility URS, Stage 1).

Tables managed here
--------------------
facilities      : One row per greenfield facility record, owned by a Project
                  (mirrors equipment_database.py's Equipment-under-Project
                  ownership — see that module's docstring for the rationale).
                  Carries the facility-level identity fields a Facility URS
                  is generated from (facility type, product category,
                  regulatory market, site capacity, manufacturing type,
                  design standards, description), plus (Stage 1.1)
                  `classification` — Greenfield/Brownfield/Expansion/... — a
                  distinct axis from `facility_type` (which mixes facility
                  function and product type; kept unchanged for backward
                  compatibility) — and `design_basis`, a JSON blob (same
                  pattern as urs_projects.facility_data/ai_review_data)
                  holding the rest of Stage 1.1's structured metadata:
                  capacity (current/annual/future + units), expansion
                  (planned_expansion_pct, expandable_design), per-utility
                  design philosophy, validation strategy, and default
                  requirement source. Living on the Facility (not the URS)
                  is deliberate — these are durable facility attributes
                  Stage 2 modules (DQ/IQ/OQ/PQ/VMP) will also need to read.
facility_nodes  : Self-referential tree holding the Building -> Floor ->
                  Area -> Room hierarchy for a Facility. One generic table
                  (node_type discriminates the level) rather than four
                  near-identical tables, so the hierarchy is reusable for
                  future expansion (additional levels, additional attributes)
                  without a schema change — attributes is a free-form JSON
                  blob (classification, area, pressure regime, etc.), same
                  pattern already used by urs_projects.ai_review_data.

Relationship to Equipment / the URS Management Suite
------------------------------------------------------
A Facility is referenced by a URS record via `urs_projects.facility_id`
(urs_type='facility') exactly like an Equipment URS references equipment via
the free-text equipment_name/equipment_id fields — see urs_database.py and
routes/urs.py. Facility itself never owns URS content; the URS Management
Suite (urs_projects/urs_requirements/urs_approvals/urs_versions) remains the
single document engine for both URS types (Stage 1 scope: no separate
facility document/workflow tables).
"""

import json

from pharmagpt.database import get_connection

NODE_TYPES = ("building", "floor", "area", "room")

FACILITY_SCHEMA = """
    CREATE TABLE IF NOT EXISTS facilities (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id          INTEGER NOT NULL,
        facility_name       TEXT    NOT NULL,
        facility_type       TEXT    DEFAULT '',
        product_category    TEXT    DEFAULT '',
        country             TEXT    DEFAULT '',
        regulatory_market   TEXT    DEFAULT '',
        site_capacity       TEXT    DEFAULT '',
        manufacturing_type  TEXT    DEFAULT '',
        design_standards    TEXT    DEFAULT '',
        description         TEXT    DEFAULT '',
        created_by          TEXT    DEFAULT '',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS facility_nodes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id   INTEGER NOT NULL,
        parent_id     INTEGER DEFAULT NULL,
        node_type     TEXT    NOT NULL CHECK(node_type IN ('building','floor','area','room')),
        name          TEXT    NOT NULL,
        attributes    TEXT    DEFAULT '{}',
        sort_order    INTEGER DEFAULT 0,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id)   REFERENCES facility_nodes(id) ON DELETE CASCADE
    );
"""

_FACILITY_FIELDS = (
    "facility_name", "facility_type", "product_category", "country",
    "regulatory_market", "site_capacity", "manufacturing_type",
    "design_standards", "description", "classification",
)

DEFAULT_CLASSIFICATION = "Greenfield"

# Stage 1.1 mandatory field — distinct axis from facility_type (see module
# docstring). Order matches the product spec's enumeration.
FACILITY_CLASSIFICATIONS = (
    "Greenfield", "Brownfield", "Expansion", "Contract Manufacturing",
    "Warehouse", "Distribution Center", "QC Laboratory", "R&D Center",
    "Pilot Plant", "Manufacturing Facility",
)


def _facility_row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["design_basis"] = json.loads(d.get("design_basis") or "{}")
    except (TypeError, ValueError):
        d["design_basis"] = {}
    return d


# ── Facility CRUD ─────────────────────────────────────────────────────────────

def create_facility(project_id: int, data: dict, *, created_by: str = "") -> dict:
    """Insert a new Facility row scoped to a Project and return the full dict.

    `classification` (Stage 1.1) is mandatory at the API layer (routes/
    facility.py validates it) but defaults to DEFAULT_CLASSIFICATION here as
    a safety net — SQLite's column default only applies when a column is
    omitted from the INSERT, not when an explicit empty string is written,
    so the fallback has to happen in Python.
    """
    conn = get_connection()
    columns = ", ".join(_FACILITY_FIELDS)
    placeholders = ", ".join("?" for _ in _FACILITY_FIELDS)
    values = [(data.get(f) or "").strip() if isinstance(data.get(f), str) else data.get(f) or ""
              for f in _FACILITY_FIELDS]
    values[_FACILITY_FIELDS.index("classification")] = (
        (data.get("classification") or "").strip() or DEFAULT_CLASSIFICATION
    )
    design_basis = data.get("design_basis")
    design_basis_json = json.dumps(design_basis) if isinstance(design_basis, dict) else "{}"
    cur = conn.execute(
        f"INSERT INTO facilities (project_id, {columns}, created_by, design_basis) "
        f"VALUES (?, {placeholders}, ?, ?)",
        [project_id, *values, created_by, design_basis_json],
    )
    conn.commit()
    row = conn.execute("SELECT * FROM facilities WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _facility_row_to_dict(row)


def get_facility(facility_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    conn.close()
    return _facility_row_to_dict(row) if row else None


def get_facility_scoped(facility_id: int, company_id: str | None) -> dict | None:
    """Return the facility row only if it exists AND its owning Project
    belongs to `company_id` — mirrors equipment_database.get_equipment_scoped
    (a Facility has no company_id column of its own; it inherits tenancy from
    its Project). `company_id` must come from the authenticated
    TenantContext, never client input."""
    if not company_id:
        return None
    conn = get_connection()
    row = conn.execute(
        """SELECT f.* FROM facilities f
           JOIN projects p ON p.id = f.project_id
           WHERE f.id = ? AND p.company_id = ?""",
        (facility_id, company_id),
    ).fetchone()
    conn.close()
    return _facility_row_to_dict(row) if row else None


def get_project_facilities(project_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM facilities WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
    ).fetchall()
    conn.close()
    return [_facility_row_to_dict(r) for r in rows]


def update_facility(facility_id: int, data: dict) -> dict | None:
    updates = {k: data[k] for k in _FACILITY_FIELDS if k in data}
    if "classification" in updates and not (updates["classification"] or "").strip():
        updates.pop("classification")  # never let an explicit blank clear a mandatory field
    if "design_basis" in data and isinstance(data["design_basis"], dict):
        updates["design_basis"] = json.dumps(data["design_basis"])
    if not updates:
        return get_facility(facility_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [facility_id]
    conn = get_connection()
    with conn:
        conn.execute(
            f"UPDATE facilities SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
    conn.close()
    return get_facility(facility_id)


def delete_facility(facility_id: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM facilities WHERE id = ?", (facility_id,))
    conn.close()


# ── Facility node tree (Building -> Floor -> Area -> Room) ───────────────────

def _node_row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["attributes"] = json.loads(d.get("attributes") or "{}")
    except (TypeError, ValueError):
        d["attributes"] = {}
    return d


def create_node(facility_id: int, data: dict) -> dict:
    node_type = (data.get("node_type") or "").strip().lower()
    if node_type not in NODE_TYPES:
        raise ValueError(f"node_type must be one of: {', '.join(NODE_TYPES)}")
    attributes = data.get("attributes")
    attributes_json = json.dumps(attributes) if isinstance(attributes, dict) else "{}"
    conn = get_connection()
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM facility_nodes "
        "WHERE facility_id = ? AND parent_id IS ?",
        (facility_id, data.get("parent_id")),
    ).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO facility_nodes
           (facility_id, parent_id, node_type, name, attributes, sort_order)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            facility_id, data.get("parent_id"), node_type,
            (data.get("name") or "").strip() or node_type.title(),
            attributes_json, max_order + 1,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM facility_nodes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return _node_row_to_dict(row)


def get_node(node_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM facility_nodes WHERE id = ?", (node_id,)).fetchone()
    conn.close()
    return _node_row_to_dict(row) if row else None


def get_facility_nodes(facility_id: int) -> list[dict]:
    """Flat list of every node in the facility, ordered so a caller can
    build the tree client-side (parents before children within each level is
    not guaranteed — the frontend groups by parent_id — but sort_order is
    stable within a parent)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM facility_nodes WHERE facility_id = ? ORDER BY parent_id, sort_order",
        (facility_id,),
    ).fetchall()
    conn.close()
    return [_node_row_to_dict(r) for r in rows]


def update_node(node_id: int, data: dict) -> dict | None:
    updates: dict = {}
    if "name" in data:
        updates["name"] = (data.get("name") or "").strip()
    if "attributes" in data and isinstance(data["attributes"], dict):
        updates["attributes"] = json.dumps(data["attributes"])
    if "sort_order" in data:
        updates["sort_order"] = data["sort_order"]
    if not updates:
        return get_node(node_id)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [node_id]
    conn = get_connection()
    with conn:
        conn.execute(f"UPDATE facility_nodes SET {set_clause} WHERE id = ?", values)
    conn.close()
    return get_node(node_id)


def delete_node(node_id: int) -> None:
    """Delete a node; ON DELETE CASCADE removes its descendants."""
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM facility_nodes WHERE id = ?", (node_id,))
    conn.close()


def build_node_tree(facility_id: int) -> list[dict]:
    """Nest the flat node list into a tree (children under each node's
    `children` key) for the frontend layout view."""
    nodes = get_facility_nodes(facility_id)
    by_id = {n["id"]: {**n, "children": []} for n in nodes}
    roots = []
    for n in nodes:
        entry = by_id[n["id"]]
        parent_id = n.get("parent_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(entry)
        else:
            roots.append(entry)
    return roots


def summarize_nodes_for_prompt(facility_id: int) -> str:
    """Compact text summary of the facility's Building/Floor/Area/Room
    hierarchy for AI-prompt context (services/facility_urs prompt builder) —
    avoids dumping raw JSON at the model."""
    tree = build_node_tree(facility_id)
    lines: list[str] = []

    def walk(entries: list[dict], depth: int) -> None:
        for entry in entries:
            attrs = entry.get("attributes") or {}
            attr_str = ", ".join(f"{k}: {v}" for k, v in attrs.items() if v not in (None, ""))
            label = f"{'  ' * depth}- [{entry['node_type'].title()}] {entry['name']}"
            if attr_str:
                label += f" ({attr_str})"
            lines.append(label)
            walk(entry.get("children") or [], depth + 1)

    walk(tree, 0)
    return "\n".join(lines) if lines else "(no building/floor/area/room hierarchy defined yet)"
