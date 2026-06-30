"""
urs_requirement_library.py — Pre-built pharmaceutical requirement libraries.

Architecture: each equipment/system type contributes a structured requirement
library organized by section. When a user selects a system, PharmaGPT merges
relevant library requirements with AI-generated project-specific requirements.

This keeps the URS module scalable — adding new equipment requires only a new
entry in REQUIREMENT_LIBRARY without touching application logic.

Requirement structure:
    requirement         : "The system shall…" statement
    rationale           : justification / regulatory driver
    priority            : Critical | High | Medium | Low
    gmp_criticality     : GMP-Critical | GMP | Non-GMP
    regulatory_ref      : applicable standard(s)
    verification_method : Functional Test | Document Review | Inspection | etc.
    acceptance_criteria : pass/fail criterion
"""

from __future__ import annotations


# ── Section prefix map (used to generate req_id codes) ───────────────────────

SECTION_PREFIX = {
    "General Requirements": "GEN",
    "Functional Requirements": "FUNC",
    "Operational Requirements": "OPR",
    "Performance Requirements": "PERF",
    "Process Requirements": "PROC",
    "Safety Requirements": "SAFE",
    "GMP Requirements": "GMP",
    "Regulatory Requirements": "REG",
    "Data Integrity Requirements": "DI",
    "Alarm Requirements": "ALM",
    "Security Requirements": "SEC",
    "Access Control": "ACC",
    "Audit Trail": "AT",
    "Electronic Records": "ER",
    "Electronic Signature": "ES",
    "Reporting": "RPT",
    "Communication & Networking": "NET",
    "Backup & Recovery": "BAK",
    "Maintenance & Calibration": "MAINT",
    "Environmental Conditions": "ENV",
    "Cleaning Requirements": "CLN",
    "Documentation": "DOC",
    "Utilities": "UTL",
    "Cybersecurity": "CYBER",
    "Custom Requirements": "CUST",
}


# ── Common requirements shared across all equipment types ─────────────────────

COMMON_REQUIREMENTS: dict[str, list[dict]] = {
    "General Requirements": [
        {
            "requirement": "The equipment/system shall be supplied with full documentation including design drawings, wiring diagrams, parts list, and user manuals.",
            "rationale": "GMP documentation requirements ensure equipment can be maintained and qualified throughout its lifecycle.",
            "priority": "Critical",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15, 21 CFR 211.68",
            "verification_method": "Document Review",
            "acceptance_criteria": "All documentation received, reviewed and filed prior to Installation Qualification.",
        },
        {
            "requirement": "The equipment/system shall comply with all applicable local regulatory requirements and international GMP standards.",
            "rationale": "Ensures the equipment meets regulatory expectations for pharmaceutical manufacturing environments.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15, WHO GMP, 21 CFR Part 211, Schedule M",
            "verification_method": "Document Review",
            "acceptance_criteria": "Regulatory compliance declaration provided by vendor.",
        },
        {
            "requirement": "The equipment/system shall be designed and constructed of materials compatible with pharmaceutical manufacturing, suitable for cleaning and disinfection.",
            "rationale": "Material compatibility prevents product contamination and supports cleanability.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, 21 CFR 211.65",
            "verification_method": "Inspection / Material Certificate Review",
            "acceptance_criteria": "Material certificates (e.g., 316L SS) provided; no material incompatibility with product.",
        },
    ],
    "GMP Requirements": [
        {
            "requirement": "All product-contact surfaces shall be manufactured from pharmaceutical-grade 316L stainless steel or equivalent material with surface finish ≤ 0.8 μm Ra.",
            "rationale": "Smooth surfaces prevent product contamination and facilitate effective cleaning and sterilization.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, ASTM A270",
            "verification_method": "Inspection / Surface Roughness Measurement",
            "acceptance_criteria": "Surface roughness ≤ 0.8 μm Ra on all product-contact surfaces; material certificates available.",
        },
        {
            "requirement": "The equipment/system shall be designed for ease of cleaning with no dead legs, blind spots, or areas where product can accumulate.",
            "rationale": "GMP requirement to prevent cross-contamination between product batches.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, 21 CFR 211.67",
            "verification_method": "Inspection / Cleaning Validation",
            "acceptance_criteria": "No dead legs; all surfaces accessible for cleaning; cleaning validation protocol accepted.",
        },
        {
            "requirement": "The equipment/system shall have a unique equipment identification number permanently affixed in a visible location.",
            "rationale": "Equipment identification is mandatory for GMP traceability and inventory management.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, 21 CFR 211.68",
            "verification_method": "Inspection",
            "acceptance_criteria": "Equipment ID tag visible and legible; matches asset register.",
        },
    ],
    "Documentation": [
        {
            "requirement": "The vendor shall provide a Factory Acceptance Test (FAT) protocol for review and approval prior to execution.",
            "rationale": "FAT ensures equipment meets specifications before shipment, reducing on-site commissioning risk.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ASTM E2500, GAMP 5",
            "verification_method": "Document Review",
            "acceptance_criteria": "FAT protocol received and approved ≥ 2 weeks before scheduled FAT.",
        },
        {
            "requirement": "The vendor shall provide an Installation Qualification (IQ) protocol template aligned with this URS.",
            "rationale": "Vendor-supplied IQ template accelerates site qualification activities.",
            "priority": "Medium",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15, GAMP 5",
            "verification_method": "Document Review",
            "acceptance_criteria": "IQ template received and traceable to URS requirements.",
        },
    ],
    "Maintenance & Calibration": [
        {
            "requirement": "All critical measuring instruments (pressure gauges, temperature sensors, load cells, flow meters) shall be calibrated before first use and at defined periodic intervals.",
            "rationale": "Calibrated instruments ensure accurate process control and GMP compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 3, 21 CFR 211.68, ISO 9001",
            "verification_method": "Calibration Certificate Review",
            "acceptance_criteria": "Calibration certificates traceable to national standards; all within calibration due dates.",
        },
        {
            "requirement": "A preventive maintenance schedule shall be provided by the vendor covering all critical components, with recommended service intervals and spare parts list.",
            "rationale": "Preventive maintenance prevents unexpected downtime and supports equipment qualification status.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, ICH Q10",
            "verification_method": "Document Review",
            "acceptance_criteria": "Preventive maintenance schedule provided with the equipment documentation package.",
        },
    ],
}


# ── Manufacturing Equipment ───────────────────────────────────────────────────

TABLET_COMPRESSION: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The tablet compression machine shall provide upper and lower punch compression force control with accuracy ± 0.1 kN across the full operating range.",
            "rationale": "Precise compression force control ensures tablet hardness consistency and prevents tablet defects.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15, ICH Q6A",
            "verification_method": "Functional Test / OQ",
            "acceptance_criteria": "Compression force control accuracy ± 0.1 kN; verified during OQ across 3 force setpoints.",
        },
        {
            "requirement": "The machine shall provide individual tablet weight control with automatic rejection of tablets outside ± 5% of target weight.",
            "rationale": "Weight control is a critical quality attribute for tablet dosage uniformity per pharmacopoeial requirements.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "BP/USP/IP tablet weight uniformity, ICH Q6A",
            "verification_method": "Functional Test / PQ",
            "acceptance_criteria": "Tablets outside ± 5% weight tolerance automatically rejected; rejection verified with 20 consecutive out-of-spec tablets.",
        },
        {
            "requirement": "The turret speed shall be controllable in the range of at least 10–60 rpm with digital display and closed-loop speed control.",
            "rationale": "Variable speed control allows optimization of production rate vs. tablet quality for different formulations.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "GAMP 5 Category 4",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Speed setpoint achieved within ± 1 rpm; stable operation at all speed settings.",
        },
        {
            "requirement": "The machine shall be capable of processing tooling sets of standard (BB/B/D) and non-standard punch sizes as specified in the purchase order.",
            "rationale": "Tooling compatibility determines tablet shapes and sizes that can be produced.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ASTM B591",
            "verification_method": "Inspection",
            "acceptance_criteria": "Specified tooling sets installed and confirmed compatible during IQ.",
        },
        {
            "requirement": "The machine shall have a recipe management system capable of storing at least 50 product recipes with password-protected access.",
            "rationale": "Recipe management ensures reproducible process parameters and prevents unauthorized changes.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Minimum 50 recipes stored; access requires authorized login; recipe recall verified for 5 products.",
        },
    ],
    "Performance Requirements": [
        {
            "requirement": "The machine shall achieve a production output of at least [SPECIFY] tablets per hour at the validated turret speed.",
            "rationale": "Production output must meet manufacturing demand and batch size requirements.",
            "priority": "High",
            "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Internal Business Requirement",
            "verification_method": "Performance Test / PQ",
            "acceptance_criteria": "Rated output achieved at validated speed; production efficiency ≥ 95%.",
        },
        {
            "requirement": "Tablet hardness uniformity shall be maintained within ± 1.0 kP of the setpoint across the full batch run.",
            "rationale": "Hardness uniformity is a key quality attribute influencing tablet disintegration and dissolution.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "BP/USP/IP tablet hardness specifications",
            "verification_method": "In-process Testing / PQ",
            "acceptance_criteria": "Hardness within ± 1.0 kP of setpoint; verified in 3 consecutive validation batches.",
        },
    ],
    "Alarm Requirements": [
        {
            "requirement": "The machine shall generate alarms for: over-compression force, weight deviation out of tolerance, turret jam, punch missing, feed frame failure, and reject system failure.",
            "rationale": "Alarms protect tablet quality and prevent equipment damage during abnormal conditions.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 11, GAMP 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All specified alarms triggered and recorded when simulated fault conditions applied.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The machine control system shall maintain a 21 CFR Part 11 compliant audit trail recording all parameter changes, alarm events, recipe changes, and user logins with timestamp, user ID, and reason for change.",
            "rationale": "Electronic audit trail is mandatory for computerized systems in GMP pharmaceutical manufacturing.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, ALCOA+",
            "verification_method": "Functional Test / CSV",
            "acceptance_criteria": "Audit trail cannot be deleted or modified; all specified events captured with timestamp accuracy ± 1 minute; accessible to QA.",
        },
    ],
}

CAPSULE_FILLING: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The capsule filling machine shall handle capsule sizes 00, 0, 1, 2, 3, 4 and 5 with changeover tooling as specified.",
            "rationale": "Capsule size flexibility supports multiple product types on a single platform.",
            "priority": "Critical",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Inspection / Functional Test",
            "acceptance_criteria": "All specified capsule sizes successfully filled with ≤ 0.1% misfilled capsules.",
        },
        {
            "requirement": "The fill weight control system shall achieve a fill weight accuracy of ± 3% RSD for each dosing station.",
            "rationale": "Fill weight accuracy is critical for dose uniformity and bioavailability of the final product.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q6A, BP/USP content uniformity requirements",
            "verification_method": "Functional Test / PQ",
            "acceptance_criteria": "RSD ≤ 3% across all dosing stations; verified with 10 consecutive samples per station.",
        },
        {
            "requirement": "The machine shall include a 100% in-process weight checking system with automatic rejection of capsules outside the weight specification.",
            "rationale": "100% weight checking ensures all capsules shipped meet dosage specifications.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q6A",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All out-of-specification capsules rejected; reject system verified with 10 seeded OOS samples.",
        },
        {
            "requirement": "The machine shall have a defect detection system to identify and reject empty capsules, damaged capsules, and open capsules.",
            "rationale": "Defect detection prevents defective product from reaching patients.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All seeded defective capsule types detected and rejected with ≥ 99.9% efficiency.",
        },
    ],
    "Performance Requirements": [
        {
            "requirement": "The machine shall achieve production output of at least [SPECIFY] capsules per hour at the validated operating speed.",
            "rationale": "Output must meet manufacturing schedule and batch size requirements.",
            "priority": "High",
            "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Internal Business Requirement",
            "verification_method": "Performance Test",
            "acceptance_criteria": "Rated output achieved; OEE ≥ 80%.",
        },
    ],
    "Alarm Requirements": [
        {
            "requirement": "Alarms shall be provided for: capsule jam, empty capsule supply, powder hopper low, reject container full, checkweigher failure, and temperature deviations.",
            "rationale": "Alarms ensure operator awareness of conditions affecting product quality and process continuity.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All alarms triggered and recorded under simulated fault conditions.",
        },
    ],
}

COATING_MACHINE: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The coating machine pan speed shall be controllable between 2–20 rpm with ± 0.5 rpm accuracy.",
            "rationale": "Pan speed determines tablet mixing and film uniformity during coating.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Speed setpoint achieved within ± 0.5 rpm; stable at all operating speeds.",
        },
        {
            "requirement": "Inlet air temperature control shall be accurate to ± 2°C across the operating range of 30–80°C.",
            "rationale": "Inlet temperature controls coating film formation and drying rate; critical to coating quality.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Temperature Mapping / OQ",
            "acceptance_criteria": "Inlet temperature within ± 2°C of setpoint during steady-state; verified at 3 temperature setpoints.",
        },
        {
            "requirement": "The spray system shall provide a minimum of [N] spray guns with independent atomization air pressure and liquid flow rate control per gun.",
            "rationale": "Independent spray gun control allows optimization of coating uniformity across the tablet bed.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "GAMP 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Each spray gun independently controllable; spray pattern uniform per photographic assessment.",
        },
        {
            "requirement": "Exhaust air humidity shall be continuously monitored and displayed as an indicator of tablet moisture content.",
            "rationale": "Exhaust humidity correlates with tablet moisture and guides coating end-point determination.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q6A",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Exhaust humidity sensor accuracy ± 2% RH; continuous display on HMI.",
        },
    ],
}

GRANULATION: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The high shear granulator impeller speed shall be adjustable from 50–500 rpm with ± 5 rpm accuracy in both manual and recipe-controlled modes.",
            "rationale": "Impeller speed is a critical process parameter determining granule size and density.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15, ICH Q8",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Speed setpoint achieved within ± 5 rpm; stable operation confirmed over 30-minute run.",
        },
        {
            "requirement": "The chopper speed shall be independently controllable from 500–3000 rpm.",
            "rationale": "Chopper speed breaks up lumps and influences granule size distribution.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Chopper speed setpoint achievable within ± 50 rpm.",
        },
        {
            "requirement": "Bowl temperature shall be monitored with ± 1°C accuracy; process endpoint shall be determinable by power consumption monitoring.",
            "rationale": "Temperature and power monitoring provide in-process controls for granulation endpoint determination.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q8",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Temperature accuracy ± 1°C; power consumption trend displayed in real time.",
        },
    ],
}

BLENDING: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The blender shall achieve blend uniformity of RSD ≤ 5% for the active pharmaceutical ingredient across the blending volume.",
            "rationale": "Blend uniformity is a critical quality attribute ensuring consistent drug content in the final product.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR 211.110, ICH Q6A, USP <905>",
            "verification_method": "Blend Uniformity Study / PQ",
            "acceptance_criteria": "RSD ≤ 5% for API across minimum 10 sampling locations; verified in 3 validation batches.",
        },
        {
            "requirement": "Blender rotation speed shall be controllable between 2–25 rpm with ± 0.5 rpm accuracy.",
            "rationale": "Speed control ensures reproducible blending process parameters across batches.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Speed setpoint achieved within ± 0.5 rpm.",
        },
        {
            "requirement": "The blender shall have an interlocking system preventing operation with open hatches or improperly locked IBC.",
            "rationale": "Safety interlock prevents exposure to personnel and product contamination.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU Machinery Directive 2006/42/EC",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Blender does not start with open hatch; emergency stop verified.",
        },
    ],
}

FLUID_BED_PROCESSOR: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "Inlet air temperature shall be controllable between 30–90°C with ± 2°C accuracy.",
            "rationale": "Inlet temperature controls drying rate and product temperature; critical to moisture content.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Temperature Mapping",
            "acceptance_criteria": "Temperature within ± 2°C of setpoint during steady-state at 3 setpoints.",
        },
        {
            "requirement": "Inlet airflow shall be controllable and monitored with accuracy ± 5% of setpoint.",
            "rationale": "Airflow rate determines fluidization quality and drying efficiency.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 15",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Airflow within ± 5% of setpoint.",
        },
        {
            "requirement": "Product temperature shall be continuously monitored during drying with high temperature alarm at user-defined setpoint.",
            "rationale": "Product temperature control prevents overheating of heat-sensitive APIs.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q8",
            "verification_method": "Functional Test",
            "acceptance_criteria": "High temperature alarm activates within 30 seconds of exceeding setpoint.",
        },
        {
            "requirement": "All HEPA filters shall have differential pressure monitoring with alarms for filter blockage and bypass failure.",
            "rationale": "HEPA filter integrity ensures sterile air supply and prevents cross-contamination.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1",
            "verification_method": "Functional Test / Filter Integrity Test",
            "acceptance_criteria": "ΔP alarms trigger at defined limits; HEPA filter integrity DOP test passed.",
        },
    ],
}


# ── Packaging Equipment ───────────────────────────────────────────────────────

BLISTER_MACHINE: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The blister machine shall produce blister packs using PVC/Aluminium or ALU/ALU forming material as specified in the product dossier.",
            "rationale": "Correct packaging material ensures product stability and regulatory compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q1A, EU GMP Chapter 5",
            "verification_method": "Inspection / Functional Test",
            "acceptance_criteria": "Correct material verified; seal integrity tested per EN ISO 11607.",
        },
        {
            "requirement": "The machine shall include a 100% vision inspection system to detect missing tablets, broken tablets, double tablets, and sealing defects.",
            "rationale": "Vision inspection prevents defective blisters from reaching patients.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, Annex 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All seeded defect types detected with ≥ 99.9% efficiency at rated speed.",
        },
        {
            "requirement": "Online printing of batch number, expiry date, and manufacturing date shall be integrated with automatic verification camera.",
            "rationale": "Printing verification ensures traceability and regulatory compliance for serialization.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU Falsified Medicines Directive 2011/62/EU, 21 CFR 211.130",
            "verification_method": "Functional Test",
            "acceptance_criteria": "100% print verification; illegible or missing print triggers rejection.",
        },
        {
            "requirement": "Sealing temperature shall be controllable within ± 2°C and monitored with alarm if deviation exceeds defined limits.",
            "rationale": "Sealing temperature directly affects blister seal integrity and product protection.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EN ISO 11607",
            "verification_method": "Functional Test / Seal Integrity Test",
            "acceptance_criteria": "Temperature within ± 2°C of setpoint; seal integrity tests passed.",
        },
    ],
    "Performance Requirements": [
        {
            "requirement": "Machine speed shall be at least [SPECIFY] blisters per minute at rated efficiency.",
            "rationale": "Output must meet production schedule.",
            "priority": "High",
            "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Internal Business Requirement",
            "verification_method": "Performance Test",
            "acceptance_criteria": "Rated speed achieved; OEE ≥ 85%.",
        },
    ],
}

METAL_DETECTOR: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The metal detector shall detect ferrous, non-ferrous, and stainless steel contaminants at minimum sensitivity as specified: Ferrous ≥ 1.5 mm sphere, Non-ferrous ≥ 2.0 mm sphere, Stainless Steel ≥ 2.5 mm sphere.",
            "rationale": "Metal detection protects patients from physical contaminants and demonstrates GMP compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, 21 CFR 211.113",
            "verification_method": "Challenge Testing",
            "acceptance_criteria": "100% detection of specified test spheres in stationary and running product conditions.",
        },
        {
            "requirement": "The metal detector shall automatically reject any detected product and maintain a count of rejected units in the audit trail.",
            "rationale": "Automatic rejection prevents contaminated product from proceeding and provides data integrity.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Reject actuated within 200 ms of detection; rejected count logged with timestamp.",
        },
        {
            "requirement": "The system shall have automatic frequency adjustment (AFM) to compensate for product effect.",
            "rationale": "AFM maintains sensitivity when detecting metal in products with high moisture or salt content.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "Industry Best Practice",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Sensitivity maintained within specification in product effect conditions.",
        },
        {
            "requirement": "Calibration shall be required at the start of each production run with mandatory test-pass confirmation before production proceeds.",
            "rationale": "Regular calibration verification ensures detector is functioning correctly throughout production.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR 211.68, EU GMP Chapter 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Machine will not allow production to start until calibration confirmed passed.",
        },
    ],
}

LABELING_MACHINE: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The labeling machine shall apply labels to containers with positional accuracy of ± 2 mm and without wrinkles, bubbles, or misalignment.",
            "rationale": "Accurate label application ensures product traceability and professional presentation.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR 211.130",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Label position within ± 2 mm; no wrinkles or bubbles detected in 100-unit test run.",
        },
        {
            "requirement": "A 100% vision inspection camera shall verify label presence, position, and barcode/2D-code readability.",
            "rationale": "Vision inspection prevents unlabeled or mislabeled containers from reaching patients.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, EU FMD 2011/62/EU",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Missing, mispositioned, or unreadable labels cause rejection; ≥ 99.9% detection efficiency.",
        },
        {
            "requirement": "The machine shall integrate with the serialization system to receive and apply 2D DataMatrix codes with GS1 compliance.",
            "rationale": "Serialization compliance is mandatory under EU FMD and DSCSA for pharmaceutical products.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU FMD Regulation 2016/161, DSCSA",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Serialization data received; 2D code verified readable at GS1 specification.",
        },
    ],
}

VISION_INSPECTION: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The vision inspection system shall detect and reject containers with cosmetic defects including cracks, chips, discoloration, foreign particles, and fill level deviations.",
            "rationale": "Cosmetic defects may indicate contamination or process anomalies affecting product quality.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, USP <1790>",
            "verification_method": "Challenge Testing",
            "acceptance_criteria": "All seeded defect types detected and rejected with ≥ 99.9% efficiency.",
        },
        {
            "requirement": "Inspection speed shall match the production line speed without creating a bottleneck.",
            "rationale": "Inspection must not limit production throughput.",
            "priority": "High",
            "gmp_criticality": "Non-GMP",
            "regulatory_ref": "Internal Business Requirement",
            "verification_method": "Performance Test",
            "acceptance_criteria": "Inspection throughput ≥ line speed; reject rate < 0.1% false positives.",
        },
        {
            "requirement": "All rejection events shall be logged with timestamp, container ID (if serialized), defect type, and image capture.",
            "rationale": "Rejection data supports batch record review and trend analysis for process improvement.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR Part 11, ALCOA+",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All rejection events recorded; images accessible for 5 years; audit trail intact.",
        },
    ],
}


# ── Laboratory Equipment ──────────────────────────────────────────────────────

HPLC: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The HPLC system shall meet the requirements of USP <621> and EP 2.2.29 for chromatography system suitability.",
            "rationale": "System suitability ensures the HPLC is operating correctly for each analytical method.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <621>, EP 2.2.29, ICH Q2(R1)",
            "verification_method": "System Suitability Testing",
            "acceptance_criteria": "System suitability criteria met for all validated methods: RSD ≤ 2%, tailing factor ≤ 2.0, plates ≥ 2000.",
        },
        {
            "requirement": "Flow rate accuracy shall be ± 1% across the operating range of 0.1–5.0 mL/min.",
            "rationale": "Flow rate accuracy directly affects retention time reproducibility and quantitative results.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <621>",
            "verification_method": "Performance Qualification",
            "acceptance_criteria": "Flow rate accuracy ± 1%; verified gravimetrically at 0.5, 1.0, and 2.0 mL/min.",
        },
        {
            "requirement": "Column oven temperature shall be controllable from ambient to 60°C with accuracy ± 0.5°C and stability ± 0.2°C during a run.",
            "rationale": "Temperature control ensures reproducible chromatographic conditions across analytical runs.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "USP <621>",
            "verification_method": "Performance Qualification",
            "acceptance_criteria": "Temperature accuracy ± 0.5°C; stability ± 0.2°C over 60-minute run.",
        },
        {
            "requirement": "The detector shall have a linear dynamic range spanning at least 3 orders of magnitude for UV absorbance measurements.",
            "rationale": "Linear range ensures accurate quantification across the full concentration range of analytical methods.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q2(R1)",
            "verification_method": "Performance Qualification",
            "acceptance_criteria": "Linearity R² ≥ 0.999 over 3 orders of magnitude.",
        },
    ],
    "Data Integrity Requirements": [
        {
            "requirement": "The HPLC data system shall comply with 21 CFR Part 11 and EU GMP Annex 11 for electronic records and signatures.",
            "rationale": "Data integrity is fundamental to GMP compliance; results must be attributable, legible, and original.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, ALCOA+",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "Audit trail enabled; data cannot be deleted without electronic signature; CSV validation completed.",
        },
        {
            "requirement": "Raw chromatographic data shall be stored in the original instrument data format and shall not be overwritable.",
            "rationale": "ALCOA+ requires that original data is preserved unaltered.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ALCOA+, FDA Data Integrity Guidance 2018",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Raw data stored in locked format; overwrite attempt generates error and audit entry.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The chromatography data system shall capture an audit trail for all sequence modifications, result processing changes, method changes, and user logins.",
            "rationale": "Audit trail is a GMP requirement for computerized systems handling electronic records.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11.10, EU GMP Annex 11 §9",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "All specified events captured; audit trail cannot be disabled; QA has read-only access.",
        },
    ],
}

DISSOLUTION: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The dissolution apparatus shall include USP Apparatus 1 (basket) and Apparatus 2 (paddle) with interchangeable vessels and shaft assemblies.",
            "rationale": "USP apparatus types are mandatory for compliance with pharmacopoeial dissolution methods.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <711>, EP 2.9.3",
            "verification_method": "Inspection",
            "acceptance_criteria": "Both apparatus types installed and verified per USP/EP specifications.",
        },
        {
            "requirement": "Bath temperature shall be maintained at 37.0 ± 0.5°C throughout the dissolution test.",
            "rationale": "Temperature control is critical; deviation from 37°C significantly affects dissolution results.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <711>",
            "verification_method": "Temperature Mapping / PQ",
            "acceptance_criteria": "Temperature 37.0 ± 0.5°C at all vessel positions; verified with calibrated thermometers.",
        },
        {
            "requirement": "Paddle/basket speed shall be controllable from 25–200 rpm with accuracy ± 4% and wobble ≤ 1.0 mm.",
            "rationale": "Speed accuracy and wobble limits are pharmacopoeial requirements for dissolution apparatus.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <711>",
            "verification_method": "Performance Qualification",
            "acceptance_criteria": "Speed accuracy ± 4%; wobble ≤ 1.0 mm; verified per USP <711>.",
        },
    ],
}

STABILITY_CHAMBER: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The stability chamber shall maintain temperature within the range of 5°C to 40°C with accuracy ± 2°C and uniformity ± 2°C at ICH Q1A study conditions.",
            "rationale": "Temperature control is essential for valid stability data supporting drug registration.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q1A(R2), WHO Technical Report 953",
            "verification_method": "Temperature Mapping / OQ",
            "acceptance_criteria": "Temperature accuracy ± 2°C; uniformity ± 2°C at all ICH study points; mapping per WHO guideline.",
        },
        {
            "requirement": "Relative humidity shall be maintained within 5–95% RH with accuracy ± 5% RH at ICH study conditions.",
            "rationale": "Humidity control is required for ICH intermediate and accelerated stability conditions.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q1A(R2)",
            "verification_method": "RH Mapping / OQ",
            "acceptance_criteria": "RH accuracy ± 5% RH; verified at 25°C/60%RH and 40°C/75%RH conditions.",
        },
        {
            "requirement": "Continuous temperature and humidity monitoring with 21 CFR Part 11 compliant data logging and alarm notification system.",
            "rationale": "Continuous monitoring detects excursions that could invalidate stability samples.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ICH Q1A(R2), 21 CFR Part 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Monitoring continuous 24/7; alarm notification within 5 minutes of excursion; data locked.",
        },
        {
            "requirement": "The chamber shall have a backup power supply or alarm to protect stability samples during power failure.",
            "rationale": "Power failure could compromise stability study integrity and require study restart.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q1A(R2)",
            "verification_method": "Functional Test",
            "acceptance_criteria": "UPS maintains conditions for ≥ 30 minutes; power failure alarm triggered.",
        },
    ],
}

AUTOCLAVE: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The autoclave shall achieve and maintain sterilization temperature of 121°C ± 1°C or 134°C ± 1°C as per the defined sterilization cycle.",
            "rationale": "Sterilization temperature is critical to achieving the required sterility assurance level (SAL 10⁻⁶).",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, EN ISO 17665-1, PDA TR 01",
            "verification_method": "Temperature Mapping / OQ",
            "acceptance_criteria": "Temperature 121°C ± 1°C or 134°C ± 1°C; F₀ ≥ 15 achieved at all load positions.",
        },
        {
            "requirement": "The autoclave shall include a biological indicator (BI) port and chemical indicator integration for cycle validation.",
            "rationale": "Biological and chemical indicators provide direct evidence of sterilization efficacy.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EN ISO 11138, EN ISO 11140, EU GMP Annex 1",
            "verification_method": "Sterilization Validation",
            "acceptance_criteria": "BI results negative post-cycle; CI correct color change achieved.",
        },
        {
            "requirement": "The control system shall prevent door opening during pressurized operation and shall log all cycle parameters electronically.",
            "rationale": "Safety interlock prevents burn/pressure injury; electronic records ensure batch traceability.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU Pressure Equipment Directive, 21 CFR Part 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Door cannot open above 0.05 bar; cycle data logged electronically with audit trail.",
        },
    ],
}


# ── Utilities ─────────────────────────────────────────────────────────────────

PURIFIED_WATER: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The purified water system shall produce water meeting EP/USP/IP Purified Water specifications: conductivity ≤ 4.3 μS/cm at 25°C, TOC ≤ 500 ppb, and microbial action limit ≤ 100 CFU/mL.",
            "rationale": "Water quality is critical to product quality; all pharmacopoeial specifications must be met.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EP 0008, USP <1231>, IP 2018, WHO GMP",
            "verification_method": "Analytical Testing / PQ",
            "acceptance_criteria": "All PW specifications met in 3-phase validation (installation, operational, and performance) per USP <1231>.",
        },
        {
            "requirement": "The system shall include multi-media filtration, softening, activated carbon treatment, reverse osmosis (minimum two-pass), and electrodeionization (EDI) or equivalent purification technology.",
            "rationale": "Multi-barrier treatment ensures consistent water quality across varying feed water conditions.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <1231>, WHO TRS 970",
            "verification_method": "Inspection / IQ",
            "acceptance_criteria": "All treatment stages installed, operational, and verified during IQ.",
        },
        {
            "requirement": "The distribution system shall be a continuous loop with velocities ≥ 1 m/s to prevent biofilm formation.",
            "rationale": "Turbulent flow prevents stagnation and biofilm development in distribution pipework.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "WHO TRS 970, ISPE Baseline Guide Vol 4",
            "verification_method": "Flow Velocity Measurement",
            "acceptance_criteria": "Velocity ≥ 1 m/s at all loop points; verified by flow measurement.",
        },
        {
            "requirement": "The system shall have online monitoring for conductivity and TOC at the system outlet with alarms for specification exceedances.",
            "rationale": "Online monitoring provides real-time quality assurance and early warning of system deviations.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "USP <645>, <643>",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Online conductivity and TOC monitors calibrated and alarming correctly.",
        },
        {
            "requirement": "The system shall be designed for sanitization by hot water (≥ 80°C) or chemical sanitization with documented sanitization SOP.",
            "rationale": "Regular sanitization maintains microbial quality within specification.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "WHO TRS 970",
            "verification_method": "Functional Test / Microbial Testing",
            "acceptance_criteria": "Sanitization achieves ≥ 4-log reduction; microbial counts within limits post-sanitization.",
        },
    ],
}

WFI: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The WFI system shall produce water meeting EP/USP/IP Water for Injection specifications: conductivity ≤ 1.3 μS/cm at 25°C, TOC ≤ 500 ppb, bacterial endotoxins ≤ 0.25 EU/mL, and microbial action limit ≤ 10 CFU/100 mL.",
            "rationale": "WFI is used in parenteral product manufacturing; exceedances directly impact patient safety.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EP 0169, USP <1231>, WHO TRS 970",
            "verification_method": "Analytical Testing / PQ",
            "acceptance_criteria": "All WFI specifications met consistently during 3-phase validation per USP <1231>.",
        },
        {
            "requirement": "The WFI storage and distribution system shall be maintained at ≥ 70°C continuously (hot storage) or 4°C ± 2°C (cold storage with 24-hour use policy).",
            "rationale": "Elevated temperature prevents microbial proliferation in WFI loop.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "WHO TRS 970, ISPE Baseline Guide Vol 4",
            "verification_method": "Temperature Monitoring",
            "acceptance_criteria": "Temperature maintained ≥ 70°C at all loop points; verified by continuous monitoring.",
        },
    ],
}

COMPRESSED_AIR: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "Product-contact compressed air shall meet ISO 8573-1 Class 1 for particles (0.1 μm), Class 1 for water (−70°C pressure dew point), and Class 1 for oil (0.01 mg/m³).",
            "rationale": "Compressed air quality is critical for products where air contacts the product directly.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ISO 8573-1, EU GMP Annex 1, WHO GMP",
            "verification_method": "Air Quality Testing",
            "acceptance_criteria": "All parameters within ISO 8573-1 Class 1 limits; microbial testing ≤ 1 CFU/m³.",
        },
        {
            "requirement": "Compressed air supply pressure shall be maintained at [SPECIFY] bar ± 0.5 bar with pressure monitoring and alarm.",
            "rationale": "Stable pressure ensures consistent pneumatic operation of downstream equipment.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "Internal Engineering Requirement",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Pressure within ± 0.5 bar of setpoint; alarm activates on deviation.",
        },
    ],
}


# ── Computerized Systems ──────────────────────────────────────────────────────

SCADA: dict[str, list[dict]] = {
    "General Requirements": [
        {
            "requirement": "The SCADA system shall be classified as GAMP 5 Category 4 (Configured Software) or Category 5 (Custom Software) and shall be fully validated per the approved Validation Master Plan.",
            "rationale": "GAMP 5 classification determines the required depth of validation activities.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "GAMP 5 Second Edition, EU GMP Annex 11",
            "verification_method": "CSV / Document Review",
            "acceptance_criteria": "GAMP classification documented; validation lifecycle completed per VMP.",
        },
    ],
    "Functional Requirements": [
        {
            "requirement": "The SCADA system shall acquire data from all process instruments at a minimum scan rate of 1 second for critical parameters.",
            "rationale": "Adequate scan rate ensures no significant process deviations are missed.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 11, GAMP 5",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All critical parameters sampled at ≤ 1 second intervals; verified by time-stamped historian data.",
        },
        {
            "requirement": "The SCADA system shall provide real-time process visualization with color-coded status indicators, trend displays, and mimics for all monitored systems.",
            "rationale": "Intuitive visualization allows operators to detect process deviations rapidly.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "GAMP 5, Good Practice Guide: Computerized Systems",
            "verification_method": "Functional Test / UAT",
            "acceptance_criteria": "All process areas visible; real-time trends update within 2 seconds; colour codes match engineering standards.",
        },
        {
            "requirement": "The SCADA historian shall store process data with time resolution of 1 second for critical parameters and 10 seconds for non-critical parameters, with a minimum retention period of 5 years.",
            "rationale": "Process data retention supports batch record reconstruction and regulatory inspections.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11 §17",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Data stored at specified resolution; 5-year retention verified; data retrieval tested.",
        },
        {
            "requirement": "The SCADA system shall support recipe management with electronic approval workflow for recipe creation, modification, and deletion.",
            "rationale": "Recipe management ensures process reproducibility and prevents unauthorized process changes.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Recipe changes require QA approval; all recipe versions retained in audit trail.",
        },
    ],
    "Alarm Requirements": [
        {
            "requirement": "The alarm management system shall be designed per ISA-18.2 and EEMUA 191 standards with alarm rationalization documented for all process alarms.",
            "rationale": "Alarm rationalization prevents alarm floods and ensures operators can respond effectively.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ISA-18.2, EEMUA 191, EU GMP Annex 11",
            "verification_method": "Alarm Rationalization Review",
            "acceptance_criteria": "Alarm rationalization document approved; alarm rate < 10 alarms/hour during normal operations.",
        },
        {
            "requirement": "All alarm events shall be logged with timestamp, tag ID, description, operator acknowledgement time, and corrective action taken.",
            "rationale": "Alarm logging provides traceability for GMP investigations and trend analysis.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, ALCOA+",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All specified alarm data captured; logs cannot be modified; accessible for 5 years.",
        },
    ],
    "Security Requirements": [
        {
            "requirement": "The SCADA system shall implement role-based access control (RBAC) with minimum 4 user roles: Operator, Supervisor, Engineer, Administrator.",
            "rationale": "RBAC limits system access to authorized functions, preventing unauthorized changes.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11.10(d), EU GMP Annex 11 §12",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Each role restricted to defined functions; unauthorized actions rejected; access rights documented.",
        },
        {
            "requirement": "User passwords shall comply with a defined complexity policy: minimum 8 characters, alphanumeric with special characters, expiry every 90 days.",
            "rationale": "Password policy prevents unauthorized access through weak credentials.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR Part 11.10(d), NIST SP 800-63",
            "verification_method": "Functional Test",
            "acceptance_criteria": "System enforces password policy; weak passwords rejected; expiry enforced.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The SCADA system shall maintain a comprehensive, 21 CFR Part 11 compliant audit trail for all: parameter changes, setpoint modifications, alarm acknowledgements, operator logons/logoffs, recipe changes, and system configuration changes.",
            "rationale": "Complete audit trail is mandatory for GMP computerized systems and regulatory inspection.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11.10(e), EU GMP Annex 11 §9, ALCOA+",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "All specified events captured; audit trail cannot be disabled, modified, or deleted; timestamp accuracy ± 1 second; QA has read-only access.",
        },
    ],
    "Electronic Records": [
        {
            "requirement": "Electronic records generated by the SCADA system shall meet ALCOA+ principles: Attributable, Legible, Contemporaneous, Original, Accurate, Complete, Consistent, Enduring, Available.",
            "rationale": "ALCOA+ is the foundational data integrity framework for GMP electronic records.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "FDA Data Integrity Guidance 2018, EU GMP Annex 11, WHO TRS 996",
            "verification_method": "CSV / Data Integrity Assessment",
            "acceptance_criteria": "All ALCOA+ attributes demonstrated through CSV testing; data integrity assessment completed.",
        },
    ],
    "Electronic Signature": [
        {
            "requirement": "Electronic signatures used in the SCADA system shall comply with 21 CFR Part 11 Subpart C, binding the signature to the signatory's identity and the document.",
            "rationale": "21 CFR Part 11 compliant e-signatures are legally equivalent to handwritten signatures.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11.50, EU GMP Annex 11 §14",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "E-signature requires unique username + password; signature linked to record; cannot be repudiated.",
        },
    ],
    "Backup & Recovery": [
        {
            "requirement": "Automated daily backup of all SCADA databases, configuration files, and historical data to a secondary storage location, with monthly restoration testing.",
            "rationale": "Data backup ensures business continuity and GMP data integrity in case of system failure.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 11 §17, 21 CFR Part 11",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Automated daily backup confirmed; restoration test completes within defined RTO; data integrity verified.",
        },
        {
            "requirement": "The system shall have a documented disaster recovery plan with Recovery Time Objective (RTO) ≤ 4 hours and Recovery Point Objective (RPO) ≤ 1 hour for GMP critical data.",
            "rationale": "Defined RTO/RPO ensures critical GMP systems are restored to operation with minimal data loss.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 11 §17, ICH Q10",
            "verification_method": "DR Test",
            "acceptance_criteria": "DR plan documented and tested; RTO and RPO targets met.",
        },
    ],
    "Cybersecurity": [
        {
            "requirement": "The SCADA network shall be segmented from corporate IT networks using a DMZ architecture with firewall protection.",
            "rationale": "Network segmentation prevents cyber threats from propagating to critical production systems.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "NIST CSF, IEC 62443, FDA Cybersecurity Guidance",
            "verification_method": "Network Architecture Review / Penetration Test",
            "acceptance_criteria": "DMZ implemented; firewall rules reviewed and approved; penetration test passed.",
        },
        {
            "requirement": "All SCADA workstations shall have application whitelisting and endpoint protection software with automatic updates managed through patch management.",
            "rationale": "Endpoint protection prevents malware infection that could disrupt production or compromise data.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "IEC 62443, NIST SP 800-82",
            "verification_method": "IT Security Review",
            "acceptance_criteria": "Whitelisting active; AV/EDR deployed; patch management policy in place.",
        },
    ],
}

MES: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The MES shall support electronic batch record creation, execution, and review with 21 CFR Part 11 compliant electronic signatures for all critical steps.",
            "rationale": "Electronic batch records eliminate handwriting errors and enable real-time batch tracking.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, ICH Q7",
            "verification_method": "CSV / UAT",
            "acceptance_criteria": "eBR lifecycle (create, execute, review, approve) fully functional; e-signatures compliant.",
        },
        {
            "requirement": "The MES shall enforce manufacturing instructions step-by-step, preventing advancement to the next step until all current step data is entered and electronically signed.",
            "rationale": "Step-locking prevents skipping of critical process steps and ensures procedural compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR 211.188, EU GMP Chapter 5",
            "verification_method": "Functional Test / UAT",
            "acceptance_criteria": "System blocks step advancement; attempted bypass rejected and logged in audit trail.",
        },
        {
            "requirement": "The MES shall integrate with the ERP system for material consumption, batch issuance, and inventory management with bidirectional data exchange.",
            "rationale": "ERP integration ensures accurate inventory management and eliminates manual data entry errors.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q10",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Bidirectional data exchange verified; reconciliation reports accurate.",
        },
        {
            "requirement": "The MES shall provide real-time OEE (Overall Equipment Effectiveness) tracking for all production equipment.",
            "rationale": "OEE monitoring supports continuous improvement and production optimization.",
            "priority": "Medium",
            "gmp_criticality": "Non-GMP",
            "regulatory_ref": "ICH Q10",
            "verification_method": "Functional Test",
            "acceptance_criteria": "OEE calculated correctly; availability, performance, and quality components displayed.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The MES shall maintain a comprehensive audit trail for all batch record changes, data entries, corrections, and electronic signature events.",
            "rationale": "Complete audit trail supports GMP compliance and batch release decisions.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "All audit trail requirements of 21 CFR Part 11.10(e) met; no audit trail gaps.",
        },
    ],
}

LIMS: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The LIMS shall manage the complete sample lifecycle from sample login through testing, result entry, review, approval, and disposal.",
            "rationale": "Sample lifecycle management ensures complete traceability and prevents sample mix-ups.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 211.194, EU GMP Chapter 6",
            "verification_method": "CSV / UAT",
            "acceptance_criteria": "Full sample lifecycle demonstrated; no orphaned samples; chain of custody intact.",
        },
        {
            "requirement": "The LIMS shall interface with laboratory instruments (HPLC, GC, UV, balances) for direct data acquisition, eliminating manual transcription.",
            "rationale": "Direct instrument interface prevents transcription errors and supports ALCOA+ data integrity.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, ALCOA+, EU GMP Annex 11",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Data transferred directly from instrument to LIMS without manual entry; transfer verified for all interfaces.",
        },
        {
            "requirement": "The LIMS shall enforce test specifications and automatically flag out-of-specification (OOS) results for investigation workflow.",
            "rationale": "Automatic OOS flagging ensures investigations are initiated promptly per 21 CFR 211.192.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR 211.192, EU GMP Chapter 6",
            "verification_method": "Functional Test",
            "acceptance_criteria": "OOS results flagged automatically; OOS workflow initiated; results cannot be finalized without investigation.",
        },
        {
            "requirement": "The LIMS shall support Certificate of Analysis (CoA) generation with electronic signature and PDF/DOCX export.",
            "rationale": "CoA generation supports product release and customer documentation requirements.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 6, ICH Q7",
            "verification_method": "Functional Test",
            "acceptance_criteria": "CoA generated correctly with all specified fields; electronic signature applied.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The LIMS audit trail shall capture all result entries, modifications, deletions, specification changes, and user actions with timestamp and user ID.",
            "rationale": "Complete audit trail is fundamental to data integrity in laboratory systems.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, OECD GLP",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "All specified events captured; audit trail read-only; report exportable for inspection.",
        },
    ],
}

BARCODE_SYSTEM: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The barcode system shall support 1D (Code 128, EAN-13, ITF-14) and 2D (GS1 DataMatrix, QR Code) barcode standards as required for pharmaceutical serialization.",
            "rationale": "GS1 standards are mandatory for pharmaceutical serialization and supply chain compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "GS1 General Specification, EU FMD, DSCSA",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All specified barcode types verified readable with GS1-certified scanner.",
        },
        {
            "requirement": "Barcode print quality shall meet ISO/IEC 15415 Grade B or better for 2D codes and ISO/IEC 15416 Grade B or better for 1D codes.",
            "rationale": "Print quality verification ensures barcode readability throughout the supply chain.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "ISO/IEC 15415, ISO/IEC 15416, GS1 General Specification",
            "verification_method": "Print Quality Verification",
            "acceptance_criteria": "Barcode grade ≥ B on all printed labels; verified with ISO-compliant verifier.",
        },
        {
            "requirement": "The barcode system shall integrate with ERP for real-time material tracking and inventory update, with bidirectional data exchange.",
            "rationale": "ERP integration ensures accurate inventory and eliminates manual data entry errors.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "ICH Q10",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Bidirectional data exchange verified; inventory updated within 30 seconds of scan.",
        },
        {
            "requirement": "Misread or unreadable barcodes shall trigger automatic rejection and an alarm with logging of the event.",
            "rationale": "Automatic rejection of unreadable codes prevents unverified product from proceeding.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU FMD, GS1",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Unreadable codes cause rejection; event logged with timestamp; 100% detection efficiency.",
        },
        {
            "requirement": "The system shall be compatible with the site serialization platform and capable of receiving unique identifiers from the serialization system.",
            "rationale": "Serialization integration is mandatory for EU FMD and DSCSA compliance.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU FMD Regulation 2016/161, DSCSA",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Serialization data received and applied correctly; end-to-end traceability verified.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "All barcode scan events, print events, rejections, and system configuration changes shall be logged with timestamp and operator ID.",
            "rationale": "Complete event logging supports batch traceability and regulatory inspection readiness.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "21 CFR Part 11, ALCOA+",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All events logged; log read-only; retained for minimum 5 years.",
        },
    ],
}

BMS: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The BMS shall monitor and control HVAC systems including AHUs, FCUs, dampers, and VAV boxes to maintain room classification parameters.",
            "rationale": "HVAC control is critical for maintaining cleanroom classification and environmental conditions for GMP manufacturing.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1, ISO 14644, ASHRAE 62.1",
            "verification_method": "Functional Test / OQ",
            "acceptance_criteria": "All HVAC components monitored and controlled; room classifications maintained per design.",
        },
        {
            "requirement": "The BMS shall monitor differential pressure between adjacent rooms in the GMP cleanroom cascade with alarms for pressure exceedances beyond ± 2 Pa of setpoint.",
            "rationale": "Differential pressure cascade prevents contamination migration between areas of different cleanliness.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 1 §4.22, ISO 14644-4",
            "verification_method": "Functional Test",
            "acceptance_criteria": "ΔP alarms triggered at ± 2 Pa deviation; continuous monitoring 24/7; alarm logged.",
        },
        {
            "requirement": "The BMS shall provide trend reports, energy monitoring dashboards, and compliance reports for all monitored parameters.",
            "rationale": "Trend reports support environmental monitoring programs and energy efficiency initiatives.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Annex 1, ICH Q10",
            "verification_method": "Functional Test",
            "acceptance_criteria": "All specified reports generated accurately; data retrievable for 5 years.",
        },
        {
            "requirement": "The BMS shall integrate with the calibration management system for instrument calibration due date tracking and out-of-calibration alarms.",
            "rationale": "Calibration status integration ensures only calibrated instruments are used for GMP monitoring.",
            "priority": "High",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 3, 21 CFR 211.68",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Out-of-calibration instruments flagged; alarm generated; GMP monitoring data excluded.",
        },
    ],
    "Alarm Requirements": [
        {
            "requirement": "BMS alarms shall be categorized by priority (Critical, Major, Minor) with escalation notification via email/SMS to defined personnel for Critical alarms.",
            "rationale": "Alarm prioritization ensures appropriate response and prevents critical GMP deviations going unaddressed.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Annex 11, EEMUA 191",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Alarm priority correctly assigned; Critical alarm notifications sent within 2 minutes; escalation list current.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The BMS shall maintain a GMP-compliant audit trail for all parameter changes, setpoint modifications, alarm events, and user actions.",
            "rationale": "BMS audit trail supports environmental monitoring compliance and GMP inspections.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11, ALCOA+",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "Audit trail comprehensive; cannot be modified; QA access confirmed.",
        },
    ],
}

ERP: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The ERP system shall manage pharmaceutical material master data including material codes, specifications, shelf life, and storage conditions.",
            "rationale": "Centralized material master ensures consistent data across all business processes.",
            "priority": "Critical",
            "gmp_criticality": "GMP",
            "regulatory_ref": "EU GMP Chapter 4, ICH Q10",
            "verification_method": "Functional Test / UAT",
            "acceptance_criteria": "Material master data accurately maintained; all specified fields functional.",
        },
        {
            "requirement": "The ERP shall support batch/lot management with complete traceability from raw material receipt through finished product dispatch.",
            "rationale": "Batch traceability is a GMP requirement and supports recall management.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, 21 CFR 211.188",
            "verification_method": "UAT",
            "acceptance_criteria": "Forward and backward batch traceability demonstrated in UAT scenarios.",
        },
        {
            "requirement": "The ERP shall enforce quality status management (Quarantine, Approved, Rejected) with access controls preventing use of unapproved materials.",
            "rationale": "Quality status management prevents use of rejected or unapproved materials in production.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU GMP Chapter 5, 21 CFR 211.101",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Quarantined/Rejected materials cannot be issued for production; system prevents override without QA authorization.",
        },
    ],
    "Audit Trail": [
        {
            "requirement": "The ERP shall maintain an audit trail for all GMP-relevant transactions including material movements, batch record changes, quality status changes, and user access events.",
            "rationale": "ERP audit trail supports GMP compliance and regulatory inspection readiness.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "21 CFR Part 11, EU GMP Annex 11",
            "verification_method": "CSV / Functional Test",
            "acceptance_criteria": "All GMP transactions audited; read-only access for QA; retained 5 years.",
        },
    ],
}

SERIALIZATION_SYSTEM: dict[str, list[dict]] = {
    "Functional Requirements": [
        {
            "requirement": "The serialization system shall generate unique identifiers (UI) compliant with GS1 standards and the applicable regulatory framework (EU FMD, DSCSA, India TRACK & TRACE).",
            "rationale": "Regulatory serialization mandates unique identification of every saleable unit.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU FMD 2011/62/EU, DSCSA, GS1 General Specification",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Unique identifiers generated per GS1 specification; no duplicates; verified against regulatory requirements.",
        },
        {
            "requirement": "The system shall perform aggregation management linking item-level, carton-level, and pallet-level serial numbers.",
            "rationale": "Aggregation enables complete supply chain traceability from unit to pallet.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "GS1, DSCSA Interoperability",
            "verification_method": "Functional Test",
            "acceptance_criteria": "Aggregation hierarchy maintained and verifiable for each batch.",
        },
        {
            "requirement": "The system shall interface with the national medicines verification system (EMVS/DSCSA repository) for serial number reporting and verification.",
            "rationale": "Reporting to national repositories is mandatory under EU FMD and DSCSA.",
            "priority": "Critical",
            "gmp_criticality": "GMP-Critical",
            "regulatory_ref": "EU FMD Regulation 2016/161, DSCSA",
            "verification_method": "Integration Test",
            "acceptance_criteria": "Serial numbers successfully reported; verification queries return correct status.",
        },
    ],
}


# ── Master Requirement Library ────────────────────────────────────────────────

REQUIREMENT_LIBRARY: dict[str, dict[str, list[dict]]] = {
    # Manufacturing Equipment
    "tablet_compression":    TABLET_COMPRESSION,
    "capsule_filling":       CAPSULE_FILLING,
    "coating_machine":       COATING_MACHINE,
    "granulation":           GRANULATION,
    "blending":              BLENDING,
    "fluid_bed_processor":   FLUID_BED_PROCESSOR,
    # Packaging Equipment
    "blister_machine":       BLISTER_MACHINE,
    "metal_detector":        METAL_DETECTOR,
    "labeling_machine":      LABELING_MACHINE,
    "vision_inspection":     VISION_INSPECTION,
    # Laboratory Equipment
    "hplc":                  HPLC,
    "dissolution":           DISSOLUTION,
    "stability_chamber":     STABILITY_CHAMBER,
    "autoclave":             AUTOCLAVE,
    # Utilities
    "purified_water":        PURIFIED_WATER,
    "wfi":                   WFI,
    "compressed_air":        COMPRESSED_AIR,
    # Computerized Systems
    "scada":                 SCADA,
    "mes":                   MES,
    "lims":                  LIMS,
    "barcode_system":        BARCODE_SYSTEM,
    "bms":                   BMS,
    "erp":                   ERP,
    "serialization_system":  SERIALIZATION_SYSTEM,
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_library_requirements(equipment_type: str) -> dict[str, list[dict]]:
    """Return merged requirement library for the given equipment type.

    Always prepends COMMON_REQUIREMENTS so GMP fundamentals are always
    included. Equipment-specific sections follow.
    """
    equipment_type = equipment_type.lower().strip().replace(" ", "_").replace("-", "_")
    specific = REQUIREMENT_LIBRARY.get(equipment_type, {})
    merged: dict[str, list[dict]] = {}
    for section, reqs in COMMON_REQUIREMENTS.items():
        merged[section] = list(reqs)
    for section, reqs in specific.items():
        if section in merged:
            merged[section] = merged[section] + list(reqs)
        else:
            merged[section] = list(reqs)
    return merged


def build_numbered_requirements(equipment_type: str) -> list[dict]:
    """Convert library into a flat list with auto-generated req_id codes."""
    sections = get_library_requirements(equipment_type)
    result = []
    section_counters: dict[str, int] = {}
    for section, reqs in sections.items():
        prefix = SECTION_PREFIX.get(section, "REQ")
        if prefix not in section_counters:
            section_counters[prefix] = 0
        for req in reqs:
            section_counters[prefix] += 1
            item = dict(req)
            item["req_id"] = f"{prefix}-{section_counters[prefix]:03d}"
            item["section"] = section
            item["status"] = "draft"
            item["source"] = "library"
            result.append(item)
    return result


def list_equipment_types() -> list[str]:
    """Return all equipment types that have library requirements."""
    return sorted(REQUIREMENT_LIBRARY.keys())


def get_sections_for_type(equipment_type: str) -> list[str]:
    """Return all sections available for an equipment type."""
    sections = get_library_requirements(equipment_type)
    return list(sections.keys())
