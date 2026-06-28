"""Quality control testing equipment: Dissolution Tester, Friability Tester, Hardness Tester."""

from equipment import EquipmentProfile, _register

# ─── Dissolution Tester ───────────────────────────────────────────────────────

_register(EquipmentProfile(
    name="DISSOLUTION TESTER",
    aliases=["dissolution apparatus", "dissolution testing machine", "dissolution bath",
             "usp dissolution apparatus", "tablet dissolution", "dissolution system"],
    description=(
        "A Dissolution Tester (USP Apparatus I–VII) measures the rate and extent of drug "
        "release from solid oral dosage forms (tablets, capsules, transdermal patches). "
        "Core components include a temperature-controlled water bath, rotating basket (App. I) "
        "or paddle (App. II), vessels, and integrated UV or auto-sampling systems. "
        "Critical for in-vitro–in-vivo correlation (IVIVC) and product release testing."
    ),
    applicable_regulations=[
        "21 CFR Part 211.194 — Laboratory records and test requirements",
        "USP <711> — Dissolution",
        "USP <724> — Drug Release (extended-release)",
        "USP <1092> — The Dissolution Procedure: Development and Validation",
        "EP 2.9.3 — Dissolution Test for Solid Dosage Forms",
        "ICH Q2(R1) — Validation of analytical procedures (UV method for dissolution)",
        "FDA Guidance: Dissolution Testing of Immediate Release Solid Oral Dosage Forms (1997)",
        "ASTM E2503 — Practice for qualification of dissolution apparatus",
    ],
    required_utilities=[
        "Electrical: 220–240 V AC, 50 Hz, 15 A (with temperature controller load)",
        "Purified water (Type 2/3): supply for dissolution media preparation",
        "Stable ambient temperature: 20–25°C to avoid heat transfer errors",
        "Vibration-free bench: mechanical vibration is a critical interference source",
        "UV spectrophotometer or HPLC for dissolution sample analysis",
        "Auto-sampler tubing (inert silicone/PTFE) and collection vials if automated",
        "Membrane filters (0.45 µm) for sample filtration if required by method",
    ],
    critical_components=[
        "Water bath with immersion heater and circulation pump (temperature uniformity ±0.5°C)",
        "Shaft / spindle motor with speed controller (RPM accuracy ±4%)",
        "Basket (App. I: 40 mesh, stainless steel) or paddle (App. II: USP dimensions)",
        "Dissolution vessels (1000 mL borosilicate glass, hemispherical bottom)",
        "Vessel covers with sampling ports",
        "Temperature probe (immersed in medium, NTC/PT100)",
        "Auto-sampling system with tubing, pump, and UV flow-through cell (if equipped)",
        "Shaft wobble detection mechanism (wobble ≤ 0.5 mm per USP)",
        "Drive motor speed calibration mechanism",
    ],
    iq_checklist=[
        "Verify dissolution apparatus type (I, II, IV, etc.) and number of vessels against URS/PO",
        "Confirm vessel geometry per USP specification (height, diameter, hemispherical radius)",
        "Verify basket/paddle dimensions against USP <711> Table 1 requirements",
        "Check shaft / spindle alignment: wobble ≤ 0.5 mm at vessel bottom",
        "Confirm temperature controller range, probe type, and calibration date",
        "Verify motor speed controller range and display resolution (1 RPM minimum)",
        "Check vessel covers for sampling port and degassing port integrity",
        "Verify auto-sampler tubing material (insoluble, non-reactive — PTFE or silicone)",
        "Confirm utility connections: electrical earthing, water bath fill requirements",
        "Check instrument registration in asset management with unique ID tag",
        "Confirm all accessories (baskets, paddles, sinkers, O-rings) received and documented",
    ],
    oq_tests=[
        "Temperature accuracy: 37.0 ± 0.5°C in all vessels simultaneously (6/8 vessels) — calibrated probe",
        "Temperature uniformity: ΔT between vessels ≤ 0.5°C",
        "Temperature stability: ≤ ±0.5°C variation over 60 minutes",
        "Spindle rotation speed accuracy: 50, 75, 100 RPM — actual vs. set ±4%",
        "Basket wobble test: ≤ 0.5 mm lateral movement at mid-height of vessel",
        "Paddle wobble test: ≤ 0.5 mm lateral movement",
        "Basket dimension verification: mesh size, wire diameter, basket diameter (USP <711>)",
        "Vessel volume accuracy: fill to 900 mL ± 5 mL",
        "Sampling probe position: 10 mm ± 2 mm from vessel wall and surface (USP)",
        "Mechanical calibration (USP Calibrators): Prednisone (App. I/II) or Salicylic acid (App. II) within NF specification",
    ],
    pq_tests=[
        "Precision of dissolution profile: RSD ≤ 3% across vessels at each time point",
        "Accuracy: dissolution values within ±5% of reference/target specification",
        "Discrimination: apparatus distinguishes between fast and slow release formulations",
        "Robustness to pH: dissolution at pH 1.2, 4.5, 6.8 — method specific acceptance",
        "Filter validation: dissolved drug not adsorbed to filter, recovery 98–102%",
        "Sink condition verification: medium volume ≥ 3× saturation concentration",
        "Analyst comparison: two analysts, RSD between datasets ≤ 3%",
    ],
    calibration_points=[
        "Temperature probes (all vessels): 35°C, 37°C, 40°C — NIST-traceable reference thermometer",
        "Motor speed (RPM): 25, 50, 75, 100, 150, 200 RPM — calibrated tachometer",
        "Timer/clock accuracy: ±30 seconds over 60 minutes",
        "UV spectrophotometer or HPLC linked to dissolution — per analytical instrument calibration SOP",
    ],
    safety_checks=[
        "Water bath overheat protection: high-temperature cutoff tested at set limit +5°C",
        "Electrical earthing of water bath: ≤ 1 Ω",
        "GFCI/RCD protection for water-proximity electrical equipment",
        "Mechanical guarding of drive shaft and motor to prevent contact injury",
        "Acid/base dissolution media: appropriate PPE (gloves, goggles) and neutralisation station",
    ],
    documentation_checklist=[
        "Vendor installation certificate and factory calibration certificate",
        "USP Mechanical Calibration report (Prednisone/Salicylic acid records)",
        "Calibration certificates for temperature probes and tachometer",
        "Basket and paddle dimensional verification records",
        "Approved dissolution method SOP referencing apparatus number and vessel IDs",
        "Instrument logbook (calibration, PM, basket/paddle changes, deviations)",
        "Training records for all operators",
        "Preventive Maintenance SOP (basket inspection, vessel cleaning, O-ring replacement)",
    ],
    standard_acceptance_criteria=[
        "Temperature: 37.0 ± 0.5°C (all vessels simultaneously)",
        "Spindle speed accuracy: ±4% of set value (USP requirement)",
        "Basket/paddle wobble: ≤ 0.5 mm",
        "Vessel volume: 900 mL ± 5 mL",
        "Inter-vessel precision: RSD ≤ 3% at each time point",
        "USP mechanical calibration: Prednisone within NF specification (Q value and %RSD)",
        "Filter recovery: 98–102%",
    ],
    common_deviations=[
        "Spindle wobble > 0.5 mm due to shaft wear — inspect and replace spindle",
        "Temperature non-uniformity between vessels — check circulation pump and heater",
        "Basket mesh corrosion or clogging affecting drug release — replace baskets per SOP",
        "Air bubble formation in vessel affecting paddle hydrodynamics — enforce degassing SOP",
        "USP mechanical calibration failure — immediate OOS investigation required",
        "Sampling tubing contamination or adsorption — validate filter and tubing per method",
        "Vessel volume inaccuracy — verify volume with calibrated volumetric vessel",
    ],
))


# ─── Friability Tester ────────────────────────────────────────────────────────

_register(EquipmentProfile(
    name="FRIABILITY TESTER",
    aliases=["friabilator", "tablet friability", "friability testing machine", "friability apparatus"],
    description=(
        "A Friability Tester (Friabilator) measures the physical strength of uncoated tablets "
        "by subjecting them to abrasion and shock in a rotating drum. Per USP <1216> and "
        "EP 2.9.7, the test determines percentage weight loss of tablets after 100 revolutions "
        "at 25 RPM. Critical for tablet mechanical integrity assessment during process "
        "development and QC release testing."
    ),
    applicable_regulations=[
        "21 CFR Part 211.194 — Laboratory records",
        "USP <1216> — Tablet Friability",
        "EP 2.9.7 — Friability of Uncoated Tablets",
        "BP Appendix XVI G — Friability of Uncoated Tablets",
        "Schedule M (India) — Good Manufacturing Practices for Pharmaceuticals",
        "ICH Q6A — Specifications: Test Procedures and Acceptance Criteria for New Drug Substances",
    ],
    required_utilities=[
        "Electrical: 220–240 V AC, 50 Hz, 5 A",
        "Stable ambient temperature: 20–25°C; relative humidity: 40–60% RH (moisture affects friability)",
        "Analytical balance: ≥ 0.1 mg resolution, calibrated and levelled",
        "Dedusting brush and sieve for pre-/post-test tablet dedusting",
    ],
    critical_components=[
        "Drum: transparent polycarbonate, internal diameter 283–291 mm, depth 36–40 mm",
        "Drum motor with speed controller: 25 ± 1 RPM",
        "Revolution counter / timer: 100 revolutions ± 1 revolution",
        "Drum inner projecting tab (6 mm radius, 25.4 mm from inner wall, 26 mm depth)",
        "Drive shaft and locking mechanism for drum attachment",
    ],
    iq_checklist=[
        "Verify drum dimensions (internal diameter 283–291 mm, depth 36–40 mm) against USP <1216>",
        "Confirm projecting tab geometry (radius 6 mm, position per USP drawing)",
        "Verify motor speed range includes 25 RPM",
        "Check revolution counter accuracy and reset function",
        "Confirm drum locking mechanism is secure during operation",
        "Verify drum material (polycarbonate) and surface smoothness (no scratches)",
        "Check instrument registration in asset management system",
        "Confirm analytical balance availability and calibration status for pre/post weighing",
    ],
    oq_tests=[
        "Drum rotation speed: 25 ± 1 RPM verified with calibrated tachometer",
        "Revolution count accuracy: 100 revolutions ± 1 revolution (3 replicate counts)",
        "Timer accuracy: 4 minutes ± 5 seconds for 100 revolutions at 25 RPM",
        "Drum balance: no vibration or wobble during rotation at 25 RPM",
        "Counter reset function: counter resets to 0 and stops drum at target revolutions",
        "Temperature and humidity conditions: confirm laboratory conditions documented",
    ],
    pq_tests=[
        "Friability of reference placebo tablets: % weight loss ≤ 1.0% (USP acceptance)",
        "Repeatability: 3 runs of same batch, % weight loss RSD ≤ 5%",
        "Operator comparison: two operators, results within ±0.2% absolute",
    ],
    calibration_points=[
        "Drum rotation speed (25 RPM) — calibrated contact or optical tachometer",
        "Revolution counter (100, 200 revolutions) — manual count verification",
        "Analytical balance used for pre/post weighing — per balance calibration SOP",
    ],
    safety_checks=[
        "Interlocking drum cover: drum cannot rotate if cover is open",
        "Motor thermal overload protection verified",
        "No entanglement risk: drum cover fully secured before start",
        "Tablet dust: use dedusting chamber or PPE (dust mask) during tablet handling",
    ],
    documentation_checklist=[
        "Vendor installation certificate",
        "Drum dimensional verification records (internal diameter, depth, tab geometry)",
        "Tachometer calibration certificate used for OQ",
        "Instrument logbook (calibration, PM, deviations)",
        "Approved SOP for friability testing referencing this instrument ID",
        "Training records for authorised operators",
    ],
    standard_acceptance_criteria=[
        "Drum speed: 25 ± 1 RPM",
        "Revolution count accuracy: ±1 revolution over 100 revolutions",
        "Friability result (USP <1216>): ≤ 1.0% weight loss (uncoated tablets)",
        "Repeatability: RSD ≤ 5% between replicate runs",
    ],
    common_deviations=[
        "Tablet breakage (not erosion) invalidating test — investigate tablet mechanical strength",
        "Humidity deviation during test affecting hygroscopic tablet results",
        "Counter stopping before 100 revolutions due to motor thermal cut-off",
        "Pre-test dedusting step not performed — SOP must mandate dedusting and initial weight",
    ],
))


# ─── Hardness Tester ──────────────────────────────────────────────────────────

_register(EquipmentProfile(
    name="HARDNESS TESTER",
    aliases=["tablet hardness tester", "tablet hardness testing", "hardness testing machine",
             "crushing strength tester", "tablet crusher", "monsanto hardness tester",
             "erweka hardness", "schleuniger"],
    description=(
        "A Tablet Hardness Tester (Crushing Strength Tester) measures the mechanical "
        "resistance of tablets to compression using a calibrated jaw system. Hardness is "
        "expressed in Newtons (N) or Kiloponds (kP). Modern instruments combine hardness, "
        "thickness, and diameter measurement in one test cycle. Critical for process control "
        "during tablet compression and finished product release."
    ),
    applicable_regulations=[
        "21 CFR Part 211.194 — Laboratory records",
        "USP <1217> — Tablet Breaking Force",
        "EP 2.9.8 — Resistance to Crushing of Tablets",
        "Schedule M (India) — Tablet manufacturing controls",
        "ICH Q6A — Specifications and acceptance criteria",
    ],
    required_utilities=[
        "Electrical: 220–240 V AC, 50 Hz, 5 A",
        "Compressed air: 6 bar ± 0.5 bar (if pneumatic jaw drive model)",
        "Stable ambient conditions: 20–25°C, 40–60% RH",
        "Printer or RS-232/USB interface for data output (if auto-recording model)",
    ],
    critical_components=[
        "Force measurement cell (load cell) with range 0–500 N or 0–1000 N",
        "Jaw assembly: fixed anvil and moving jaw with hardened steel contact surfaces",
        "Micrometer / position sensor for tablet thickness and diameter measurement",
        "Display/printer for force (N), thickness (mm), diameter (mm) output",
        "Automatic tablet feeder / magazine (if automated model)",
        "RS-232 / USB / LIMS interface for data transfer",
    ],
    iq_checklist=[
        "Verify instrument model, serial number, and force range against URS/PO",
        "Confirm load cell capacity covers expected tablet hardness range",
        "Verify jaw material (hardened steel) and jaw surface finish",
        "Check thickness and diameter measurement probes for calibration stickers",
        "Confirm data output interface (print, RS-232, USB) operational",
        "Verify instrument is level (spirit level) and vibration-free",
        "Register instrument in asset management system with unique ID",
        "Confirm all accessories (calibration weights, certificate) received",
    ],
    oq_tests=[
        "Force measurement accuracy: NIST-traceable reference weights at 50 N, 100 N, 200 N, 500 N (±2 N or ±1%)",
        "Force measurement repeatability: 5 readings of 100 N reference weight, RSD ≤ 1%",
        "Thickness measurement accuracy: gauge blocks at 3 mm, 5 mm, 8 mm (±0.01 mm)",
        "Diameter measurement accuracy: gauge pins at 5 mm, 8 mm, 12 mm (±0.05 mm)",
        "Zero force calibration: jaw closure with no tablet gives 0.0 N reading",
        "Data printout / transfer accuracy: values on printout match display readings",
        "Jaw alignment: contact across full tablet width (parallelism verification with feeler gauge)",
    ],
    pq_tests=[
        "Precision: 10 tablets from same batch, hardness RSD ≤ 5% (typically ≤ 3%)",
        "Accuracy: reference tablet of known breaking force (certified standard) within ±5%",
        "Analyst comparison: two analysts, mean hardness within ±5%",
        "Correlation with compression force: hardness trend matches expected curve",
    ],
    calibration_points=[
        "Force cell: 50, 100, 200, 500 N — NIST-traceable calibrated weights",
        "Thickness gauge: 3, 5, 8 mm — calibrated gauge block set",
        "Diameter gauge: 5, 8, 12 mm — calibrated pin gauge set",
        "Zero and span adjustment after each calibration",
    ],
    safety_checks=[
        "Jaw guard / shield in place during automatic operation",
        "Auto-stop on jaw overload: verified at 110% of rated capacity",
        "Pinch-point guarding between jaw and tablet feeder",
        "Tablet ejection mechanism does not propel fragments towards operator",
    ],
    documentation_checklist=[
        "Vendor calibration certificate for load cell and dimensional probes",
        "NIST-traceable weight certificates used for OQ calibration",
        "Gauge block and pin gauge calibration certificates",
        "Instrument logbook (calibration, PM, deviations)",
        "Approved SOP for hardness testing referencing this instrument",
        "Training records for authorised operators",
    ],
    standard_acceptance_criteria=[
        "Force accuracy: ±2 N or ±1% of reading (whichever is greater)",
        "Force repeatability: RSD ≤ 1% (reference weight, 5 readings)",
        "Thickness accuracy: ±0.01 mm",
        "Diameter accuracy: ±0.05 mm",
        "Tablet hardness precision (10 tablets): RSD ≤ 5%",
    ],
    common_deviations=[
        "Load cell drift after thermal exposure — enforce warm-up and daily zero/span check",
        "Jaw misalignment causing eccentric fracture of tablets — check parallelism",
        "Tablet fragments jamming in jaw recess — clean jaw after every batch",
        "Data printout not archived — link instrument to LIMS or enforce paper record SOP",
    ],
))
