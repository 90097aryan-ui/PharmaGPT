"""
facility_requirement_library.py — Pre-built requirement library for the
Greenfield Facility URS (Stage 1).

Architecture mirrors services/urs_requirement_library.py exactly (section
prefix map -> common requirements -> type-specific overlay -> flat numbered
list) but keyed by `facility_type` instead of `equipment_type`, since a
Facility URS is one holistic document covering the whole site rather than a
single piece of equipment. FACILITY_COMMON_REQUIREMENTS supplies the
baseline every facility type gets; FACILITY_TYPE_OVERLAYS adds the handful
of sections where a facility type's requirements genuinely diverge
(cleanroom classification, HVAC philosophy, water systems, gas systems,
waste flow) rather than duplicating the whole library per type.

Requirement structure — identical shape to urs_requirement_library.py's, so
both feed the same urs_requirements table/DOCX exporter unmodified:
    requirement         : "The facility shall…" statement
    rationale           : justification / regulatory driver
    priority            : Critical | High | Medium | Low
    gmp_criticality     : GMP-Critical | GMP | Non-GMP
    regulatory_ref      : applicable standard(s)
    verification_method : Document Review | Design Review | Inspection | etc.
    acceptance_criteria : pass/fail criterion
"""

from __future__ import annotations


# ── Facility types (dropdown source for the wizard) ───────────────────────────

FACILITY_TYPES = [
    "OSD (Oral Solid Dosage)",
    "Injectable (Sterile)",
    "API (Active Pharmaceutical Ingredient)",
    "Warehouse / Distribution Center",
    "QC Laboratory",
    "R&D Facility",
    "Multi-Product / General Manufacturing",
]


# ── Section prefix map (used to generate req_id codes) ────────────────────────

FACILITY_SECTION_PREFIX = {
    "General Requirements":       "GEN",
    "Site Information":           "SITE",
    "Building Requirements":      "BLD",
    "Architectural Requirements": "ARCH",
    "Cleanroom Requirements":     "CLN",
    "HVAC Requirements":          "HVAC",
    "Utilities Requirements":     "UTL",
    "Water Systems":              "WTR",
    "Compressed Air Requirements":"CAIR",
    "Nitrogen Requirements":      "N2",
    "Electrical Requirements":    "ELEC",
    "BMS Requirements":           "BMS",
    "EMS Requirements":           "EMS",
    "Material Flow":              "MATF",
    "Personnel Flow":             "PERF",
    "Waste Flow":                 "WASF",
    "GMP Requirements":           "GMP",
    "Regulatory Requirements":    "REG",
    "Data Integrity Requirements":"DI",
    "Automation Requirements":    "AUTO",
    "Safety Requirements":        "SAFE",
    "Maintenance Requirements":   "MAINT",
    "Training Requirements":      "TRN",
    "Documentation":              "DOC",
    "Sustainability Requirements":"SUS",
    "Risk Considerations":        "RISK",
    "Future Expansion Requirements": "EXP",
}


# ── Baseline requirements shared across all facility types ────────────────────

FACILITY_COMMON_REQUIREMENTS: dict[str, list[dict]] = {
    "General Requirements": [
        {
            "requirement": "The facility shall be designed, constructed, and qualified in accordance with current Good Manufacturing Practice (cGMP) requirements applicable to the intended regulatory markets.",
            "rationale": "Establishes the overarching compliance basis for all downstream design and qualification activities.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 211, EU GMP Chapter 1-9, ICH Q10",
            "verification_method": "Document Review", "acceptance_criteria": "URS/DQ traceability confirmed for every regulatory market declared.",
        },
        {
            "requirement": "The facility design shall accommodate the declared product portfolio (dosage form, potency/containment class) without cross-contamination risk between incompatible products or processes.",
            "rationale": "Prevents cross-contamination, the most common facility-design-driven GMP finding.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3 and 5, ICH Q9",
            "verification_method": "Design Review", "acceptance_criteria": "Segregation/containment strategy documented and risk-assessed for each product/process combination.",
        },
    ],
    "Site Information": [
        {
            "requirement": "The site shall provide documented evidence of land use approval, environmental clearance, and utility availability (power, water, effluent discharge) sufficient for the declared site capacity.",
            "rationale": "Site-level constraints determine facility feasibility before detailed design proceeds.",
            "priority": "High", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Local statutory/environmental authority requirements",
            "verification_method": "Document Review", "acceptance_criteria": "All statutory clearances on file prior to construction commencement.",
        },
    ],
    "Building Requirements": [
        {
            "requirement": "The building envelope shall provide a Building/Floor/Area/Room hierarchy that clearly segregates classified manufacturing space from unclassified support space, with defined adjacencies and access points.",
            "rationale": "The building layout is the physical basis for the pressure cascade and personnel/material flow strategy.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, ISPE Baseline Guide Vol. 2/3",
            "verification_method": "Design Review", "acceptance_criteria": "Facility layout drawing shows every declared building/floor/area/room with classification and adjacency.",
        },
        {
            "requirement": "Interior surfaces (walls, floors, ceilings) in classified manufacturing areas shall be smooth, impervious, and free from cracks and open joints to facilitate effective cleaning.",
            "rationale": "Surface finish is a direct cleanability and contamination-control requirement.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR 211.42, EU GMP Chapter 3",
            "verification_method": "Inspection", "acceptance_criteria": "Finish specification confirmed against approved materials list for each classified room.",
        },
    ],
    "Architectural Requirements": [
        {
            "requirement": "Room finishes, coving, and penetration sealing shall be specified per room classification to eliminate particulate/microbial harbourage points.",
            "rationale": "Architectural detailing directly supports the room's cleanroom classification.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ISO 14644, EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Architectural finish schedule cross-referenced to room classification schedule.",
        },
    ],
    "Cleanroom Requirements": [
        {
            "requirement": "Each manufacturing, packaging, and QC room shall be assigned a documented cleanroom classification (ISO 14644-1 class or EU GMP Grade) commensurate with product exposure risk.",
            "rationale": "Classification is the design basis for HVAC, gowning, and monitoring requirements.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ISO 14644-1, EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Room classification schedule approved by Quality prior to detailed HVAC design.",
        },
        {
            "requirement": "The facility shall maintain a documented pressure cascade between rooms of differing classification, with differential pressure targets defined for each boundary.",
            "rationale": "Pressure cascade is the primary control preventing contamination migration between areas.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, ISPE Baseline Guide Vol. 3",
            "verification_method": "Design Review", "acceptance_criteria": "Pressure cascade diagram approved with differential targets at every classified boundary.",
        },
    ],
    "HVAC Requirements": [
        {
            "requirement": "HVAC systems shall maintain temperature, relative humidity, and air change rate within the ranges specified for each room's classification and process need.",
            "rationale": "Environmental control is a direct product-quality attribute for most dosage forms.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, ISPE Baseline Guide Vol. 2/3, ASHRAE",
            "verification_method": "Design Review / Testing", "acceptance_criteria": "Room data sheet issued for every classified/controlled room with T/RH/ACPH targets.",
        },
        {
            "requirement": "AHU segregation strategy shall be defined to prevent cross-contamination between incompatible products or processes sharing the facility.",
            "rationale": "Shared air handling is a recognised cross-contamination pathway.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, ICH Q9",
            "verification_method": "Design Review", "acceptance_criteria": "AHU-to-room allocation matrix reviewed and approved by Quality.",
        },
    ],
    "Utilities Requirements": [
        {
            "requirement": "All facility utilities (water, steam, compressed air, gases, electrical) required by the declared manufacturing process shall be identified, sized, and documented in a utility matrix.",
            "rationale": "A complete utility matrix is the design basis for all downstream utility system URS/DQ.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 4",
            "verification_method": "Document Review", "acceptance_criteria": "Utility matrix signed off covering every declared process/utility combination.",
        },
    ],
    "Water Systems": [
        {
            "requirement": "Purified Water and (where applicable) Water For Injection generation, storage, and distribution shall meet the current pharmacopoeial specification at every point of use.",
            "rationale": "Water quality is a critical material attribute for most pharmaceutical processes.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <1231>, Ph.Eur. Water monographs, EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Water system design basis approved with point-of-use specification for every user point.",
        },
    ],
    "Compressed Air Requirements": [
        {
            "requirement": "Product-contact and instrument compressed air branches shall meet a documented ISO 8573-1 purity class appropriate to their point of use.",
            "rationale": "Contaminated compressed air is a direct product-contamination pathway where product-contact.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ISO 8573-1, EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Purity class specified and documented for every compressed air branch.",
        },
    ],
    "Nitrogen Requirements": [
        {
            "requirement": "Where nitrogen is used for product blanketing or inerting, purity and residual oxygen content shall be specified and monitored at the point of use.",
            "rationale": "Inadequate inerting purity undermines the process control it is intended to provide.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "ISPE Baseline Guide — Process Gases",
            "verification_method": "Design Review", "acceptance_criteria": "Nitrogen purity specification documented for every blanketing/inerting use point.",
        },
    ],
    "Electrical Requirements": [
        {
            "requirement": "Standby/emergency power shall be sized to sustain GMP-critical loads (HVAC, utilities, BMS, environmental monitoring) through a defined outage duration without loss of classification or product hold.",
            "rationale": "Power interruption is a leading root cause of environmental-excursion deviations.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2, applicable national electrical code",
            "verification_method": "Design Review", "acceptance_criteria": "Load list and standby power sizing calculation approved.",
        },
    ],
    "BMS Requirements": [
        {
            "requirement": "The Building Management System shall monitor and alarm all GxP-critical environmental and utility parameters identified in the facility risk assessment, with electronic records meeting 21 CFR Part 11 where those parameters support batch disposition.",
            "rationale": "Continuous, auditable monitoring of critical parameters is required for batch release defensibility.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, GAMP 5, EU GMP Annex 11",
            "verification_method": "Design Review", "acceptance_criteria": "GxP-critical monitoring point list approved and mapped to BMS I/O.",
        },
    ],
    "EMS Requirements": [
        {
            "requirement": "Environmental monitoring point locations and frequency shall be defined by a documented risk assessment representative of worst-case product/personnel exposure.",
            "rationale": "Unrepresentative monitoring points can mask genuine contamination excursions.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 1, ISO 14644-2",
            "verification_method": "Document Review", "acceptance_criteria": "EM point map and rationale approved by Quality.",
        },
    ],
    "Material Flow": [
        {
            "requirement": "Material flow from receipt through dispensing, processing, packaging, and finished-goods release shall be unidirectional wherever practicable, minimizing backtracking through classified space.",
            "rationale": "Unidirectional flow reduces cross-contamination and mix-up risk.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, WHO TRS 961",
            "verification_method": "Design Review", "acceptance_criteria": "Material flow diagram approved showing no unmitigated flow reversal through classified space.",
        },
    ],
    "Personnel Flow": [
        {
            "requirement": "Personnel flow shall route through a defined gowning sequence appropriate to the destination room's classification, with segregated entry/exit where required to preserve the pressure cascade.",
            "rationale": "Personnel are a primary contamination vector; gowning sequence design directly mitigates this.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 1, Chapter 3",
            "verification_method": "Design Review", "acceptance_criteria": "Personnel flow and gowning diagram approved for every classified area.",
        },
    ],
    "Waste Flow": [
        {
            "requirement": "Waste (solid, liquid, and — where applicable — biohazard/potent-compound) flow shall be segregated from product and personnel flow and shall not transit classified areas after generation.",
            "rationale": "Waste is a contamination and cross-contamination vector if not physically segregated.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, local environmental regulations",
            "verification_method": "Design Review", "acceptance_criteria": "Waste flow diagram approved with no crossing of product/personnel flow paths.",
        },
    ],
    "GMP Requirements": [
        {
            "requirement": "The facility shall provide adequate space, segregation, and workflow to allow operations to be performed in a logical sequence consistent with GMP and to minimize the risk of mix-up.",
            "rationale": "Direct GMP requirement on premises design.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR 211.42, EU GMP Chapter 3",
            "verification_method": "Design Review", "acceptance_criteria": "Layout review confirms logical operational sequence with no identified mix-up risk.",
        },
    ],
    "Regulatory Requirements": [
        {
            "requirement": "The facility design shall satisfy the GMP expectations of every regulatory market declared for this facility (e.g., USFDA, EU GMP, WHO-GMP, CDSCO, PIC/S, TGA) at the strictest common denominator where markets differ.",
            "rationale": "A facility intended for multiple markets must be designed to the most stringent applicable requirement to avoid later re-work.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "As declared in the facility's Regulatory Market field",
            "verification_method": "Document Review", "acceptance_criteria": "Regulatory gap analysis completed and closed for every declared market.",
        },
    ],
    "Data Integrity Requirements": [
        {
            "requirement": "All GxP-critical electronic data generated by facility systems (BMS, EMS, access control where GxP-relevant) shall be attributable, legible, contemporaneous, original, and accurate (ALCOA+), with audit trail enabled.",
            "rationale": "Facility systems increasingly generate data that supports batch disposition and must meet the same data-integrity bar as process equipment.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, PIC/S Data Integrity Guidance",
            "verification_method": "Design Review", "acceptance_criteria": "Data integrity assessment completed for every GxP-critical facility system.",
        },
    ],
    "Automation Requirements": [
        {
            "requirement": "The extent of automation (manual, semi-automated, fully automated) for facility monitoring and control shall be defined per system based on criticality and shall be justified in the facility design basis.",
            "rationale": "Automation level drives validation scope and ongoing operational risk.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "GAMP 5",
            "verification_method": "Document Review", "acceptance_criteria": "Automation philosophy documented and approved per system.",
        },
    ],
    "Safety Requirements": [
        {
            "requirement": "The facility shall provide fire detection/suppression, emergency egress, and hazardous-material handling provisions compliant with applicable local fire and occupational safety codes.",
            "rationale": "Life-safety compliance is a non-negotiable design constraint independent of GMP.",
            "priority": "Critical", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Local fire/building code, OSHA or equivalent",
            "verification_method": "Document Review", "acceptance_criteria": "Fire/life-safety design approved by the local Authority Having Jurisdiction.",
        },
    ],
    "Maintenance Requirements": [
        {
            "requirement": "Critical facility systems shall provide maintenance access (catwalks, service corridors, isolation valves) without requiring entry through classified production space during routine maintenance.",
            "rationale": "Maintenance access design prevents maintenance activity from becoming a contamination event.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2",
            "verification_method": "Design Review", "acceptance_criteria": "Service corridor/interstitial space design confirmed to avoid classified-area maintenance entry for routine tasks.",
        },
    ],
    "Training Requirements": [
        {
            "requirement": "Personnel operating or entering classified areas shall complete documented gowning, hygiene, and area-specific GMP training prior to unsupervised access.",
            "rationale": "Personnel behaviour is a leading contamination-control variable; training is the primary control.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR 211.25, EU GMP Chapter 2",
            "verification_method": "Document Review", "acceptance_criteria": "Training curriculum defined per area/role prior to facility occupancy.",
        },
    ],
    "Documentation": [
        {
            "requirement": "The facility design shall be fully documented (layout drawings, room data sheets, utility matrix, pressure cascade diagram, flow diagrams) sufficient to support Design Qualification.",
            "rationale": "Complete design documentation is the prerequisite for the Stage 2 DQ/IQ/OQ/PQ lifecycle.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15, ASTM E2500",
            "verification_method": "Document Review", "acceptance_criteria": "Design documentation package complete and version-controlled prior to DQ.",
        },
    ],
    "Sustainability Requirements": [
        {
            "requirement": "The facility design shall consider energy efficiency and resource-consumption reduction measures (heat recovery, variable-speed drives, water reuse where GMP-compatible) without compromising GMP compliance.",
            "rationale": "Sustainability is an increasingly common stakeholder requirement that must be reconciled with, not traded against, GMP compliance.",
            "priority": "Low", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Company ESG policy (where applicable)",
            "verification_method": "Document Review", "acceptance_criteria": "Sustainability measures documented and confirmed not to compromise any GMP-critical requirement.",
        },
    ],
    "Risk Considerations": [
        {
            "requirement": "A facility-level quality risk assessment shall be performed covering cross-contamination, mix-up, utility failure, and data-integrity risks, with mitigations reflected in the design.",
            "rationale": "A documented risk basis is expected for every major design decision under ICH Q9.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q9 — Quality Risk Management",
            "verification_method": "Document Review", "acceptance_criteria": "Facility risk assessment approved prior to detailed design freeze.",
        },
    ],
    "Future Expansion Requirements": [
        {
            "requirement": "The facility design shall reserve identified space, utility capacity, and structural allowance for the stated future expansion scope without requiring shutdown of existing classified operations during expansion construction.",
            "rationale": "Retrofitting a live GMP facility is materially more disruptive and risky than designing expansion allowance in from the outset.",
            "priority": "Medium", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2 (facility master planning)",
            "verification_method": "Document Review", "acceptance_criteria": "Expansion allowance (space/utility/structural) documented and reviewed against the stated future scope.",
        },
    ],
}


# ── Facility-type overlays — additional requirements for high-divergence
#    sections only, layered on top of FACILITY_COMMON_REQUIREMENTS ────────────

FACILITY_TYPE_OVERLAYS: dict[str, dict[str, list[dict]]] = {
    "OSD (Oral Solid Dosage)": {
        "HVAC Requirements": [
            {
                "requirement": "Dust-generating operations (granulation, compression, coating) shall be served by dedicated dust extraction integrated with the room HVAC to control airborne particulate and cross-contamination.",
                "rationale": "Powder/dust handling is the dominant contamination vector in OSD manufacturing.",
                "priority": "High", "gmp_criticality": "GMP",
                "regulatory_ref": "ISPE Baseline Guide Vol. 2",
                "verification_method": "Design Review", "acceptance_criteria": "Dust extraction integration confirmed for every powder-handling room.",
            },
        ],
    },
    "Injectable (Sterile)": {
        "Cleanroom Requirements": [
            {
                "requirement": "Aseptic processing areas shall be designed to EU GMP Annex 1 Grade A/B (ISO 5/7) with unidirectional airflow at the point of fill and continuous viable/non-viable monitoring.",
                "rationale": "Sterile injectable manufacture carries the highest contamination-control regulatory expectation.",
                "priority": "Critical", "gmp_criticality": "GMP-Critical",
                "regulatory_ref": "EU GMP Annex 1",
                "verification_method": "Design Review", "acceptance_criteria": "Grade A/B zone boundaries and unidirectional airflow design confirmed at the fill point.",
            },
        ],
        "Water Systems": [
            {
                "requirement": "Water For Injection shall be available at the point of use for final rinse and formulation, generated and stored per the current Ph.Eur./USP monograph.",
                "rationale": "WFI is mandatory for parenteral product contact.",
                "priority": "Critical", "gmp_criticality": "GMP-Critical",
                "regulatory_ref": "Ph.Eur./USP WFI monograph, EU GMP Annex 1",
                "verification_method": "Design Review", "acceptance_criteria": "WFI point-of-use list confirmed against every sterile-contact use point.",
            },
        ],
    },
    "API (Active Pharmaceutical Ingredient)": {
        "Waste Flow": [
            {
                "requirement": "Solvent recovery and hazardous-waste handling systems shall be designed to segregate process solvent waste from general facility waste and to meet applicable environmental discharge/emission limits.",
                "rationale": "API synthesis commonly involves hazardous solvents requiring dedicated handling distinct from OSD/injectable waste streams.",
                "priority": "High", "gmp_criticality": "Non-GMP",
                "regulatory_ref": "Local environmental/hazardous-waste regulations",
                "verification_method": "Design Review", "acceptance_criteria": "Solvent/hazardous waste handling design reviewed by EHS and approved.",
            },
        ],
    },
    "Warehouse / Distribution Center": {
        "HVAC Requirements": [
            {
                "requirement": "Storage areas for temperature-sensitive material shall be mapped and monitored to demonstrate uniform temperature distribution within the declared storage condition range.",
                "rationale": "Storage temperature excursion is the leading GDP finding for warehouse facilities.",
                "priority": "High", "gmp_criticality": "GMP",
                "regulatory_ref": "WHO GDP guidance, EU GDP Guidelines",
                "verification_method": "Design Review", "acceptance_criteria": "Temperature mapping study plan defined for every declared storage condition zone.",
            },
        ],
    },
    "QC Laboratory": {
        "HVAC Requirements": [
            {
                "requirement": "Instrument rooms and sample-preparation areas shall maintain the temperature/humidity stability required by the installed analytical instrumentation (e.g., HPLC, balances).",
                "rationale": "Analytical instrument performance is sensitive to environmental variation.",
                "priority": "High", "gmp_criticality": "GMP",
                "regulatory_ref": "Instrument manufacturer specifications, USP <1058>",
                "verification_method": "Design Review", "acceptance_criteria": "Environmental stability confirmed against the most sensitive instrument's specification.",
            },
        ],
    },
    "R&D Facility": {
        "Material Flow": [
            {
                "requirement": "Development-scale equipment and pilot batches shall follow a material flow that prevents cross-contamination between concurrent, unrelated development programs.",
                "rationale": "R&D facilities typically run multiple concurrent development programs with higher product/process variability than commercial manufacturing.",
                "priority": "Medium", "gmp_criticality": "GMP",
                "regulatory_ref": "ICH Q9",
                "verification_method": "Design Review", "acceptance_criteria": "Program segregation strategy documented for concurrent development activities.",
            },
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Stage 1.1 — Business Intelligence metadata
#
# Adds four more overlay axes on top of Stage 1's FACILITY_TYPE_OVERLAYS
# (kept unchanged above, still applied first): Facility Classification,
# Product Category (now a constrained value set, still stored in the same
# `facilities.product_category` column Stage 1 already created), Regulatory
# Package, and Validation Strategy. Two more inputs — per-utility design
# philosophy and future-expansion capacity — don't fit a static per-value
# dict (48 system×philosophy combinations, and expansion numbers are
# free-form) so they're synthesized programmatically instead; see
# _synthesize_utility_philosophy_requirements() and
# _synthesize_expansion_requirement() below.
#
# All of this is purely additive to get_facility_library_requirements()'s
# merge chain — no existing section, dict, or call signature is removed or
# renamed, and every new parameter on the public functions is keyword-only
# with a default, so `build_numbered_facility_requirements(facility_type)`
# (Stage 1's only call shape) still works unchanged.
# ═══════════════════════════════════════════════════════════════════════════

# ── Dropdown/checklist value sets (single source of truth for routes/
#    facility.py's /facility/design-basis-options and this module's own
#    validation) ────────────────────────────────────────────────────────────

PRODUCT_CATEGORIES = [
    "Tablets", "Capsules", "Oral Liquids", "Ointments", "Injectables",
    "Ophthalmic", "API", "Biologics", "Nutraceuticals", "Medical Devices",
    "Multiple Products",
]

REGULATORY_PACKAGE_OPTIONS = [
    "US FDA", "EU GMP", "WHO GMP", "PIC/S", "MHRA", "TGA", "ANVISA",
    "Schedule M", "ISO 14644", "Annex 1", "Annex 15",
]

UTILITY_SYSTEMS_FOR_PHILOSOPHY = [
    "HVAC", "Purified Water", "WFI", "Compressed Air", "Nitrogen",
    "Vacuum", "Steam", "Electrical",
]

UTILITY_PHILOSOPHY_OPTIONS = [
    "Centralized", "Dedicated", "Shared", "N+1 Redundancy",
    "2N Redundancy", "Standby Only",
]

VALIDATION_STRATEGY_OPTIONS = [
    "Traditional Validation", "ASTM E2500", "CSA", "Risk-Based Validation",
]

REQUIREMENT_SOURCE_OPTIONS = [
    "Corporate Standard", "Customer Requirement", "Regulatory Requirement",
    "Internal SOP", "Engineering Standard", "User Defined",
]

CAPACITY_UNIT_OPTIONS = [
    "Tablets/day", "Capsules/day", "Bottles/day", "Vials/day", "Units/day",
    "Tablets/year", "Tons/year", "Other",
]


# ── Facility Classification overlay ───────────────────────────────────────
# "Manufacturing Facility" (the generic default) has no overlay of its own
# — FACILITY_COMMON_REQUIREMENTS + the product-category overlay already
# describe a generic manufacturing facility.

CLASSIFICATION_OVERLAYS: dict[str, dict[str, list[dict]]] = {
    "Brownfield": {
        "Building Requirements": [{
            "requirement": "The facility design shall document all tie-in points to existing structure, utilities, and services, and shall identify any existing conditions (structural, contamination history, utility capacity) that constrain the new design.",
            "rationale": "A brownfield project inherits constraints a greenfield design does not — undocumented tie-ins are a common source of late-stage rework.",
            "priority": "High", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2 (facility master planning)",
            "verification_method": "Design Review", "acceptance_criteria": "Existing-conditions survey and tie-in schedule completed and approved before detailed design.",
        }],
    },
    "Expansion": {
        "Risk Considerations": [{
            "requirement": "Construction and commissioning activities shall be sequenced and contained to prevent disruption of environmental classification, utility availability, or product quality in any adjacent, currently-operating GMP area.",
            "rationale": "An expansion project runs alongside live GMP manufacturing — the construction interface itself becomes a contamination and quality risk.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, ICH Q9",
            "verification_method": "Design Review", "acceptance_criteria": "Construction interface/containment plan approved by Quality before work begins adjacent to operating areas.",
        }],
    },
    "Contract Manufacturing": {
        "GMP Requirements": [{
            "requirement": "Where the facility manufactures for multiple clients, the design shall support product/client segregation (dedicated or validated changeover between shared areas and equipment) and per-client batch record and material traceability.",
            "rationale": "Contract manufacturing carries a cross-client mix-up and confidentiality risk that a single-owner facility does not.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3 and 5",
            "verification_method": "Design Review", "acceptance_criteria": "Client segregation strategy (dedicated vs. shared-with-changeover) documented per area/equipment.",
        }],
    },
    "Warehouse": {
        "Building Requirements": [{
            "requirement": "Racking, staging, and quarantine areas shall be physically or systematically segregated (quarantine, released, rejected, returned) with unambiguous status identification.",
            "rationale": "Storage status mix-up is the principal GDP risk in a warehouse-classified facility.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "WHO GDP guidance, EU GDP Guidelines",
            "verification_method": "Design Review", "acceptance_criteria": "Status-segregation layout (quarantine/released/rejected/returned) approved.",
        }],
    },
    "Distribution Center": {
        "Material Flow": [{
            "requirement": "Dispatch and cross-docking flow shall be designed to minimize product dwell time outside controlled storage conditions and to maintain chain-of-custody traceability through loading.",
            "rationale": "A distribution center's principal risk is excursion during the receipt-to-dispatch window, not long-term storage.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "WHO GDP guidance",
            "verification_method": "Design Review", "acceptance_criteria": "Dispatch/cross-dock flow and dwell-time control confirmed in the design.",
        }],
    },
    "QC Laboratory": {
        "Personnel Flow": [{
            "requirement": "Sample receipt, testing, and retention areas shall be laid out to prevent cross-contamination between test samples and to maintain chain-of-custody from receipt through disposition.",
            "rationale": "Sample integrity and chain-of-custody are the QC laboratory's core data-integrity concern.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "USP <1058>, EU GMP Chapter 6",
            "verification_method": "Design Review", "acceptance_criteria": "Sample flow (receipt → testing → retention/disposal) documented with no cross-contamination path identified.",
        }],
    },
    "R&D Center": {
        "Building Requirements": [{
            "requirement": "Laboratory and pilot spaces shall be designed for reconfigurability (modular services, movable partitions where feasible) to accommodate changing development programs without major structural rework.",
            "rationale": "R&D program scope changes far more frequently than commercial manufacturing scope.",
            "priority": "Medium", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2",
            "verification_method": "Design Review", "acceptance_criteria": "Reconfigurability provisions (modular services/partitions) documented where feasible.",
        }],
    },
    "Pilot Plant": {
        "Automation Requirements": [{
            "requirement": "Process equipment and utilities shall be sized and skid-mounted where practicable to support scale-up/scale-down between development batch sizes without facility modification.",
            "rationale": "A pilot plant's value is flexibility across batch scales, not fixed-scale throughput optimization.",
            "priority": "Medium", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2",
            "verification_method": "Design Review", "acceptance_criteria": "Scale-up/scale-down flexibility confirmed for the declared batch-size range.",
        }],
    },
}


# ── Product Category overlay (Stage 1.1's constrained value set — distinct
#    from, and additive to, Stage 1's FACILITY_TYPE_OVERLAYS above) ───────

PRODUCT_CATEGORY_OVERLAYS: dict[str, dict[str, list[dict]]] = {
    "Tablets": {
        "HVAC Requirements": [{
            "requirement": "Compression and coating rooms shall be served by dust extraction sized for the declared tablet throughput, with make-up air balanced to maintain the room's pressure cascade under extraction load.",
            "rationale": "Tablet compression/coating is the facility's highest particulate-generation process step.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2",
            "verification_method": "Design Review", "acceptance_criteria": "Dust extraction capacity and make-up air balance confirmed against declared throughput.",
        }],
    },
    "Capsules": {
        "HVAC Requirements": [{
            "requirement": "Capsule filling and storage areas shall maintain relative humidity within the range specified by the shell material (gelatin or HPMC) to prevent brittleness or softening.",
            "rationale": "Capsule shell integrity is directly humidity-dependent, more so than tablet processing.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "USP General Chapters — Capsules",
            "verification_method": "Design Review", "acceptance_criteria": "RH range specified and confirmed against the declared shell material.",
        }],
    },
    "Oral Liquids": {
        "Water Systems": [{
            "requirement": "Purified Water used as a formulation vehicle shall be available at the point of compounding with microbial and endotoxin monitoring appropriate to the product's preservative system.",
            "rationale": "Water is typically the majority excipient by mass in an oral liquid, making its microbial quality directly product-critical.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <1231>, Ph.Eur. Purified Water monograph",
            "verification_method": "Design Review", "acceptance_criteria": "PW point-of-use confirmed at every compounding vessel.",
        }],
    },
    "Ointments": {
        "Cleanroom Requirements": [{
            "requirement": "Semi-solid compounding and filling areas shall be designed for effective cleaning of lipid/grease-based residues, with cleaning-validation-compatible surface finishes and drainage.",
            "rationale": "Ointment/cream bases are materially harder to clean-validate than aqueous products.",
            "priority": "Medium", "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Design Review", "acceptance_criteria": "Surface finish/drainage design confirmed compatible with the declared cleaning validation approach.",
        }],
    },
    "Injectables": {
        "Cleanroom Requirements": [{
            "requirement": "Filling and closure areas shall meet EU GMP Annex 1 Grade A (background Grade B/C per operation) with a documented Contamination Control Strategy covering the full aseptic process.",
            "rationale": "Injectable products bypass the body's natural barriers, carrying the highest sterility-assurance expectation of any dosage form.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1",
            "verification_method": "Design Review", "acceptance_criteria": "Grade A/B/C zoning and a facility-level Contamination Control Strategy documented and approved.",
        }],
    },
    "Ophthalmic": {
        "Cleanroom Requirements": [{
            "requirement": "Ophthalmic filling areas shall be designed to the sterility assurance level applicable to the declared container/closure system (single-dose or multi-dose with preservative), consistent with Annex 1 principles.",
            "rationale": "Ophthalmic products are applied to a sterile body surface and carry a sterility expectation close to injectables, but container/closure system materially changes the design basis.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, USP <771>",
            "verification_method": "Design Review", "acceptance_criteria": "Sterility assurance design basis documented against the declared container/closure system.",
        }],
    },
    "API": {
        "Waste Flow": [{
            "requirement": "Solvent handling, recovery, and hazardous-waste systems shall be sized for the declared synthesis route and shall meet local environmental discharge/emission limits.",
            "rationale": "API synthesis chemistry (not formulation) drives solvent volume and hazard classification.",
            "priority": "High", "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Local environmental/hazardous-waste regulations, ICH Q7",
            "verification_method": "Design Review", "acceptance_criteria": "Solvent recovery/hazardous waste capacity confirmed against the declared synthesis route.",
        }],
    },
    "Biologics": {
        "HVAC Requirements": [{
            "requirement": "Cell culture, fermentation, and downstream processing areas shall be designed for the declared biosafety level, with containment (not only cleanliness) as a co-equal design driver, and shall confirm compatibility with single-use system disposal logistics where used.",
            "rationale": "Biologics manufacturing must control both contamination INTO the process and containment of biological material OUT of it — a two-directional requirement OSD/injectable HVAC design does not have.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, WHO TRS on biological products",
            "verification_method": "Design Review", "acceptance_criteria": "Biosafety level and containment design basis documented; single-use system logistics confirmed if applicable.",
        }],
    },
    "Nutraceuticals": {
        "GMP Requirements": [{
            "requirement": "The facility shall document which GMP framework governs each product line (pharmaceutical GMP vs. dietary supplement/food GMP) where the facility manufactures across that boundary, and shall design to the stricter applicable requirement in shared areas.",
            "rationale": "Nutraceutical facilities frequently straddle pharmaceutical and food/supplement regulatory frameworks, which have materially different premises requirements.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "Applicable national dietary supplement/food GMP regulation, alongside declared pharma GMP",
            "verification_method": "Document Review", "acceptance_criteria": "Governing GMP framework documented per product line and per shared area.",
        }],
    },
    "Medical Devices": {
        "Regulatory Requirements": [{
            "requirement": "Where the facility manufactures medical devices, the quality system and premises requirements shall additionally satisfy ISO 13485, which is not automatically satisfied by pharmaceutical GMP compliance alone.",
            "rationale": "Medical device manufacturing sits under a distinct quality-system standard (ISO 13485) from pharmaceutical GMP — the two are complementary, not substitutable.",
            "priority": "High", "gmp_criticality": "GMP",
            "regulatory_ref": "ISO 13485",
            "verification_method": "Document Review", "acceptance_criteria": "ISO 13485 applicability confirmed and gap-assessed against the facility design.",
        }],
    },
    "Multiple Products": {
        "Material Flow": [{
            "requirement": "Changeover and cleaning validation between distinct product lines sharing an area or equipment train shall be documented with a cross-contamination risk assessment covering potency, allergenicity, and sensitization potential.",
            "rationale": "Multi-product facilities carry a cross-contamination risk that single-product facilities structurally avoid.",
            "priority": "Critical", "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3 and 5, EMA/ICH Q9 dedicated-facility guidance",
            "verification_method": "Design Review", "acceptance_criteria": "Cross-contamination risk assessment completed for every shared area/equipment train.",
        }],
    },
}


# ── Regulatory Package overlay — applied only for the frameworks the
#    facility actually selected (see _normalize_regulatory_selection below),
#    so the generated document cites what was chosen, not a fixed boilerplate
#    list ─────────────────────────────────────────────────────────────────

REGULATORY_OVERLAYS: dict[str, dict[str, list[dict]]] = {
    "US FDA": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy 21 CFR Part 211 premises requirements (Subpart C) for any area intended to support US-market product.",
        "rationale": "US FDA is a declared regulatory market for this facility.",
        "priority": "Critical", "gmp_criticality": "GMP-Critical", "regulatory_ref": "21 CFR Part 211 Subpart C",
        "verification_method": "Document Review", "acceptance_criteria": "21 CFR 211 Subpart C gap assessment completed.",
    }]},
    "EU GMP": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy EU GMP Chapter 3 (Premises and Equipment) for any area intended to support EU-market product.",
        "rationale": "EU GMP is a declared regulatory market for this facility.",
        "priority": "Critical", "gmp_criticality": "GMP-Critical", "regulatory_ref": "EU GMP Chapter 3",
        "verification_method": "Document Review", "acceptance_criteria": "EU GMP Chapter 3 gap assessment completed.",
    }]},
    "WHO GMP": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy WHO GMP (TRS series) premises requirements for any area intended for WHO-prequalified or export product.",
        "rationale": "WHO GMP is a declared regulatory market for this facility.",
        "priority": "High", "gmp_criticality": "GMP", "regulatory_ref": "WHO TRS GMP guidance",
        "verification_method": "Document Review", "acceptance_criteria": "WHO GMP gap assessment completed.",
    }]},
    "PIC/S": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to align with the PIC/S GMP Guide, harmonizing with the requirements of every PIC/S-participating authority relevant to this facility's declared markets.",
        "rationale": "PIC/S is a declared regulatory market for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "PIC/S GMP Guide",
        "verification_method": "Document Review", "acceptance_criteria": "PIC/S alignment confirmed alongside the other declared frameworks.",
    }]},
    "MHRA": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy MHRA (UK) GMP expectations (the 'Orange Guide') for any area intended to support UK-market product.",
        "rationale": "MHRA is a declared regulatory market for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "MHRA GMP Guide (Orange Guide)",
        "verification_method": "Document Review", "acceptance_criteria": "MHRA-specific gap items identified and closed.",
    }]},
    "TGA": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy Australian TGA GMP requirements (PIC/S-aligned) for any area intended to support the Australian market.",
        "rationale": "TGA is a declared regulatory market for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "TGA GMP requirements",
        "verification_method": "Document Review", "acceptance_criteria": "TGA-specific gap items identified and closed.",
    }]},
    "ANVISA": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy Brazilian ANVISA GMP requirements (RDC series) for any area intended to support the Brazilian market.",
        "rationale": "ANVISA is a declared regulatory market for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "ANVISA RDC GMP regulations",
        "verification_method": "Document Review", "acceptance_criteria": "ANVISA-specific gap items identified and closed.",
    }]},
    "Schedule M": {"Regulatory Requirements": [{
        "requirement": "The facility shall be designed to satisfy Schedule M (Indian GMP) premises requirements for any area intended to support the Indian market.",
        "rationale": "Schedule M is a declared regulatory market for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "Schedule M — Good Manufacturing Practices (India)",
        "verification_method": "Document Review", "acceptance_criteria": "Schedule M-specific gap items identified and closed.",
    }]},
    "ISO 14644": {"Cleanroom Requirements": [{
        "requirement": "Cleanroom classification and ongoing monitoring shall follow ISO 14644-1 (classification) and ISO 14644-2 (monitoring for continued compliance) explicitly, in addition to any GMP grade equivalence stated.",
        "rationale": "ISO 14644 was explicitly selected as a design standard for this facility.",
        "priority": "High", "gmp_criticality": "GMP", "regulatory_ref": "ISO 14644-1, ISO 14644-2",
        "verification_method": "Design Review", "acceptance_criteria": "ISO 14644-1 class and ISO 14644-2 monitoring plan documented per room.",
    }]},
    "Annex 1": {"Cleanroom Requirements": [{
        "requirement": "The facility shall maintain a documented, facility-wide Contamination Control Strategy (CCS) integrating all classified-area controls, per EU GMP Annex 1 (2022 revision).",
        "rationale": "Annex 1 was explicitly selected as a design standard, and its central new requirement (relative to the prior revision) is the holistic CCS.",
        "priority": "Critical", "gmp_criticality": "GMP-Critical", "regulatory_ref": "EU GMP Annex 1",
        "verification_method": "Document Review", "acceptance_criteria": "Facility-wide Contamination Control Strategy document initiated and scoped.",
    }]},
    "Annex 15": {"Documentation": [{
        "requirement": "The facility's qualification and validation lifecycle documentation (validation master plan, qualification protocols, change control) shall follow EU GMP Annex 15 structure and terminology.",
        "rationale": "Annex 15 was explicitly selected as a design standard for this facility.",
        "priority": "High", "gmp_criticality": "GMP", "regulatory_ref": "EU GMP Annex 15",
        "verification_method": "Document Review", "acceptance_criteria": "Validation Master Plan structure confirmed to follow Annex 15 terminology ahead of Stage 2.",
    }]},
}


# ── Validation Strategy overlay ────────────────────────────────────────────

VALIDATION_STRATEGY_OVERLAYS: dict[str, dict[str, list[dict]]] = {
    "Traditional Validation": {"Documentation": [{
        "requirement": "The facility's qualification lifecycle shall follow the traditional Installation Qualification / Operational Qualification / Performance Qualification (IQ/OQ/PQ) protocol sequence for all direct-impact systems.",
        "rationale": "Traditional Validation was the selected validation strategy for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "EU GMP Annex 15",
        "verification_method": "Document Review", "acceptance_criteria": "IQ/OQ/PQ protocol structure confirmed in the Validation Master Plan (Stage 2).",
    }]},
    "ASTM E2500": {"Documentation": [{
        "requirement": "The facility's qualification lifecycle shall follow a science- and risk-based verification approach per ASTM E2500, integrating commissioning and qualification activities rather than treating them as sequential, separately-documented phases.",
        "rationale": "ASTM E2500 was the selected validation strategy for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "ASTM E2500",
        "verification_method": "Document Review", "acceptance_criteria": "Commissioning/qualification integration approach documented ahead of Stage 2.",
    }]},
    "CSA": {"Automation Requirements": [{
        "requirement": "Computerized and automated systems within the facility (BMS, EMS, and equivalent) shall be assured using a risk-based Computer Software Assurance approach, prioritizing critical-thinking-based testing over exhaustive scripted verification for low-risk functions.",
        "rationale": "CSA (Computer Software Assurance) was the selected validation strategy for this facility's computerized systems.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "FDA CSA guidance, GAMP 5",
        "verification_method": "Document Review", "acceptance_criteria": "CSA risk-based test-method allocation documented for each computerized system.",
    }]},
    "Risk-Based Validation": {"Risk Considerations": [{
        "requirement": "The scope and depth of qualification activities for each facility system shall be determined by a documented ICH Q9 risk assessment, with verification effort concentrated on GMP-Critical systems and reduced, justified verification for Non-GMP systems.",
        "rationale": "Risk-Based Validation was the selected validation strategy for this facility.",
        "priority": "Medium", "gmp_criticality": "GMP", "regulatory_ref": "ICH Q9",
        "verification_method": "Document Review", "acceptance_criteria": "Risk-based qualification scope matrix documented per system ahead of Stage 2.",
    }]},
}


# ── Programmatic synthesis (not static dicts — inputs are open-ended) ─────

_UTILITY_SYSTEM_TO_SECTION = {
    "HVAC": "HVAC Requirements",
    "Purified Water": "Water Systems",
    "WFI": "Water Systems",
    "Compressed Air": "Compressed Air Requirements",
    "Nitrogen": "Nitrogen Requirements",
    "Vacuum": "Utilities Requirements",
    "Steam": "Utilities Requirements",
    "Electrical": "Electrical Requirements",
}


def _synthesize_utility_philosophy_requirements(utility_philosophy: dict[str, str]) -> dict[str, list[dict]]:
    """One requirement per system that actually has a philosophy selected —
    not a static 8-system x 6-philosophy (48-entry) dict, since the
    combination is user-chosen and the wording is formulaic enough to
    template directly."""
    result: dict[str, list[dict]] = {}
    for system, philosophy in (utility_philosophy or {}).items():
        philosophy = (philosophy or "").strip()
        if not philosophy or system not in UTILITY_SYSTEMS_FOR_PHILOSOPHY:
            continue
        section = _UTILITY_SYSTEM_TO_SECTION.get(system, "Utilities Requirements")
        redundant = philosophy in ("N+1 Redundancy", "2N Redundancy")
        result.setdefault(section, []).append({
            "requirement": f"The {system} system shall be designed on a {philosophy} basis, consistent with the facility's declared utility design philosophy.",
            "rationale": f"Reflects the {philosophy} strategy selected for this facility's {system} system.",
            "priority": "High" if redundant else "Medium",
            "gmp_criticality": "GMP-Critical" if (redundant and system in ("HVAC", "WFI")) else "GMP",
            "regulatory_ref": "ISPE Baseline Guide Vol. 2 / Vol. 4",
            "verification_method": "Design Review",
            "acceptance_criteria": f"{system} system architecture confirmed as {philosophy} in the design basis and single-line/P&ID documentation.",
        })
    return result


def _synthesize_expansion_requirement(
    expandable_design: bool, future_capacity_value: str, future_capacity_unit: str,
    planned_expansion_pct: str,
) -> dict[str, list[dict]]:
    """Only emits when the facility declared itself expandable — an
    Expandable Design = No facility gets no extra expansion requirement
    beyond the Stage 1 baseline."""
    if not expandable_design:
        return {}
    capacity_phrase = (
        f"to {future_capacity_value} {future_capacity_unit}".strip()
        if future_capacity_value else "to the declared future capacity"
    )
    pct_phrase = f" ({planned_expansion_pct}% above current design capacity)" if planned_expansion_pct else ""
    return {"Future Expansion Requirements": [{
        "requirement": (
            f"The facility shall reserve identified space, structural allowance, and utility "
            f"capacity headroom sufficient to expand {capacity_phrase}{pct_phrase} without "
            f"requiring shutdown of existing GMP operations."
        ),
        "rationale": "Expandable Design was declared Yes for this facility — the expansion allowance must be sized against a stated target, not left generic.",
        "priority": "Medium", "gmp_criticality": "Non-GMP",
        "regulatory_ref": "ISPE Baseline Guide Vol. 2 (facility master planning)",
        "verification_method": "Design Review",
        "acceptance_criteria": "Reserved space/structural/utility headroom documented and quantified against the stated future capacity.",
    }]}


def _normalize_regulatory_selection(regulatory_package) -> list[str]:
    """Accepts either a list (from the wizard's checkbox payload) or a
    comma-joined string (the shape `facilities.regulatory_market` is stored
    in) so callers can pass either without converting first."""
    if isinstance(regulatory_package, list):
        return [r.strip() for r in regulatory_package if r and r.strip()]
    if isinstance(regulatory_package, str):
        return [r.strip() for r in regulatory_package.split(",") if r.strip()]
    return []


# ── Public API ──────────────────────────────────────────────────────────────

def get_facility_library_requirements(
    facility_type: str,
    *,
    product_category: str = "",
    classification: str = "",
    regulatory_package=None,
    utility_philosophy: dict[str, str] | None = None,
    validation_strategy: str = "",
    expandable_design: bool = False,
    future_capacity_value: str = "",
    future_capacity_unit: str = "",
    planned_expansion_pct: str = "",
) -> dict[str, list[dict]]:
    """Return merged requirement library for the given facility metadata.

    Always starts from FACILITY_COMMON_REQUIREMENTS so the full 27-section
    baseline is always included. Overlays are applied in a fixed order —
    facility type (Stage 1), product category, classification, regulatory
    package (Stage 1.1) — each only adding to the sections it targets, never
    removing or replacing a prior layer's content. Every parameter beyond
    `facility_type` is optional and defaults to "no overlay from this axis",
    so `get_facility_library_requirements(facility_type)` (Stage 1's call
    shape) still returns exactly Stage 1's result.
    """
    merged: dict[str, list[dict]] = {}
    for section, reqs in FACILITY_COMMON_REQUIREMENTS.items():
        merged[section] = list(reqs)

    def _apply(overlay: dict[str, list[dict]]) -> None:
        for section, reqs in overlay.items():
            merged.setdefault(section, [])
            merged[section] = merged[section] + list(reqs)

    _apply(FACILITY_TYPE_OVERLAYS.get(facility_type, {}))
    _apply(PRODUCT_CATEGORY_OVERLAYS.get(product_category, {}))
    _apply(CLASSIFICATION_OVERLAYS.get(classification, {}))
    for reg in _normalize_regulatory_selection(regulatory_package):
        _apply(REGULATORY_OVERLAYS.get(reg, {}))
    _apply(VALIDATION_STRATEGY_OVERLAYS.get(validation_strategy, {}))
    _apply(_synthesize_utility_philosophy_requirements(utility_philosophy or {}))
    _apply(_synthesize_expansion_requirement(
        expandable_design, future_capacity_value, future_capacity_unit, planned_expansion_pct,
    ))
    return merged


def build_numbered_facility_requirements(
    facility_type: str,
    *,
    product_category: str = "",
    classification: str = "",
    regulatory_package=None,
    utility_philosophy: dict[str, str] | None = None,
    validation_strategy: str = "",
    expandable_design: bool = False,
    future_capacity_value: str = "",
    future_capacity_unit: str = "",
    planned_expansion_pct: str = "",
    requirement_source: str = "",
) -> list[dict]:
    """Convert the facility library into a flat list with auto-generated
    req_id codes — same shape as urs_requirement_library.build_numbered_
    requirements() so it saves via the existing urs_database.save_
    requirements() unmodified. `requirement_source` (Stage 1.1) is stamped
    onto every returned requirement for RTM traceability — defaults to ''
    (unset), matching every requirement created before this field existed."""
    sections = get_facility_library_requirements(
        facility_type, product_category=product_category, classification=classification,
        regulatory_package=regulatory_package, utility_philosophy=utility_philosophy,
        validation_strategy=validation_strategy, expandable_design=expandable_design,
        future_capacity_value=future_capacity_value, future_capacity_unit=future_capacity_unit,
        planned_expansion_pct=planned_expansion_pct,
    )
    result = []
    section_counters: dict[str, int] = {}
    for section, reqs in sections.items():
        prefix = FACILITY_SECTION_PREFIX.get(section, "REQ")
        section_counters.setdefault(prefix, 0)
        for req in reqs:
            section_counters[prefix] += 1
            item = dict(req)
            item["req_id"] = f"{prefix}-{section_counters[prefix]:03d}"
            item["section"] = section
            item["status"] = "draft"
            item["source"] = "library"
            item["requirement_source"] = requirement_source
            result.append(item)
    return result


def list_facility_types() -> list[str]:
    return list(FACILITY_TYPES)


def get_sections_for_facility_type(facility_type: str) -> list[str]:
    return list(get_facility_library_requirements(facility_type).keys())
