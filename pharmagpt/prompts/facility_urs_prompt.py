"""
facility_urs_prompt.py — Dedicated Gemini prompt for Greenfield Facility URS
generation (Stage 1, extended in Stage 1.1 with business-intelligence
metadata: Facility Classification, Product Category, Regulatory Package,
Production Capacity, Future Expansion, Utility Philosophy, and Validation
Strategy).

Deliberately separate wording from prompts/urs_prompt.py and
services/urs_service.build_generation_prompt() (the equipment/system
prompt) — a facility URS reasons about buildings, room classification,
utility systems, and material/personnel/waste flow, not a single piece of
equipment's functional/performance specification. The two prompt builders
share nothing but the output contract: both must return a JSON array
matching services/urs_generation_job.py's _REQUIREMENT_ARRAY_SCHEMA, which
is what lets the same background-job pipeline (batching, retry, partial
recovery, persistence) generate either document type unmodified — see
urs_service.build_generation_prompt()'s urs_type dispatch.

Stage 1.1 design note: every new metadata field below is optional and has a
"not specified" fallback identical in spirit to Stage 1's — a facility URS
created before Stage 1.1 (or one where the wizard's new fields were left
blank) produces a prompt that reads exactly as it did in Stage 1, not a
prompt full of "None"/"[]" artifacts. The point of this file is that a
*selected* value changes what's generated, not that an unselected one
breaks anything.
"""

from __future__ import annotations

from pharmagpt.facility_systems import get_facility_system_profile, format_facility_system_for_prompt


# ── Guidance lookups — this is the "intelligently adapt" mechanism: each
#    selected value maps to a concrete instruction, not just a label the
#    model is told to repeat back. ─────────────────────────────────────────

CLASSIFICATION_GUIDANCE = {
    "Greenfield": "This is a new-build facility on a previously undeveloped or non-GMP site — design freely to best practice with no existing-structure constraints.",
    "Brownfield": "This facility reuses or ties into an existing structure/site. Explicitly call out tie-in points, existing-condition constraints, and any legacy utility capacity limits in the relevant sections (Building, Utilities) rather than writing purely greenfield requirements.",
    "Expansion": "This facility expands a currently-operating GMP site. Requirements must reflect phased construction and zero-disruption-to-ongoing-operations constraints, especially in Building Requirements and Risk Considerations.",
    "Contract Manufacturing": "This facility manufactures for multiple external clients. Emphasize product/client segregation, dedicated-vs-shared equipment decisions, and per-client traceability in GMP Requirements and Material Flow.",
    "Warehouse": "This is a storage-only facility, not a manufacturing site. Do not generate manufacturing-process requirements (compression, filling, etc.) — focus Building/HVAC/Material Flow requirements on storage-condition control, status segregation (quarantine/released/rejected), and GDP.",
    "Distribution Center": "This is a receipt-and-dispatch logistics facility. Emphasize minimal product dwell time, cross-docking flow, and chain-of-custody rather than long-term storage or manufacturing.",
    "QC Laboratory": "This is a standalone testing facility, not a manufacturing site. Do not generate manufacturing-process requirements — focus on sample receipt/testing/retention flow, instrument environmental stability, and data integrity.",
    "R&D Center": "This is a development facility. Emphasize reconfigurability, flexible/modular design, and segregation between concurrent, unrelated development programs rather than fixed-scale commercial throughput.",
    "Pilot Plant": "This facility supports scale-up/scale-down development batches. Emphasize equipment/utility flexibility across batch sizes rather than optimized fixed-scale commercial throughput.",
    "Manufacturing Facility": "This is a standard commercial manufacturing facility — apply the baseline GMP facility design practice for the declared product category without a specialized classification overlay.",
}

PRODUCT_CATEGORY_GUIDANCE = {
    "Tablets": "Emphasize dust containment and extraction for compression/coating, and cleanroom/HVAC design sized for particulate-generating unit operations.",
    "Capsules": "Emphasize relative-humidity control (shell integrity — gelatin/HPMC) as a primary HVAC design driver, alongside dust control.",
    "Oral Liquids": "Emphasize Purified Water quality and microbial control as a primary utility/water-system design driver — water is typically the majority excipient by mass.",
    "Ointments": "Emphasize cleaning-validation-compatible surface finishes and drainage for semi-solid (lipid/grease-based) compounding and filling.",
    "Injectables": "Emphasize EU GMP Annex 1 Grade A/B aseptic design, unidirectional airflow at the fill point, WFI availability, and a facility-wide Contamination Control Strategy — this is the highest sterility-assurance category.",
    "Ophthalmic": "Emphasize sterility assurance appropriate to the container/closure system (single-dose vs. multi-dose with preservative), close to injectable-grade design but explicitly note the container/closure-driven differences.",
    "API": "Emphasize solvent handling, recovery, and hazardous-waste design sized to the synthesis chemistry — this is a chemical synthesis facility, not a dosage-form facility; do not generate dosage-form-specific (tablet/capsule/injectable) requirements unless the facility also declares that scope.",
    "Biologics": "Emphasize BOTH contamination control INTO the process and containment OUT of it (biosafety level), plus single-use system compatibility and cold-chain considerations — a two-directional control requirement distinct from small-molecule facilities.",
    "Nutraceuticals": "Explicitly note where the facility sits at the boundary between pharmaceutical GMP and food/dietary-supplement GMP frameworks, and design shared areas to the stricter of the two.",
    "Medical Devices": "Note that ISO 13485 governs device manufacturing quality systems as a complement to, not a substitute for, pharmaceutical GMP — flag this explicitly in Regulatory Requirements.",
    "Multiple Products": "Emphasize cross-contamination risk assessment, changeover, and cleaning validation between distinct product lines sharing area or equipment — this is the facility's dominant risk driver.",
}

VALIDATION_STRATEGY_GUIDANCE = {
    "Traditional Validation": "Phrase Documentation/traceability requirements around the classic sequential IQ/OQ/PQ protocol lifecycle.",
    "ASTM E2500": "Phrase Documentation/traceability requirements around an integrated, science- and risk-based commissioning-and-qualification approach (verification of specifications, not a separately re-tested IQ/OQ/PQ sequence).",
    "CSA": "For computerized/automated systems specifically (BMS, EMS), phrase requirements around a risk-based Computer Software Assurance approach — critical-thinking-based testing prioritized over exhaustive scripted verification for low-risk functions.",
    "Risk-Based Validation": "Phrase Documentation/Risk Considerations requirements around an ICH Q9 risk assessment driving qualification depth per system, with GMP-Critical systems getting the most rigorous verification and Non-GMP systems a justified, reduced scope.",
}


def _normalize_list(value) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if v and str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def build_generation_prompt(urs_info: dict, sections: list[str]) -> str:
    """Build a structured Gemini prompt for Facility URS requirement
    generation.

    `urs_info` is the same dict shape routes/urs.py assembles for an
    equipment URS, but for urs_type == 'facility' it carries facility_*
    columns, the parsed `facility_data` JSON blob (Stage 1 wizard fields),
    and (Stage 1.1) the facility's `classification` plus its parsed
    `design_basis` JSON blob (capacity, expansion, utility philosophy,
    validation strategy) flattened onto `urs_info` directly by
    routes/urs.py — see that module's generate_requirements().
    """
    facility_name = urs_info.get("facility_name") or urs_info.get("title", "the facility")
    fd = urs_info.get("facility_data") or {}

    facility_type      = urs_info.get("facility_type", "")
    classification       = urs_info.get("classification", "")
    product_category      = urs_info.get("product_category", "")
    country                 = urs_info.get("country", "")
    regulatory_market       = urs_info.get("regulatory_market", "")
    site_capacity            = urs_info.get("site_capacity", "")
    manufacturing_type        = urs_info.get("manufacturing_type", "")
    design_standards           = urs_info.get("design_standards", "")
    description                 = urs_info.get("description", "")

    manufacturing_areas  = fd.get("manufacturing_areas", "")
    warehouse_areas       = fd.get("warehouse_areas", "")
    qc_areas               = fd.get("qc_areas", "")
    utilities_required     = fd.get("utilities_required", [])
    hvac_philosophy         = fd.get("hvac_philosophy", "")
    cleanroom_classification = fd.get("cleanroom_classification", "")
    material_flow            = fd.get("material_flow", "")
    personnel_flow            = fd.get("personnel_flow", "")
    waste_flow                = fd.get("waste_flow", "")
    expansion_requirements     = fd.get("expansion_requirements", "")
    automation_requirements    = fd.get("automation_requirements", "")
    validation_expectations    = fd.get("validation_expectations", "")

    # ── Stage 1.1 metadata (design_basis, flattened onto urs_info) ──────────
    regulatory_package      = _normalize_list(urs_info.get("regulatory_package") or regulatory_market)
    current_capacity_value   = urs_info.get("current_capacity_value", "")
    current_capacity_unit     = urs_info.get("current_capacity_unit", "")
    annual_capacity_value      = urs_info.get("annual_capacity_value", "")
    annual_capacity_unit        = urs_info.get("annual_capacity_unit", "")
    future_capacity_value        = urs_info.get("future_capacity_value", "")
    future_capacity_unit          = urs_info.get("future_capacity_unit", "")
    planned_expansion_pct          = urs_info.get("planned_expansion_pct", "")
    expandable_design                = bool(urs_info.get("expandable_design"))
    utility_philosophy                = urs_info.get("utility_philosophy") or {}
    validation_strategy                = urs_info.get("validation_strategy", "")

    node_summary = urs_info.get("facility_node_summary", "(no building/floor/area/room hierarchy defined yet)")

    if isinstance(utilities_required, list):
        utilities_list = utilities_required
    else:
        utilities_list = [u.strip() for u in str(utilities_required).split(",") if u.strip()]

    system_profile_blocks = []
    for system_name in utilities_list:
        profile = get_facility_system_profile(system_name)
        if profile:
            system_profile_blocks.append(format_facility_system_for_prompt(profile))
    system_profiles_text = "\n".join(system_profile_blocks) if system_profile_blocks else ""

    sections_str = ", ".join(sections) if sections else "all relevant sections"

    # ── Regulatory framework instruction — dynamic when a package was
    #    explicitly selected ("generate only relevant clauses"); falls back
    #    to Stage 1's generic list when it wasn't, so a facility with no
    #    regulatory package selected still gets sensible default coverage. ──
    if regulatory_package:
        regulatory_instruction = (
            f"Reference ONLY the following regulatory frameworks, which were explicitly selected for "
            f"this facility: {', '.join(regulatory_package)}. Do not cite a framework outside this list "
            f"unless a requirement is a universal safety/engineering-code matter with no GMP-specific "
            f"framework of its own (e.g., local fire code)."
        )
    else:
        regulatory_instruction = (
            "No specific regulatory package was selected — reference the standard applicable frameworks "
            "(21 CFR Part 211, EU GMP Chapters/Annexes, ISO 14644, ISPE Baseline Guides, ICH Q9/Q10, "
            "WHO GMP/GDP, PIC/S, GAMP 5) as appropriate to each section."
        )

    classification_line = classification or "not specified"
    classification_guidance = CLASSIFICATION_GUIDANCE.get(classification, "")

    product_category_guidance = PRODUCT_CATEGORY_GUIDANCE.get(product_category, "")

    validation_strategy_line = validation_strategy or "not specified — use standard GAMP 5 risk-based qualification lifecycle framing (Stage 2 of this project)"
    validation_strategy_guidance = VALIDATION_STRATEGY_GUIDANCE.get(validation_strategy, "")

    capacity_lines = []
    if current_capacity_value:
        capacity_lines.append(f"- Current Capacity: {current_capacity_value} {current_capacity_unit}".rstrip())
    if annual_capacity_value:
        capacity_lines.append(f"- Annual Capacity: {annual_capacity_value} {annual_capacity_unit}".rstrip())
    if not capacity_lines and site_capacity:
        capacity_lines.append(f"- Site Capacity: {site_capacity}")
    capacity_text = "\n".join(capacity_lines) if capacity_lines else "- Not specified — size warehouse, utilities, and personnel requirements generically rather than to a specific throughput."

    if expandable_design:
        expansion_text = (
            f"This facility IS designed to be expandable. Future Capacity target: "
            f"{future_capacity_value or 'not quantified'} {future_capacity_unit}"
            f"{f' ({planned_expansion_pct}% above current design capacity)' if planned_expansion_pct else ''}. "
            f"Generate explicit expandable-facility requirements (reserved space, structural allowance, "
            f"utility headroom) in the Future Expansion Requirements section, sized against this target."
        )
    else:
        expansion_text = "This facility is NOT declared expandable — do not generate space/utility-reservation requirements for future capacity beyond the standard baseline."

    utility_philosophy_lines = [
        f"- {system}: {philosophy}" for system, philosophy in utility_philosophy.items() if philosophy
    ]
    utility_philosophy_text = (
        "\n".join(utility_philosophy_lines)
        if utility_philosophy_lines
        else "- Not specified for any system — do not state a redundancy/centralization philosophy unless it is implied by the facility type/product category."
    )

    return f"""You are a Senior Pharmaceutical Facility Engineering Consultant with 30+ years of experience writing User Requirement Specifications (URS) for greenfield pharmaceutical manufacturing facilities — building design, cleanroom classification, HVAC, utilities, and material/personnel/waste flow — for ISPE-aligned projects reviewed by USFDA, EU, and WHO-GMP inspectors.

Generate comprehensive, GMP-compliant facility-level User Requirements for the following greenfield facility. The metadata below is not a checklist to restate — every selected value must visibly change the content, specificity, and emphasis of the generated requirements (see the guidance notes attached to each field).

FACILITY DETAILS:
- Facility Name: {facility_name}
- Facility Type: {facility_type}
- Facility Classification: {classification_line}{f" — {classification_guidance}" if classification_guidance else ""}
- Product Category: {product_category or "not specified"}{f" — {product_category_guidance}" if product_category_guidance else ""}
- Country: {country}
- Regulatory Market(s): {regulatory_market}
- Manufacturing Type: {manufacturing_type}
- Design Standards Referenced: {design_standards}
- Description: {description}

BUILDING / FLOOR / AREA / ROOM HIERARCHY:
{node_summary}

FUNCTIONAL AREAS:
- Manufacturing Areas: {manufacturing_areas or "not specified"}
- Warehouse Areas: {warehouse_areas or "not specified"}
- QC Areas: {qc_areas or "not specified"}

PRODUCTION CAPACITY:
{capacity_text}
Use these figures to size warehouse (storage/staging area), utility (water/HVAC/electrical load), and personnel-related requirements proportionately — a requirement like storage racking capacity or AHU sizing should reference the stated throughput where relevant, not be generic.

FUTURE EXPANSION:
{expansion_text}

UTILITIES / FACILITY SYSTEMS REQUIRED: {", ".join(utilities_list) or "not specified"}
{system_profiles_text}

UTILITY DESIGN PHILOSOPHY (per system — reflect the stated redundancy/centralization strategy explicitly in that system's generated requirements):
{utility_philosophy_text}

DESIGN PHILOSOPHY INPUTS:
- HVAC Philosophy: {hvac_philosophy or "not specified — infer a philosophy consistent with the facility classification and product category"}
- Cleanroom Classification: {cleanroom_classification or "not specified — recommend classification consistent with the facility classification and product category"}
- Material Flow: {material_flow or "not specified — infer a unidirectional flow appropriate to the facility classification"}
- Personnel Flow: {personnel_flow or "not specified — infer a gowning-appropriate flow"}
- Waste Flow: {waste_flow or "not specified"}
- Expansion Requirements (free text, if any): {expansion_requirements or "none specified"}
- Automation Requirements: {automation_requirements or "not specified"}
- Validation Expectations (free text, if any): {validation_expectations or "none specified"}

VALIDATION STRATEGY: {validation_strategy_line}{f" — {validation_strategy_guidance}" if validation_strategy_guidance else ""}

REGULATORY PACKAGE: {regulatory_instruction}

REQUIRED SECTIONS: {sections_str}

INSTRUCTIONS:
1. Generate 4–8 specific, measurable, testable requirements per section — this is a facility-level document, materially more detailed overall than a single-equipment URS, but each individual section should stay concise and non-repetitive.
2. Each requirement must start with "The facility shall..." or "The [system/area] shall...".
3. Adapt the content to EVERY selected metadata field above (classification, product category, capacity, expansion, utility philosophy, validation strategy, regulatory package) — do not just acknowledge a selection, let it visibly change which requirements you write and how they're worded. Two facilities with different Facility Classification or Product Category values must produce visibly different documents, not the same generic content with a different label.
4. Where the facility classification or product category implies a well-established design practice (e.g., Grade A/B for sterile fill, dedicated AHUs for beta-lactam/hormone segregation, WFI for injectable final rinse), state it explicitly rather than leaving it generic — you are the domain expert filling gaps the user did not specify.
5. Include specific numeric values, tolerances, and acceptance criteria where a defensible pharmaceutical-industry design value exists (temperature/RH ranges, ACPH, pressure differentials, purity classes) — do not invent a regulatory clause number that is not well established; cite the standard/guide by name only.
6. Flag GMP-Critical requirements clearly — cross-contamination control, pressure cascade, water systems, and data-integrity-bearing monitoring are almost always GMP-Critical for a facility.
7. Do NOT generate Installation/Operational/Performance Qualification (IQ/OQ/PQ) test scripts or Design Qualification acceptance test procedures — this is a User Requirement Specification only; qualification protocols are Stage 2 of this project and out of scope here.
8. Ensure every requirement is traceable to a future Design Qualification (DQ) review — phrase requirements so a reviewer can assess design compliance against them.

OUTPUT FORMAT — Return ONLY a JSON array with this exact structure:
[
  {{
    "section": "HVAC Requirements",
    "requirement": "The facility shall...",
    "rationale": "Ensures GMP compliance because...",
    "priority": "Critical",
    "gmp_criticality": "GMP-Critical",
    "regulatory_ref": "EU GMP Annex 1, ISPE Baseline Guide Vol. 3",
    "verification_method": "Design Review",
    "acceptance_criteria": "Specific measurable pass/fail criterion"
  }}
]

Priority values: Critical, High, Medium, Low
GMP Criticality values: GMP-Critical, GMP, Non-GMP
Verification Method values for a facility URS: Design Review, Document Review, Inspection, Testing (avoid IQ/OQ/PQ-specific phrasing — that lifecycle is Stage 2).

Generate requirements that would satisfy a senior FDA, EU, or WHO GMP facility-design inspector reviewing this URS against the ISPE Baseline Guide for this facility type. Be specific, measurable, and scientifically sound.
"""
