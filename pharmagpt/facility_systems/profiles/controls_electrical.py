"""Facility systems: BMS, Electrical Distribution, Fire Alarm, Access Control."""

from pharmagpt.facility_systems import FacilitySystemProfile, _register

# ─── BMS ────────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="BMS",
    category="Controls & Electrical",
    aliases=["building management system", "building automation system", "bas"],
    description=(
        "Centralised monitoring and control platform for HVAC, utilities, and critical "
        "environmental parameters across the facility, providing alarm annunciation, "
        "trending, and (where GxP-critical) 21 CFR Part 11-compliant electronic records "
        "for parameters that support batch release or product quality decisions."
    ),
    applicable_regulations=[
        "21 CFR Part 11 — Electronic Records and Electronic Signatures (where GxP-critical)",
        "GAMP 5 — Computerised system validation, risk-based categorisation",
        "EU GMP Annex 11 — Computerised Systems",
        "ISPE Baseline Guide Vol. 2/5 — Automated systems",
    ],
    design_considerations=[
        "Scope of GxP-critical vs. facility (non-GxP) monitoring points, per a documented risk assessment",
        "Alarm philosophy: alert vs. action limits, escalation, and acknowledgement workflow",
        "Data historian retention period and backup/recovery strategy",
        "Audit trail configuration for any parameter feeding a batch disposition decision",
        "Network segregation from IT/business systems (cybersecurity)",
        "Redundancy/failover for continuous critical-parameter monitoring",
    ],
    critical_parameters=[
        "Alarm response time",
        "Data logging interval for GxP-critical parameters",
        "System uptime / redundancy target",
        "Audit trail completeness (who/what/when for every GxP-relevant change)",
    ],
    typical_interfaces=[
        "HVAC — monitoring and control points",
        "Environmental Monitoring System (EMS) — data aggregation",
        "Electrical Distribution — standby power status, breaker status",
        "Fire Alarm System — cross-alarm annunciation",
    ],
    common_risks=[
        "Undefined GxP-critical vs. non-critical point classification leading to validation gaps",
        "Alarm flooding from poorly tuned alert/action thresholds",
        "Data integrity gap if historian lacks audit trail on GxP-critical points",
    ],
))

# ─── Electrical Distribution ──────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Electrical Distribution",
    category="Controls & Electrical",
    aliases=["electrical system", "power distribution", "lv/hv distribution", "standby power"],
    description=(
        "Incoming HV/LV supply, transformers, main and sub-distribution boards, and "
        "standby/emergency power (generator, UPS) sized and segregated to keep "
        "GMP-critical loads (HVAC, utilities, BMS, process equipment) available through "
        "normal and emergency operating conditions."
    ),
    applicable_regulations=[
        "IEC 60364 / applicable national electrical code",
        "EU GMP Chapter 3 — Premises and Equipment (services segregation)",
        "ISPE Baseline Guide Vol. 2 — Facility utility design",
        "NFPA 110 (or equivalent) — Emergency and standby power systems",
    ],
    design_considerations=[
        "Load classification: normal, essential (generator-backed), UPS-backed (no-break) circuits",
        "Standby generator sizing, changeover time, and fuel autonomy",
        "UPS autonomy for critical instrumentation/BMS/control systems",
        "Segregation of clean/classified-area electrical infrastructure to avoid contamination ingress",
        "Single-line diagram documentation and future-expansion spare capacity",
    ],
    critical_parameters=[
        "Standby generator changeover time",
        "UPS autonomy (minutes) for critical loads",
        "Voltage stability / power quality at point of use",
        "Spare capacity margin for planned expansion",
    ],
    typical_interfaces=[
        "HVAC, utilities, BMS, process equipment — all downstream loads",
        "Fire Alarm System — emergency shutdown/interlock",
    ],
    common_risks=[
        "Undersized standby power causing loss of classification/product hold during outage",
        "Inadequate segregation of essential vs. non-essential loads on the same circuit",
    ],
))

# ─── Fire Alarm ────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Fire Alarm",
    category="Controls & Electrical",
    aliases=["fire detection system", "fire alarm system", "fas"],
    description=(
        "Facility-wide fire detection and alarm system with area-specific detector "
        "selection (smoke, heat, aspirating) interlocked with HVAC smoke dampers, "
        "electrical shutdown, and emergency egress signalling."
    ),
    applicable_regulations=[
        "NFPA 72 (or equivalent national fire code)",
        "Local fire/building code and occupancy classification requirements",
        "EU GMP Chapter 3 — Premises (safety provisions)",
    ],
    design_considerations=[
        "Detector type selection per area risk (solvent storage, electrical rooms, "
        "warehouse, classified manufacturing)",
        "Interlock logic with HVAC (smoke damper closure) and electrical shutdown",
        "Zone mapping and annunciation panel location(s)",
        "Integration with BMS for centralised alarm visibility",
    ],
    critical_parameters=[
        "Detector response time per zone",
        "Alarm annunciation and escalation time",
        "Interlock verification (HVAC shutdown, damper closure)",
    ],
    typical_interfaces=[
        "HVAC — smoke damper interlock",
        "Electrical Distribution — emergency shutdown interlock",
        "BMS — centralised alarm annunciation",
    ],
    common_risks=[
        "Interlock failure allowing smoke propagation through HVAC ductwork",
        "Detector type mismatched to area risk (e.g., ionisation detectors near solvent vapour)",
    ],
))

# ─── Access Control ────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Access Control",
    category="Controls & Electrical",
    aliases=["access control system", "badge access", "physical security", "personnel access control"],
    description=(
        "Electronic badge/biometric access control restricting entry to classified "
        "manufacturing areas, gowning rooms, material airlocks, and controlled-substance "
        "storage, with logged entry/exit events supporting personnel-flow traceability "
        "and data integrity of physical access to GMP areas."
    ),
    applicable_regulations=[
        "EU GMP Chapter 3 — Premises (restricted access to production areas)",
        "21 CFR Part 211.42 — Design and construction features (access control)",
        "Company-specific SOP on personnel gowning and area access qualification",
    ],
    design_considerations=[
        "Access hierarchy mapped to the facility's Building/Floor/Area/Room zoning and "
        "personnel-flow/gowning-level requirements",
        "Interlocking of airlock doors (mantrap logic) to preserve pressure cascade",
        "Event logging retention period and integration with the audit trail",
        "Emergency egress override that does not compromise fire/life-safety code",
    ],
    critical_parameters=[
        "Door interlock response (mantrap logic) for airlocks",
        "Access event log retention period",
        "Badge/biometric read reliability",
    ],
    typical_interfaces=[
        "HVAC — airlock door interlock preserving pressure cascade",
        "Fire Alarm System — emergency egress override",
        "BMS / audit trail systems — event log aggregation",
    ],
    common_risks=[
        "Airlock doors openable simultaneously, breaking pressure cascade and classification",
        "Access log gaps undermining personnel-flow traceability during an investigation",
    ],
))
