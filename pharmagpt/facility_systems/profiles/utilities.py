"""Facility systems: Purified Water, Water For Injection, Clean Steam,
Compressed Air, Nitrogen, Vacuum, CIP, SIP."""

from pharmagpt.facility_systems import FacilitySystemProfile, _register

# ─── Purified Water ─────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Purified Water",
    category="Process Utilities",
    aliases=["pw system", "purified water system", "pw generation", "pw loop"],
    description=(
        "Generation, storage, and distribution system producing Purified Water to "
        "pharmacopoeial specification for use as an excipient, cleaning medium, and "
        "feedwater to downstream systems (WFI, Clean Steam). Typically a continuously "
        "circulating loop maintained above ambient or at elevated temperature to control "
        "microbial proliferation, with UV/ozone sanitisation as applicable."
    ),
    applicable_regulations=[
        "USP <1231> — Water for Pharmaceutical Purposes",
        "Ph.Eur. Purified Water monograph",
        "EU GMP Annex 1 — Water systems for sterile manufacture",
        "ISPE Baseline Guide Vol. 4 — Water and Steam Systems",
        "WHO TRS 970 Annex 2 — Water for pharmaceutical use",
    ],
    design_considerations=[
        "Feedwater quality and pretreatment (softening, carbon, RO/EDI train)",
        "Storage and distribution loop design (continuous circulation, no dead-legs)",
        "Sanitisation method and frequency (thermal, chemical, UV, ozone)",
        "Materials of construction (316L SS, electropolished, orbital-welded)",
        "Total Organic Carbon (TOC), conductivity, and microbial/endotoxin monitoring",
        "Loop velocity and turbulent flow requirement to prevent biofilm",
    ],
    critical_parameters=[
        "Conductivity (USP <645>)",
        "Total Organic Carbon (TOC, USP <643>)",
        "Microbial bioburden (CFU/mL) action/alert limits",
        "Loop temperature and return pressure",
        "Endotoxin (if used as WFI feedwater)",
    ],
    typical_interfaces=[
        "Water For Injection system — feedwater source",
        "Clean Steam generator — feedwater source",
        "CIP system — cleaning water supply",
        "Building Management System — continuous monitoring/alarm",
    ],
    common_risks=[
        "Biofilm formation from stagnant loop segments or dead-legs",
        "Microbial excursion from inadequate sanitisation frequency",
        "Endotoxin carryover into WFI feedwater if pretreatment fails",
    ],
))

# ─── Water For Injection ─────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Water For Injection",
    category="Process Utilities",
    aliases=["wfi", "wfi system", "wfi generation", "wfi loop"],
    description=(
        "Generation (distillation or membrane-based per current pharmacopoeial "
        "allowance), storage, and hot/ambient distribution of Water For Injection for "
        "sterile product manufacture, final rinse, and clean/sterile steam generation. "
        "Storage typically maintained hot (>=80°C) or under continuous ozonation with "
        "point-of-use cooling to control microbial and endotoxin levels."
    ),
    applicable_regulations=[
        "USP <1231> and WFI monograph",
        "Ph.Eur. Water for Injections monograph (distillation and membrane-based production)",
        "EU GMP Annex 1 — Water systems for sterile manufacture",
        "ISPE Baseline Guide Vol. 4 — Water and Steam Systems",
    ],
    design_considerations=[
        "Generation technology (multi-effect distillation, vapour compression, or "
        "membrane-based per applicable pharmacopoeia)",
        "Storage/distribution temperature regime (hot loop vs. ozonated ambient loop)",
        "Point-of-use cooling and de-ozonation (if ambient loop)",
        "Materials of construction and sanitary design (no dead-legs, orbital welds)",
        "Endotoxin control strategy and monitoring points",
    ],
    critical_parameters=[
        "Conductivity (USP <645>)",
        "Total Organic Carbon (TOC, USP <643>)",
        "Bacterial endotoxin (USP <85>, action/alert limits)",
        "Microbial bioburden (CFU/100 mL) action/alert limits",
        "Loop temperature (if hot storage) or ozone residual (if ambient)",
    ],
    typical_interfaces=[
        "Purified Water system — feedwater source",
        "Clean Steam generator — feedwater source (where WFI-fed)",
        "Sterile manufacturing areas — point-of-use supply",
    ],
    common_risks=[
        "Endotoxin excursion from generation/storage temperature excursion",
        "Biofilm formation at point-of-use cooling stations",
        "Cross-contamination if distribution loop is not single-pass sanitary design",
    ],
))

# ─── Clean Steam ──────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Clean Steam",
    category="Process Utilities",
    aliases=["pure steam", "clean steam generator", "clean steam system"],
    description=(
        "Steam generated from Purified Water or WFI feedwater, free of boiler additives, "
        "used for humidification of classified areas, autoclave/SIP sterilisation, and "
        "direct product/equipment contact sterilisation processes."
    ),
    applicable_regulations=[
        "Ph.Eur. / USP Water for Injection monograph (as feedwater basis)",
        "EU GMP Annex 1 — Clean steam for sterilisation",
        "ISPE Baseline Guide Vol. 4 — Water and Steam Systems",
        "EN 285 — Sterilization, steam sterilizers, large (where SIP-linked)",
    ],
    design_considerations=[
        "Feedwater source (Purified Water vs. WFI) driven by end-use (humidification vs. "
        "direct sterile contact)",
        "Non-condensable gas, dryness fraction, and superheat limits for SIP applications",
        "Distribution design to point of use (jacketed piping, condensate management)",
        "Generator sizing against peak simultaneous demand (autoclaves, SIP skids)",
    ],
    critical_parameters=[
        "Non-condensable gas content (%)",
        "Dryness fraction / quality",
        "Superheat (°C)",
        "Condensate conductivity/TOC (feedwater carryover check)",
    ],
    typical_interfaces=[
        "Purified Water / WFI system — feedwater source",
        "Autoclaves and SIP skids — point-of-use consumers",
        "HVAC — humidification consumers",
    ],
    common_risks=[
        "Non-condensable gas exceeding SIP sterilisation-effectiveness limits",
        "Condensate backflow contaminating the clean steam generator",
    ],
))

# ─── Compressed Air ───────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Compressed Air",
    category="Process Utilities",
    aliases=["plant air", "instrument air", "clean compressed air", "process air"],
    description=(
        "Oil-free, filtered, and dried compressed air distribution for process use "
        "(pneumatic conveying, product-contact air), instrumentation, and general plant "
        "utility. Product-contact and instrument-air branches typically carry a higher "
        "purity specification than general plant air."
    ),
    applicable_regulations=[
        "ISO 8573-1 — Compressed air purity classes",
        "ISPE Baseline Guide — Process Gases",
        "EU GMP Annex 1 — Compressed gases in direct contact with product",
    ],
    design_considerations=[
        "Purity class per branch (oil-free compressor selection, coalescing/particulate "
        "filtration, dryer type)",
        "Dew point specification appropriate to point-of-use risk",
        "Redundancy/standby compressor philosophy for critical process branches",
        "Distribution material (stainless steel for product-contact branches)",
    ],
    critical_parameters=[
        "Oil content (mg/m3, ISO 8573-1 class)",
        "Particulate count (ISO 8573-1 class)",
        "Pressure dew point (°C)",
        "Delivery pressure and flow at point of use",
    ],
    typical_interfaces=[
        "Process equipment — pneumatic actuation, product-contact air",
        "Building Management System — pressure/dew-point monitoring",
    ],
    common_risks=[
        "Oil carryover into product-contact air from compressor failure",
        "Moisture ingress causing microbial growth in distribution piping",
    ],
))

# ─── Nitrogen ─────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Nitrogen",
    category="Process Utilities",
    aliases=["nitrogen system", "gn2", "nitrogen blanketing", "inert gas"],
    description=(
        "Nitrogen generation (PSA/membrane) or bulk-supply distribution system providing "
        "inert atmosphere for product blanketing, tank padding, and purging of "
        "oxygen-sensitive processes."
    ),
    applicable_regulations=[
        "ISPE Baseline Guide — Process Gases",
        "EU GMP Annex 1 — Gases in direct contact with product",
    ],
    design_considerations=[
        "Generation method (on-site PSA/membrane vs. bulk liquid supply with vaporiser)",
        "Purity specification (% N2, residual O2) per use point",
        "Distribution material and point-of-use filtration (0.2 µm for product-contact)",
        "Backup supply philosophy for continuous-demand processes",
    ],
    critical_parameters=[
        "Nitrogen purity (% v/v)",
        "Residual oxygen content (ppm)",
        "Delivery pressure and flow at point of use",
        "Point-of-use filter integrity",
    ],
    typical_interfaces=[
        "Process/storage vessels — blanketing and padding",
        "Building Management System — supply pressure monitoring",
    ],
    common_risks=[
        "Purity excursion causing inadequate inerting of oxygen-sensitive product",
        "Asphyxiation hazard in confined spaces — ventilation/oxygen monitoring required",
    ],
))

# ─── Vacuum ───────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="Vacuum",
    category="Process Utilities",
    aliases=["central vacuum system", "process vacuum", "plant vacuum"],
    description=(
        "Central vacuum distribution system supporting process operations (drying, "
        "filtration, material transfer) and facility housekeeping (central vacuum "
        "cleaning) in classified and unclassified areas."
    ),
    applicable_regulations=[
        "ISPE Baseline Guide Vol. 2 — Oral Solid Dosage Facilities (utility design)",
        "EU GMP Chapter 3 — Premises and Equipment",
    ],
    design_considerations=[
        "Segregation of process vacuum from housekeeping/central-cleaning vacuum",
        "Exhaust filtration/abatement for potent or hazardous product particulate",
        "Trap and drop-out design to prevent product/liquid carryover into the pump",
        "Point-of-use isolation valves per room",
    ],
    critical_parameters=[
        "Vacuum level (mbar/inHg) at point of use",
        "Exhaust filter efficiency where product-contact",
    ],
    typical_interfaces=[
        "Process equipment — drying, filtration, transfer operations",
        "HVAC exhaust — where vacuum exhaust is filtered to atmosphere",
    ],
    common_risks=[
        "Cross-contamination via shared vacuum main without adequate filtration/isolation",
        "Liquid/product carryover damaging the vacuum pump",
    ],
))

# ─── CIP ──────────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="CIP",
    category="Process Utilities",
    aliases=["clean-in-place", "cip system", "cip skid"],
    description=(
        "Clean-In-Place skid(s) delivering programmed, validated cleaning cycles "
        "(pre-rinse, detergent wash, intermediate rinse, final rinse) to process vessels "
        "and piping without disassembly, typically using Purified Water/WFI as final "
        "rinse medium."
    ),
    applicable_regulations=[
        "EU GMP Annex 15 — Cleaning verification/validation",
        "ISPE Baseline Guide — Process Equipment (cleaning design)",
        "PIC/S GMP Guide — Cleaning validation",
    ],
    design_considerations=[
        "Cycle recipe design (rinse/wash/rinse stages, temperature, concentration, time)",
        "Spray device coverage verification (riboflavin/coverage test) per vessel geometry",
        "Final rinse water quality (Purified Water or WFI per downstream use)",
        "Return-flow/conductivity monitoring for endpoint determination",
        "Recipe/batch record integration for cleaning verification",
    ],
    critical_parameters=[
        "Wash temperature (°C) and time per stage",
        "Detergent concentration (where used)",
        "Final rinse conductivity/TOC endpoint",
        "Spray coverage",
    ],
    typical_interfaces=[
        "Purified Water / WFI system — rinse water supply",
        "Process vessels and piping — cleaned assets",
        "Building Management System / batch record system — cycle data logging",
    ],
    common_risks=[
        "Inadequate spray coverage leaving cross-contamination residue",
        "Rinse water quality failure carried into subsequent batch",
    ],
))

# ─── SIP ──────────────────────────────────────────────────────────────────────

_register(FacilitySystemProfile(
    name="SIP",
    category="Process Utilities",
    aliases=["steam-in-place", "sip system", "sip skid"],
    description=(
        "Steam-In-Place system delivering Clean Steam to process vessels, piping, and "
        "filters for in-situ sterilisation, with validated temperature/time hold and "
        "cooling/drying phases, typically following a CIP cycle."
    ),
    applicable_regulations=[
        "EU GMP Annex 1 — Sterilisation of equipment",
        "ISPE Baseline Guide Vol. 3 — Sterile Manufacturing Facilities",
        "PDA Technical Report — Steam-in-place systems",
    ],
    design_considerations=[
        "Sterilisation hold temperature/time and coldest-point mapping",
        "Air removal/non-condensable gas management before steam admission",
        "Post-sterilisation drying/cooling and sterile air breather integrity",
        "Integration with CIP for the pre-sterilisation clean cycle",
    ],
    critical_parameters=[
        "Sterilisation hold temperature and time (coldest point)",
        "Non-condensable gas content of Clean Steam supply",
        "Post-cycle drying/cooling time",
    ],
    typical_interfaces=[
        "Clean Steam generator — steam supply",
        "CIP system — precedes SIP in the cleaning/sterilisation sequence",
        "Process vessels, piping, filters — sterilised assets",
    ],
    common_risks=[
        "Cold spots from inadequate air removal causing sterilisation failure",
        "Loss of sterile boundary if breather filter integrity is not verified",
    ],
))
