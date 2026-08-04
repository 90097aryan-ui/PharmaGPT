"""Facility systems: HVAC, Environmental Monitoring System (EMS)."""

from pharmagpt.facility_systems import FacilitySystemProfile, _register

# ─── HVAC ───────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="HVAC",
    category="HVAC & Environmental",
    aliases=[
        "heating ventilation and air conditioning", "air handling", "ahu",
        "air handling unit", "hvac system", "cleanroom hvac",
    ],
    description=(
        "Heating, Ventilation and Air Conditioning system serving classified and "
        "unclassified manufacturing, warehouse, and QC areas. Provides temperature, "
        "relative humidity, air change rate, pressure cascade, and particulate/microbial "
        "control appropriate to each room's cleanroom classification. Typically zoned by "
        "AHU per area/pressure-cascade group with HEPA terminal filtration for classified "
        "space and pre/fine filtration upstream."
    ),
    applicable_regulations=[
        "EU GMP Annex 1 — Manufacture of Sterile Medicinal Products (room classification, "
        "pressure cascades, recovery)",
        "ISO 14644-1/-2 — Cleanroom classification and monitoring",
        "ISPE Baseline Guide Vol. 2 — Oral Solid Dosage Facilities",
        "ISPE Baseline Guide Vol. 3 — Sterile Manufacturing Facilities",
        "WHO TRS 961 Annex 5 — HVAC systems for non-sterile pharmaceutical products",
        "ASHRAE Applications Handbook — Pharmaceutical facilities chapter",
    ],
    design_considerations=[
        "Room classification basis (Grade A/B/C/D or ISO 5/7/8) driven by process/product exposure",
        "Pressure cascade direction and differential targets between adjacent rooms",
        "Air change rate (ACPH) per room classification and heat/moisture load",
        "Temperature and relative humidity set points and control bands per room",
        "Filtration train (pre-filter / fine filter / HEPA) and filter integrity test access",
        "Recovery time after door-opening/intervention for classified spaces",
        "Segregation of AHUs by product/cross-contamination risk (dedicated vs shared)",
        "Energy recovery and standby/redundancy philosophy for critical AHUs",
    ],
    critical_parameters=[
        "Temperature range and tolerance per room type",
        "Relative humidity range and tolerance per room type",
        "Air changes per hour (ACPH) per classification grade",
        "Room-to-room pressure differential (Pa) and cascade direction",
        "HEPA filter efficiency and in-situ integrity test requirement",
        "Non-viable and viable particulate limits per classification",
    ],
    typical_interfaces=[
        "Building Management System (BMS) — monitoring and alarm",
        "Environmental Monitoring System (EMS) — viable/non-viable particulate data",
        "Electrical distribution — AHU motor/control power",
        "Fire alarm system — smoke damper interlock",
    ],
    common_risks=[
        "Cross-contamination via inadequate pressure cascade or AHU segregation",
        "Loss of classification during power failure without standby/alarm philosophy",
        "Condensation/microbial growth from RH excursions",
        "Inadequate recovery time after material/personnel transfer events",
    ],
))

# ─── Environmental Monitoring System (EMS) ──────────────────────────────────

_register(FacilitySystemProfile(
    name="EMS",
    category="HVAC & Environmental",
    aliases=[
        "environmental monitoring system", "environmental monitoring",
        "viable monitoring", "non-viable particle monitoring",
    ],
    description=(
        "Continuous/periodic monitoring system for viable and non-viable particulate "
        "counts, temperature, relative humidity, and differential pressure in classified "
        "manufacturing areas, alarming on excursion and providing electronic records for "
        "batch release and trend review."
    ),
    applicable_regulations=[
        "EU GMP Annex 1 — Environmental and Personnel Monitoring",
        "ISO 14644-2 — Monitoring for continued compliance with ISO 14644-1",
        "21 CFR Part 11 — Electronic Records and Electronic Signatures",
        "PIC/S GMP Guide — Environmental monitoring programme",
    ],
    design_considerations=[
        "Monitoring point locations mapped to a documented risk assessment",
        "Continuous vs. periodic (grab sample) monitoring per classification grade",
        "Alarm limits (alert/action) per parameter and location",
        "Data retention, trending, and audit-trail requirements (ALCOA+)",
        "Integration with BMS for centralised alarm annunciation",
    ],
    critical_parameters=[
        "Non-viable particle counts (0.5 µm and 5 µm) per monitoring point",
        "Viable count limits (settle plates, active air samplers, contact plates)",
        "Alert and action limits per grade/room",
        "Sampling frequency per point",
    ],
    typical_interfaces=[
        "HVAC — the system it monitors",
        "Building Management System (BMS) — alarm annunciation",
        "Quality/QC data systems — batch release review",
    ],
    common_risks=[
        "Monitoring points not representative of worst-case locations",
        "Alarm fatigue from poorly set alert/action limits",
        "Data integrity gaps if monitoring records are not electronically time-stamped/audit-trailed",
    ],
))
