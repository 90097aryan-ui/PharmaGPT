"""Quality control / end-of-line equipment: Checkweigher, Metal Detector."""

from equipment import EquipmentProfile, _register

# ─── Checkweigher ─────────────────────────────────────────────────────────────

_register(EquipmentProfile(
    name="CHECKWEIGHER",
    aliases=["check weigher", "in-line checkweigher", "dynamic checkweigher",
             "automatic checkweigher", "weight checker", "checkweighing machine"],
    description=(
        "A Checkweigher is an in-line dynamic weighing system that measures the weight of "
        "every package (bottle, carton, blister) at production line speed and rejects "
        "underweight or overweight items. Operates at 30–400 packs/min with ±0.1–1.0 g "
        "accuracy. Governed by OIML R 51 and NAWI (Non-Automatic Weighing Instrument) "
        "regulations for legal-for-trade applications."
    ),
    applicable_regulations=[
        "21 CFR Part 211.160 — General laboratory controls (fill quantity)",
        "21 CFR Part 211.194 — Laboratory records",
        "EU GMP Chapter 5 — Production (fill accuracy)",
        "EU GMP Annex 15 — Qualification and Validation",
        "OIML R 51 — Automatic checkweighing instruments (accuracy classes)",
        "EU Directive 2014/31/EU — Non-automatic weighing instruments (NAWI)",
        "MID (Measuring Instruments Directive) 2014/32/EU — if legal-for-trade",
        "ISO 4948 / EHEDG guidelines for hygienic design (food/pharma)",
        "Schedule M — GMP for Pharmaceuticals (India)",
    ],
    required_utilities=[
        "Electrical: 220–240 V AC, 50 Hz, 10 A",
        "Compressed air: 6 bar (for rejection mechanism — air blast or push rod)",
        "Stable vibration-free mounting: checkweighers are extremely sensitive to floor vibration",
        "Integration with upstream/downstream conveyors: speed-matched (PLC signal handshake)",
        "Production environment: 18–25°C; avoid HVAC draughts near weigh cell",
    ],
    critical_components=[
        "Electromagnetic Force Restoration (EMFR) or strain-gauge weigh cell",
        "Infeed, weigh, and outfeed conveyor belts (independently speed-controlled)",
        "Rejection mechanism: air blast, push rod, or diverter gate",
        "HMI display with real-time weight histogram, statistics, and SPC charting",
        "PLC with recipe management and audit trail (21 CFR Part 11 if electronic records)",
        "Rejection bin with full-bin sensor and interlocked bin gate",
        "Reject confirmation sensor (photocell or weight verification downstream)",
        "Ethernet/OPC-UA for MES/SCADA integration",
    ],
    iq_checklist=[
        "Verify checkweigher model, weigh cell type, accuracy class, and speed range against URS",
        "Confirm weigh cell range covers product weight ± 20%",
        "Verify rejection mechanism type and ejection speed compatibility with product",
        "Check infeed/weigh/outfeed belt drive and speed controller installation",
        "Confirm HMI software version, recipe management, and audit trail configuration",
        "Verify rejection bin full-sensor installation and alarm linkage",
        "Check all mechanical guards and safety stops for moving belt components",
        "Confirm earthing and electrical safety (vibration environment — check connections)",
        "Register instrument in asset management system with OIML class and legal-for-trade stamp",
        "Verify vibration isolation feet or mounting platform installation",
    ],
    oq_tests=[
        "Static accuracy: 5 NIST-traceable weights (spanning ±5% of target product weight) — ±0.2g or ±0.5% (product-specific)",
        "Dynamic accuracy: run certified reference weights on conveyor at production speed — ±sigma ≤ OQ tolerance",
        "Tare zeroing: confirm automatic tare after product removal, display returns to 0.0 g",
        "Under-weight rejection: product 5% below lower limit (LCL) — 100% rejected",
        "Over-weight rejection: product 5% above upper control limit (UCL) — 100% rejected",
        "Rejection confirmation: downstream sensor confirms each ejected pack count",
        "Speed stability: belt speed ±2% of set value over 10-minute run",
        "Statistics / histogram accuracy: display mean and sigma match manual calculation within 0.05 g",
        "Audit trail: all parameter changes logged with user, timestamp, and old/new values",
        "Interlock: production line cannot run if rejection bin gate is open",
    ],
    pq_tests=[
        "Dynamic accuracy over full production batch: all accepted packs within specification",
        "Rejection efficiency: 0 non-conforming packs escape to finished goods (full batch reconciliation)",
        "Statistical Process Control: Cpk ≥ 1.33 for fill weight using checkweigher data",
        "False reject rate: ≤ 0.05% (non-defective packs incorrectly rejected)",
        "Data integrity: all production data exported to MES/SCADA without loss",
        "Batch-to-batch repeatability: 3 consecutive batches, mean weight within ±0.5% of target",
    ],
    calibration_points=[
        "Static calibration: 0 g (tare), 25%, 50%, 75%, 100%, 125% of target weight — OIML Class F2 reference weights",
        "Dynamic calibration: certified test weight at production line speed — at intervals per SOP",
        "Speed calibration: conveyor belt speed (m/min) at 3 settings — calibrated tachometer",
        "Rejection mechanism: test timing delay (ms) at line speed — production speed simulation",
    ],
    safety_checks=[
        "Belt pinch-point guards at infeed and outfeed transitions",
        "All belt drives enclosed with interlocked covers",
        "Emergency stop accessible from both infeed and outfeed positions",
        "Rejection bin full alarm: production stops if bin full to prevent overflowing into good goods",
        "Electrical earthing: weigh cell electronics sensitive to ESD — verify earthing ≤ 1 Ω",
    ],
    documentation_checklist=[
        "Vendor calibration certificate (factory, OIML traceable)",
        "OIML class certificate and legal-for-trade stamp (if applicable)",
        "NIST-traceable reference weight calibration certificates (used for OQ)",
        "HMI/PLC software validation report and audit trail configuration",
        "Rejection bin audit: records of all rejected packs per batch",
        "Instrument logbook (calibration, PM, speed changes, deviations)",
        "Cleaning and format changeover SOP",
        "Training records for all line operators",
        "Preventive Maintenance SOP (belt replacement, weigh cell cleaning)",
    ],
    standard_acceptance_criteria=[
        "Static accuracy: ±0.2 g or ±0.5% of target weight (whichever is greater)",
        "Dynamic accuracy: ±sigma ≤ product-specific tolerance",
        "Under/overweight rejection: 100% at defined LCL/UCL",
        "False reject rate: ≤ 0.05%",
        "Process capability: Cpk ≥ 1.33 for fill weight",
        "Rejection bin: 0 non-conforming packs in finished goods",
    ],
    common_deviations=[
        "Dynamic weight drift due to floor vibration — install vibration isolation feet",
        "False rejects due to air blasts from nearby equipment — shield weigh cell from draughts",
        "Rejection bin full — increases risk of non-conforming packs not being ejected; enforce bin monitoring",
        "Speed mismatch with upstream conveyor — recheck speed synchronisation after format change",
        "Audit trail time-clock drift — synchronise to network NTP server",
        "Static calibration acceptable but dynamic accuracy fails — investigate belt vibration and damping",
    ],
))


# ─── Metal Detector ───────────────────────────────────────────────────────────

_register(EquipmentProfile(
    name="METAL DETECTOR",
    aliases=["pharmaceutical metal detector", "inline metal detector",
             "metal detection system", "metal check", "tablet metal detector",
             "ferrous non-ferrous detector", "stainless steel detector"],
    description=(
        "A Metal Detector detects ferrous, non-ferrous, and stainless steel (SS) contamination "
        "in pharmaceutical products, granules, powders, or finished packs. Uses balanced coil "
        "technology with frequency range 50 kHz–1 MHz. Critical for patient safety and "
        "mandatory for tablet/capsule/powder manufacturing per EU GMP Chapter 5 and FDA expectations. "
        "Integrated with automatic rejection and batch record systems."
    ),
    applicable_regulations=[
        "21 CFR Part 211.68 — Automatic, mechanical, electronic equipment",
        "21 CFR Part 211.100 — Written procedures for production controls",
        "EU GMP Chapter 5 — Production (foreign matter contamination control)",
        "EU GMP Annex 15 — Qualification and Validation",
        "ICH Q9 — Quality Risk Management (metal contamination risk)",
        "ISO 12543-1 — Metal detection in food (applicable as best practice)",
        "BRC/IFS Standards — Foreign body detection (pharmaceutical GMP alignment)",
        "Schedule M — GMP for Pharmaceuticals (India)",
    ],
    required_utilities=[
        "Electrical: 220–240 V AC, 50 Hz, 10–15 A",
        "Compressed air: 6 bar (for rejection air blast)",
        "Conveyor integration: speed-matched with upstream/downstream",
        "Stable environment: avoid large metal machinery within 1 m of aperture",
        "Earthing: independent earth required (balanced coil sensitive to earth loops)",
    ],
    critical_components=[
        "Search head (aperture coil): transmitter coil, two receiver coils (balanced)",
        "Signal processing unit (DSP or analogue) with auto-rejection logic",
        "Rejection mechanism: air blast, band reject, or push rod",
        "Rejection bin with full-bin sensor",
        "Conveyor belt (product-contact: food-grade, non-metallic, antistatic)",
        "HMI display with sensitivity settings, alarm log, and test log",
        "Automatic performance test function (auto-test with known test pieces)",
        "RS-232 / Ethernet for data export and batch record integration",
        "Reject confirmation sensor (confirm reject completed before product gap)",
    ],
    iq_checklist=[
        "Verify metal detector model, aperture size (height × width), and frequency against URS/PO",
        "Confirm product-contact conveyor belt material (non-metallic, food-grade PTFE or urethane)",
        "Verify search head installation: centred on conveyor, no metallic framework within 100 mm",
        "Check rejection mechanism installation and rejection bin position",
        "Confirm rejection bin full-sensor installation and alarm linkage",
        "Verify HMI software version, test log, and audit trail configuration",
        "Check earthing: independent earth bond from detector frame (not shared with drive motors)",
        "Confirm test piece set received (ferrous, non-ferrous, SS spheres of required size)",
        "Register instrument in asset management system with unique equipment ID",
        "Verify reject confirmation sensor installation and alignment",
    ],
    oq_tests=[
        "Sensitivity verification (ferrous): detect 1.5 mm Fe sphere at worst-case aperture position (centre, corners)",
        "Sensitivity verification (non-ferrous): detect 2.0 mm non-Fe sphere (aluminium) at all positions",
        "Sensitivity verification (stainless steel 316L): detect 2.5 mm SS sphere at all positions",
        "Rejection efficiency: each test sphere injected 10 times — 10/10 rejected (100%)",
        "Reject confirmation: downstream sensor confirms each ejected pack",
        "Product effect calibration: sensitivity tuned with actual product at production speed — no false rejects",
        "False reject rate: ≤ 0.05% with product at calibrated sensitivity",
        "Audit trail: all sensitivity changes and test results logged with user and timestamp",
        "Line speed stability: ±2% of set value at production speed",
        "Auto-test function: simulated internal test sphere — pass criteria verified",
    ],
    pq_tests=[
        "Sensitivity over full production batch: manual test pieces run at start, middle, and end of batch",
        "Rejection efficiency over full batch: all spiked test pieces 100% rejected",
        "False reject rate over full batch: ≤ 0.05%",
        "Product effect stability: no nuisance trips after 8-hour continuous run",
        "Batch-to-batch reproducibility: consistent sensitivity over 3 consecutive batches",
        "Data integrity: all test results and production data exported without loss",
    ],
    calibration_points=[
        "Sensitivity (ferrous, non-ferrous, SS): NIST-traceable certified sphere sizes",
        "Conveyor belt speed: calibrated tachometer at production speed",
        "Rejection timing: delay from detection to rejection verified at production speed",
        "Auto-test piece size and detectability: certified test piece with traceable certificate",
    ],
    safety_checks=[
        "No pacemaker / metallic implant warning signage at detector aperture",
        "All belt drive guards interlocked",
        "Emergency stop accessible at infeed and outfeed sides",
        "Rejection bin full alarm: production halts if bin full",
        "Test piece control: test spheres registered, numbered, and tracked; no loss permitted",
        "Earthing: earth bond continuity verified ≤ 1 Ω (sensitive to earth fluctuations)",
    ],
    documentation_checklist=[
        "Vendor installation certificate and factory sensitivity test certificate",
        "Test piece calibration certificates (ferrous, non-ferrous, SS spheres — NIST traceable)",
        "Rejection system qualification records",
        "HMI audit trail configuration document",
        "Instrument logbook (calibration, PM, sensitivity adjustments, test failures)",
        "Test piece inventory and loss/damage register",
        "Approved SOP for metal detector operation and test frequency",
        "Training records for all operators",
        "Preventive Maintenance SOP (search head cleaning, conveyor belt inspection)",
    ],
    standard_acceptance_criteria=[
        "Ferrous sensitivity: detect 1.5 mm Fe sphere at all aperture positions",
        "Non-ferrous sensitivity: detect 2.0 mm non-Fe sphere at all positions",
        "SS 316L sensitivity: detect 2.5 mm SS sphere at all positions",
        "Rejection efficiency: 10/10 (100%) for each test sphere type",
        "False reject rate: ≤ 0.05%",
        "Auto-test frequency: at start and end of every batch, every 2 hours during batch",
        "Test log completeness: 100% of scheduled tests documented with pass/fail result",
    ],
    common_deviations=[
        "Product effect causing nuisance trips — adjust frequency and phase angle; document change",
        "False reject rate > 0.05% — investigate product moisture, foil contamination of belt",
        "Test piece loss — implement test piece accountability register; search before next batch",
        "Sensitivity drift after cleaning — re-calibrate sensitivity after every belt change or cleaning",
        "Earth loop from nearby drive motor causing interference — install independent earth bond",
        "Rejection bin full not alarmed — bin full sensor dirty or disconnected; include in PM check",
    ],
))
