# Graph Report - .  (2026-07-27)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3381 nodes · 6738 edges · 143 communities (135 shown, 8 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 77 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d73d9ce4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- database.py
- qual.py
- test_companies.py
- test_backfill_projects.py
- DocxGenerator
- test_check_projects_parity.py
- test_security_tenant_rbac_esig.py
- require_role
- Flask
- preamble
- risk.py
- qual.js
- knowledge_base.js
- risk.js
- urs.js
- qms_common.py
- test_workflow_engine.py
- report.py
- test_qms_routes.py
- test_bootstrap_super_admin.py
- get_connection
- report.js
- qual_database.py
- qms_deviations.py
- ReviewIssue
- urs.py
- investigation_case.js
- test_kb_sync.py
- qms_database.py
- review_engine.py
- validation.py
- test_urs_generation_job.py
- qms_change_control.js
- qms_deviations.js
- get_authenticated_client
- urs_database.py
- EngineOpenError
- equipment.js
- call_gemini
- projects.py
- test_investigation_engine.py
- test_risk_generate_endpoint.py
- test_pdf_engines.py
- test_qms_database.py
- equipment_database.py
- qms_change_control.py
- qms_documents.py
- ExtractionEngine
- qms_capa.js
- qms_documents.js
- validation.js
- generate_fixtures.py
- urs_generation_job.py
- knowledge_base.py
- qms_document_database.py
- qms_capa.py
- risk_database.py
- equipment.py
- qms_change_control_database.py
- investigation_engine.py
- retrieve_context
- qms_change_control_service.py
- report_database.py
- review_rules.py
- qms_common.js
- test_pipeline.py
- docs.py
- projects.js
- test_phase_f_compliance.py
- _register
- qms_deviation_database.py
- get_dashboard
- dashboard.js
- test_equipment_database.py
- test_equipment_dual_write.py
- test_equipment_routes.py
- test_urs_lifecycle.py
- test_qms_dual_write.py
- job_runner.py
- test_lifecycle_engine.py
- auth.js
- test_urs_audit_logging.py
- test_urs_routes.py
- app.py
- extract_sync
- test_projects_dual_write.py
- chat.js
- notifications.js
- test_migrations_rls_recursion.py
- test_project_workspace.py
- document_processor.py
- test_approval_engine.py
- urs_lifecycle.py
- test_app_auth_integration.py
- test_kb_dual_write.py
- test_urs_docx_download_auth.py
- audit.py
- project_workspace.js
- test_creator_attribution.py
- _investigation_lock
- search_project_documents
- urs_requirement_library.py
- validation_dashboard.js
- test_equipment_links.py
- test_login_ui.py
- investigation_prompt.py
- dashboard.py
- admin_assume_context.js
- test_equipment_library.py
- test_validation_retired_doc_types.py
- urs_service.py
- admin_companies.js
- admin_users.js
- qms_document_prompt.py
- finalize_summary
- favorites.js
- recent_items.js
- ui_states.js
- test_project_equipment_link.py
- test_routes_upload_async.py
- backend.py
- qms_deviation_prompt.py
- equipment_service.py
- lifecycle_engine.py
- search.js
- _FakeCandidate
- hello.py
- backfill_deviation_status_v2.py
- migrate_investigation_v2.py
- docx_reader.py
- excel_reader.py
- insights.js
- validation_config.js
- mock_gemini
- db/__init__.py
- extraction/__init__.py
- workspace.js
- authed_client
- test_create_urs_ignores_client_supplied_approved_status
- test_approval_performed_by_derived_from_authenticated_user

## God Nodes (most connected - your core abstractions)
1. `get_connection()` - 262 edges
2. `require_role()` - 57 edges
3. `extract_bearer_token()` - 49 edges
4. `get_authenticated_client()` - 41 edges
5. `_as()` - 36 edges
6. `DocxGenerator` - 31 edges
7. `preamble()` - 30 edges
8. `ReviewIssue` - 30 edges
9. `markdown_to_docx()` - 28 edges
10. `_record_scoped_or_404()` - 27 edges

## Surprising Connections (you probably didn't know these)
- `_FakeChunk` --uses--> `TenantContext`  [INFERRED]
  tests/test_risk_generate_endpoint.py → pharmagpt/auth/context.py
- `FakeEngine` --uses--> `EngineOpenError`  [INFERRED]
  tests/test_pipeline.py → pharmagpt/services/extraction/base.py
- `FakeEngine` --uses--> `PageExtractionError`  [INFERRED]
  tests/test_pipeline.py → pharmagpt/services/extraction/base.py
- `FakeEngine` --uses--> `ExtractionEngine`  [INFERRED]
  tests/test_pipeline.py → pharmagpt/services/extraction/base.py
- `test_ai_report_unparseable_response_defaults_to_refusal_statement()` --calls--> `run_ai_report()`  [EXTRACTED]
  tests/test_investigation_engine.py → pharmagpt/services/investigation_engine.py

## Import Cycles
- None detected.

## Communities (143 total, 8 thin omitted)

### Community 0 - "database.py"
Cohesion: 0.02
Nodes (86): Connection, _add_column_if_missing(), clear_project_messages(), create_kb_document(), create_kb_version(), create_pending_document_text(), create_project(), delete_document() (+78 more)

### Community 1 - "qual.py"
Cohesion: 0.06
Nodes (75): add_approval(), add_test_case(), complete_protocol(), create_deviation(), create_protocol(), create_qualification(), create_version(), dashboard() (+67 more)

### Community 2 - "test_companies.py"
Cohesion: 0.05
Nodes (59): _as(), client(), _FakeQuery, _FakeResult, FakeSupabaseClient, _patched_clients(), fixture, tests/test_assume_company_context.py — Regression coverage for Phase 3.5's "Assu (+51 more)

### Community 3 - "test_backfill_projects.py"
Cohesion: 0.06
Nodes (65): backfill_equipment(), backfill_equipment_links(), main(), Client, scripts/backfill_equipment.py — One-time Phase 3.4 backfill: SQLite `equipment`, Migrate every SQLite equipment row without a postgres_id yet.     Returns {"mig, Migrate equipment_documents rows (source_type='kb' only, and only     once the, backfill_kb_documents() (+57 more)

### Community 4 - "DocxGenerator"
Cohesion: 0.06
Nodes (39): Path, format_docx_sections(), Return structured data for the DocxGenerator to render as a review appendix., _add_field(), _add_page_field(), _add_paragraph_border_bottom(), _add_paragraph_border_top(), _apply_inline() (+31 more)

### Community 5 - "test_check_projects_parity.py"
Cohesion: 0.06
Nodes (59): check_equipment_parity(), main(), _normalize(), Client, scripts/check_equipment_parity.py — Phase 3.4 parity check (docs/PHASE3_EXECUTI, check_kb_parity(), main(), _normalize() (+51 more)

### Community 6 - "test_security_tenant_rbac_esig.py"
Cohesion: 0.06
Nodes (63): _as(), client(), fixture, parametrize, tests/test_security_super_admin_guard.py — Regression coverage for the Phase 3.5, test_real_company_admin_is_unaffected(), test_super_admin_gets_403_not_a_leak(), _as() (+55 more)

### Community 7 - "require_role"
Cohesion: 0.07
Nodes (58): extract_bearer_token(), Return the bearer token from the current request's Authorization     header, or, Reject the request (403) unless `g.tenant.role` is one of     `allowed_roles`., require_role(), assume_company(), end_assume_company(), list_companies_for_assume(), login() (+50 more)

### Community 8 - "Flask"
Cohesion: 0.06
Nodes (45): before_request, Flask, AuthenticationError, Exception, pharmagpt/auth/context.py — Supabase Auth verification and tenant-context resolu, Raised when a bearer token is missing, invalid, expired, or belongs     to an i, The resolved identity + tenancy facts for one authenticated request., Verify a Supabase Auth access token and resolve it to a TenantContext.      Ra (+37 more)

### Community 9 - "preamble"
Cohesion: 0.06
Nodes (46): get_prompt(), CAPA — Corrective and Preventive Action Report prompt., Return the full Gemini prompt for a CAPA Report.      questionnaire keys     ---, get_prompt(), Change Control — Change Control Document prompt., Return the full Gemini prompt for a Change Control Document.      questionnaire, get_prompt(), Deviation — Deviation Report prompt. (+38 more)

### Community 10 - "risk.py"
Cohesion: 0.07
Nodes (58): _assessment_context(), build_custom_prompt(), build_fmea_prompt(), build_fta_prompt(), build_haccp_prompt(), build_hazop_prompt(), build_mitigation_prompt(), build_review_prompt() (+50 more)

### Community 11 - "qual.js"
Cohesion: 0.07
Nodes (45): addApprovalForm(), addTestCaseManual(), aiReviewProtocol(), createDeviationForm(), createProtocol(), deleteQualification(), filterQualList(), generateTestCases() (+37 more)

### Community 12 - "knowledge_base.js"
Cohesion: 0.08
Nodes (47): confirmDeleteDocument(), docDropZone, docEmptyEl, docListEl, docUploadBtn, docUploadInput, docUploadStatus, escapeHtml() (+39 more)

### Community 13 - "risk.js"
Cohesion: 0.08
Nodes (45): applyRiskFilters(), approvalEntryHtml(), ASSESSMENT_TYPES, assessmentCardHtml(), esc(), fmeaRow(), getRatingClass(), getRPNClass() (+37 more)

### Community 14 - "urs.js"
Cohesion: 0.09
Nodes (42): buildDashboardHTML(), buildDetailRow(), buildReqRow(), createURSRecord(), escHtml(), fetchAndRenderURSList(), formatDate(), formatStatus() (+34 more)

### Community 15 - "qms_common.py"
Cohesion: 0.07
Nodes (47): allowed_file(), delete_from_disk(), delete_kb_from_disk(), file_exists(), get_extension(), get_file_path(), get_kb_file_path(), get_kb_upload_dir() (+39 more)

### Community 16 - "test_workflow_engine.py"
Cohesion: 0.10
Nodes (46): _apply_gate_status(), assign_approvers(), decide_step(), _eligible_roles(), get_instance_state(), is_unlocked(), _now(), Exception (+38 more)

### Community 17 - "report.py"
Cohesion: 0.09
Nodes (45): route, SSE streaming chat endpoint.      Body:   { "message": "...", "project_id": 3, ", stream(), add_approval(), create_report(), create_version(), dashboard(), delete_report() (+37 more)

### Community 18 - "test_qms_routes.py"
Cohesion: 0.05
Nodes (11): Complete context package returned by retrieve_context().      Attributes, RetrievalResult, _dev_reach_qa_approval(), tests/test_qms_routes.py — Flask test-client integration tests for the QMS Phase, Drive a deviation from Draft through the Initiator Manager Review ->     QA Mana, test_deviation_investigation_ai_assistant_and_report(), test_deviation_investigation_knowledge_base(), test_deviation_investigation_knowledge_base_finds_related_deviations() (+3 more)

### Community 19 - "test_bootstrap_super_admin.py"
Cohesion: 0.10
Nodes (42): bootstrap_super_admin(), BootstrapError, build_service_role_client(), create_super_admin_auth_identity(), find_auth_user_by_email(), find_existing_super_admin(), get_super_admin_role_id(), insert_super_admin_profile() (+34 more)

### Community 20 - "get_connection"
Cohesion: 0.09
Nodes (40): get_connection(), Open (or create) the database and return a connection.     row_factory=sqlite3., add_ai_run(), add_evidence(), add_interview(), add_sop_review(), add_task(), add_timeline_event() (+32 more)

### Community 21 - "report.js"
Cohesion: 0.09
Nodes (35): currentVisibleViewId(), hide(), show(), currentVisibleViewId(), observeViewChanges(), pollUserState(), renderAll(), renderUserChips() (+27 more)

### Community 22 - "qual_database.py"
Cohesion: 0.07
Nodes (38): add_approval_entry(), add_test_case(), build_traceability_matrix(), create_deviation(), create_protocol(), create_qualification(), create_version_snapshot(), delete_protocol() (+30 more)

### Community 23 - "qms_deviations.py"
Cohesion: 0.13
Nodes (38): add_impact(), assign_workflow_step(), create_deviation(), decide_workflow_step(), delete_deviation(), _dual_write_create(), _dual_write_delete(), _dual_write_update() (+30 more)

### Community 24 - "ReviewIssue"
Cohesion: 0.09
Nodes (37): ReviewIssue, check_iq_oq_pq_checklist(), check_missing_acceptance_criteria(), check_missing_annexures(), check_missing_approval_page(), check_missing_calibration(), check_missing_equipment_info(), check_missing_footer_header_markers() (+29 more)

### Community 25 - "urs.py"
Cohesion: 0.14
Nodes (35): add_approval(), add_requirement(), create_urs(), create_version(), _current_display_name(), _current_role(), dashboard(), delete_requirement() (+27 more)

### Community 26 - "investigation_case.js"
Cohesion: 0.14
Nodes (34): _acceptKbSuggestion(), _addEvidence(), _addInterview(), _addSopReview(), _addTask(), _addTimelineEvent(), _attachmentIdValue(), _attachmentPickerHtml() (+26 more)

### Community 27 - "test_kb_sync.py"
Cohesion: 0.08
Nodes (26): pharmagpt/tenancy.py — tenant-isolation enforcement for the SQLite-backed live r, Return the non-spoofable identity fields for an e-signature/approval     entry —, Return `record` only if it exists and its company_id matches the     caller's. O, scoped_or_none(), signing_identity(), _kb_rows_for(), parametrize, tests/test_kb_sync.py — Regression coverage for Phase 2's "approved documents au (+18 more)

### Community 28 - "qms_database.py"
Cohesion: 0.07
Nodes (33): create_capa(), delete_capa(), escalate_action(), get_action(), get_actions(), get_all_capas(), get_capa(), get_dashboard_stats() (+25 more)

### Community 29 - "review_engine.py"
Cohesion: 0.11
Nodes (27): Enum, pharmagpt/review — Validation Review Engine (PharmaGPT v0.9.5).  Public API -, _build_approval_recommendation(), _build_recommendations(), _build_reviewer_comments(), _content_key(), _deduct(), get_score_cache() (+19 more)

### Community 30 - "validation.py"
Cohesion: 0.09
Nodes (31): EquipmentProfile, format_profile_for_prompt(), get_equipment_profile(), pharmagpt/equipment/__init__.py — Equipment Intelligence Engine for PharmaGPT v0, Complete GMP validation intelligence for a single equipment type., Return the best-matching EquipmentProfile for the given equipment name string., Render an EquipmentProfile as a structured text block to be injected into     t, delete_generated_doc() (+23 more)

### Community 31 - "test_urs_generation_job.py"
Cohesion: 0.12
Nodes (30): _build_generation_message(), _extract_partial_requirements(), _generate_batch_resilient(), The background job body. Runs on job_runner's thread pool.      Each batch is ge, Human-readable summary for the frontend, e.g.:     '2 of 3 sections generated su, Generate one batch with automatic retry on malformed/truncated output.      Only, Best-effort recovery of complete requirement objects from malformed or     trunc, _run_generation_job() (+22 more)

### Community 32 - "qms_change_control.js"
Cohesion: 0.10
Nodes (25): initQMSChangeControl(), QMS_CC_NARRATIVES, QMS_CC_TABS, qmsCCAcceptImpactSuggestion(), qmsCCAcceptPlanSuggestions(), qmsCCAddAction(), qmsCCAddImpact(), qmsCCApplyFilters() (+17 more)

### Community 33 - "qms_deviations.js"
Cohesion: 0.11
Nodes (27): initQMSDeviations(), QMS_DEV_LIFECYCLE_PHASES, QMS_DEV_STEP_BUTTON_LABELS, qmsDevAcceptImpactSuggestion(), qmsDevAddImpact(), qmsDevApplyFilters(), qmsDevApproversBadge(), qmsDevAssignApprover() (+19 more)

### Community 34 - "get_authenticated_client"
Cohesion: 0.09
Nodes (30): create_equipment(), delete_equipment(), link_kb_document(), _payload(), pharmagpt/db/equipment_repo.py — Postgres CRUD for the `equipment` and `equipme, Insert one row into Postgres `equipment`. Returns the inserted row., Update the mutable fields of one Postgres `equipment` row., Delete one Postgres `equipment` row. Raises if Postgres RESTRICTs the     delet (+22 more)

### Community 35 - "urs_database.py"
Cohesion: 0.08
Nodes (32): add_approval_entry(), add_requirement(), append_requirements(), create_urs(), create_version_snapshot(), delete_requirement(), delete_urs(), finish_generation() (+24 more)

### Community 36 - "EngineOpenError"
Cohesion: 0.14
Nodes (13): EngineOpenError, PageExtractionError, Exception, Raised when an engine cannot open a file at all (corrupted, encrypted,     unsup, Raised by an engine when a single page cannot be read. The pipeline     catches, OCRPlaceholderEngine, PdfplumberEngine, Any (+5 more)

### Community 37 - "equipment.js"
Cohesion: 0.14
Nodes (31): EQ_DOC_ROLE_LABELS, EQ_FIELD_IDS, EQ_FUTURE_MODULES, EQ_TAB_LABELS, EQ_TABS, eqBackToList(), eqCloseLinkDocModal(), eqCloseModal() (+23 more)

### Community 38 - "call_gemini"
Cohesion: 0.12
Nodes (25): build_draft_prompt(), build_effectiveness_prompt(), build_trend_prompt(), _capa_context(), prompts/qms_capa_prompt.py — AI prompt builders for the CAPA module.  Three AI f, ai_suggest_draft(), ai_suggest_effectiveness(), ai_trend_summary() (+17 more)

### Community 39 - "projects.py"
Cohesion: 0.10
Nodes (28): create_project(), delete_project(), pharmagpt/db/projects_repo.py — Postgres CRUD for the `projects` table.  Phase, Insert one row into Postgres `projects`. Returns the inserted row., Update the mutable fields of one Postgres `projects` row. RLS     (company_id =, Delete one Postgres `projects` row., update_project(), clear_conversation() (+20 more)

### Community 40 - "test_investigation_engine.py"
Cohesion: 0.10
Nodes (29): add_investigation_interview(), get_investigation_ai_history(), add_evidence(), add_interview(), get_ai_history(), Interactive, ad-hoc AI analysis — callable any number of times, never     gates, run_ai_assistant(), update_evidence() (+21 more)

### Community 41 - "test_risk_generate_endpoint.py"
Cohesion: 0.11
Nodes (26): _as(), client(), _create_assessment(), _FakeChunk, fixture, tests/test_risk_generate_endpoint.py — Regression coverage for the POST /risk/as, generate_items() starts the SSE response (200, text/event-stream)     before eve, The condition that used to slip through useTemplate()'s missing     res.ok check (+18 more)

### Community 42 - "test_pdf_engines.py"
Cohesion: 0.12
Nodes (13): DocxEngine, ExcelEngine, Any, TxtEngine, parametrize, tests/test_pdf_engines.py — Unit tests for each extraction engine adapter in iso, test_corrupted_pdf_raises_engine_open_error(), test_docx_engine_single_unit_loop() (+5 more)

### Community 44 - "equipment_database.py"
Cohesion: 0.07
Nodes (27): create_equipment(), delete_equipment(), get_all_equipment(), get_equipment(), get_equipment_document_link(), get_equipment_scoped(), get_project_equipment(), import_legacy_equipment() (+19 more)

### Community 45 - "qms_change_control.py"
Cohesion: 0.17
Nodes (26): add_impact(), create_change_control(), delete_change_control(), _dual_write_create(), _dual_write_delete(), _dual_write_update(), export_docx(), get_actions() (+18 more)

### Community 46 - "qms_documents.py"
Cohesion: 0.17
Nodes (27): acknowledge_distribution(), add_distribution(), add_training(), create_document(), create_version(), delete_document(), export_docx(), generate_draft() (+19 more)

### Community 47 - "ExtractionEngine"
Cohesion: 0.11
Nodes (19): ExtractionEngine, ABC, Any, services/extraction/base.py — The ExtractionEngine interface (Strategy pattern)., A single extraction backend for one document handle.      Lifecycle, driven enti, Open the document and return an engine-specific handle.          Raises, Return the number of units the pipeline should loop over when calling         ex, Return the page count to show to users / store in stats. Defaults to         pag (+11 more)

### Community 48 - "qms_capa.js"
Cohesion: 0.13
Nodes (21): initQMSCapa(), qmsCapaAcceptEffectiveness(), qmsCapaAddAction(), qmsCapaApplyDraft(), qmsCapaApplyFilters(), qmsCapaCompleteAction(), qmsCapaCreate(), qmsCapaEscalateAction() (+13 more)

### Community 49 - "qms_documents.js"
Cohesion: 0.12
Nodes (21): initQMSDocuments(), qmsDocAcknowledgeDistribution(), qmsDocAddDistribution(), qmsDocAddTraining(), qmsDocApplyFilters(), qmsDocCompleteTraining(), qmsDocCreate(), qmsDocCreateVersion() (+13 more)

### Community 50 - "validation.js"
Cohesion: 0.13
Nodes (21): backToWizard(), escapeAttr(), escapeHtmlVal(), _finaliseViewer(), _initViewer(), openValidationWizard(), _renderStep(), _runReviewAndShowBadge() (+13 more)

### Community 51 - "generate_fixtures.py"
Cohesion: 0.07
Nodes (26): client(), db_path(), fixtures_dir(), fixture, Build every standard PDF fixture once per test session.      Returns {filename, Point pharmagpt.database at a throwaway SQLite file for this test and     initi, Flask test client wired to the db_path fixture's throwaway database.     pharma, build_all() (+18 more)

### Community 52 - "urs_generation_job.py"
Cohesion: 0.11
Nodes (20): routes/chat.py — SSE streaming chat endpoint.  Route ----- POST /stream   stream, _batch_sections(), _check_finish_reason(), _generate_batch(), GenerationBlockedError, _parse_ai_requirements(), Exception, services/urs_generation_job.py — Background execution of URS AI requirement gene (+12 more)

### Community 53 - "knowledge_base.py"
Cohesion: 0.11
Nodes (24): archive_document(), Mark a Postgres-mirrored KB document 'archived' — the dual-write     counterpar, _dual_write_create(), _dual_write_delete(), kb_delete_document(), kb_download_document(), kb_extraction_status(), kb_folder_counts() (+16 more)

### Community 54 - "qms_document_database.py"
Cohesion: 0.10
Nodes (24): generate_document_number(), Return the next sequential document number, e.g. SOP-QA-0001.      A single-word, acknowledge_distribution(), add_distribution(), add_training(), create_document(), create_version(), delete_document() (+16 more)

### Community 55 - "qms_capa.py"
Cohesion: 0.20
Nodes (24): create_capa(), delete_capa(), _dual_write_create(), _dual_write_delete(), _dual_write_update(), escalate_action(), export_docx(), get_actions() (+16 more)

### Community 56 - "risk_database.py"
Cohesion: 0.12
Nodes (23): add_approval_entry(), add_library_entry(), create_assessment(), delete_assessment(), get_actions(), get_all_assessments(), get_approval_trail(), get_assessment() (+15 more)

### Community 57 - "equipment.py"
Cohesion: 0.15
Nodes (23): create_equipment(), delete_equipment(), _dual_write_create(), _dual_write_delete(), _dual_write_link(), _dual_write_unlink(), _dual_write_update(), equipment_ai_context() (+15 more)

### Community 58 - "qms_change_control_database.py"
Cohesion: 0.11
Nodes (22): add_impact(), create_change_control(), delete_change_control(), get_actions(), get_all_change_controls(), get_change_control(), get_change_controls_for_record(), get_dashboard_stats() (+14 more)

### Community 59 - "investigation_engine.py"
Cohesion: 0.16
Nodes (22): add_investigation_timeline_event(), run_investigation_ai_report(), add_timeline_event(), _evidence_references(), _evidence_summary(), get_evidence(), get_interviews(), get_root_cause() (+14 more)

### Community 60 - "retrieve_context"
Cohesion: 0.14
Nodes (22): _build_context_package(), chunk_text(), _extract_section_title(), _folder_to_source_type(), _get_generated_content(), _load_generated_docs(), _load_kb_all(), _load_project_docs() (+14 more)

### Community 61 - "qms_change_control_service.py"
Cohesion: 0.19
Nodes (20): build_effectiveness_review_prompt(), build_executive_summary_prompt(), build_impact_prompt(), build_implementation_plan_prompt(), build_justification_prompt(), build_regulatory_impact_prompt(), build_risk_summary_prompt(), build_rollback_plan_prompt() (+12 more)

### Community 62 - "report_database.py"
Cohesion: 0.14
Nodes (21): add_approval_entry(), create_report(), create_version_snapshot(), delete_report(), get_all_reports(), get_approval_trail(), get_dashboard_stats(), get_latest_ai_review() (+13 more)

### Community 63 - "review_rules.py"
Cohesion: 0.13
Nodes (21): check_broken_numbering(), check_duplicate_headings(), check_empty_tables(), check_heading_hierarchy(), check_short_sections(), _compliance_keywords(), evaluate_compliance(), _extract_headings() (+13 more)

### Community 64 - "qms_common.js"
Cohesion: 0.18
Nodes (18): initQMSDashboard(), qmsAddComment(), qmsBadge(), qmsBadgeClass(), qmsDeleteAttachment(), qmsFetch(), _qmsGroupState, qmsLoadMeta() (+10 more)

### Community 65 - "test_pipeline.py"
Cohesion: 0.19
Nodes (16): extract_document(), Extract every page of a document, never raising — corrupted, encrypted,     empt, quality_score(), Percentage of pages successfully extracted, rounded to 1 decimal.      Example:, FakeEngine, tests/test_pipeline.py — Unit tests for the page-by-page pipeline (services/extr, A configurable in-memory engine for pipeline testing.      `fail_pages`   : page, test_all_pages_succeed_on_primary_engine() (+8 more)

### Community 66 - "docs.py"
Cohesion: 0.15
Nodes (20): delete_document(), _doc_scoped(), document_extraction_status(), download_document(), list_documents(), project_insights(), route, routes/docs.py — Project document upload, view, download, delete, and insights. (+12 more)

### Community 67 - "projects.js"
Cohesion: 0.13
Nodes (18): activeBannerEl, activeProjMetaEl, activeProjNameEl, confirmDeleteProject(), escapeHtml(), loadProjectHistory(), loadProjects(), modal (+10 more)

### Community 68 - "test_phase_f_compliance.py"
Cohesion: 0.16
Nodes (20): _as(), client(), fixture, tests/test_phase_f_compliance.py — Regression coverage for the Phase F complianc, Linkage stays optional — this is the pre-existing, legitimate     standalone-rep, Control case: proves the block above is role-specific, not a general failure., test_closed_capa_cannot_be_edited(), test_equipment_create_writes_audit_entry_with_company_and_diff() (+12 more)

### Community 69 - "_register"
Cohesion: 0.13
Nodes (12): Add a profile to the registry under its canonical name (upper-cased)., _register(), Analytical instruments: HPLC, GC, UV Spectrophotometer., _autoload(), pharmagpt/equipment/profiles/__init__.py  Imports every profile module so their, No-op — importing this package is sufficient to trigger all registrations., Manufacturing equipment: Tablet Compression Machine, Capsule Filling Machine., Packaging equipment: Blister Packing, Bottle Filling, Cartoner, Labeler. (+4 more)

### Community 70 - "qms_deviation_database.py"
Cohesion: 0.13
Nodes (19): generate_deviation_number(), add_impact(), create_deviation(), delete_deviation(), get_all_deviations(), get_dashboard_stats(), get_deviation(), get_impacts() (+11 more)

### Community 71 - "get_dashboard"
Cohesion: 0.13
Nodes (20): add_investigation_task(), get_investigation_dashboard(), list_investigation_tasks(), update_investigation_task(), add_task(), get_dashboard(), get_task_scoped(), get_tasks() (+12 more)

### Community 72 - "dashboard.js"
Cohesion: 0.21
Nodes (16): daysUntil(), fmtDate(), fmtDateShort(), loadSuiteOverview(), navigateToItem(), renderActivity(), renderConversations(), renderEquipmentCount() (+8 more)

### Community 73 - "test_equipment_database.py"
Cohesion: 0.16
Nodes (15): _make_project(), tests/test_equipment_database.py — PharmaGPT v1.0 Module 2: Equipment entity., Deleting a Project must cascade-delete its Equipment records too., test_create_and_get_equipment(), test_delete_equipment_cascades_document_links(), test_equipment_project_cascade_delete(), test_import_legacy_equipment_creates_prefilled_record(), test_link_and_list_equipment_documents() (+7 more)

### Community 74 - "test_equipment_dual_write.py"
Cohesion: 0.22
Nodes (19): authed(), client(), _create_equipment(), _create_project(), fixture, tests/test_equipment_dual_write.py — Phase 3.4 dual-write coverage (docs/PHASE3_, Equipment is nested under a Project route, and Super Admin (no     company_id) h, Postgres RESTRICTs deleting equipment that still has equipment_links —     this (+11 more)

### Community 75 - "test_equipment_routes.py"
Cohesion: 0.16
Nodes (14): _create_project(), tests/test_equipment_routes.py — PharmaGPT v1.0 Module 2: Equipment HTTP routes., test_create_and_list_project_equipment(), test_create_equipment_requires_name(), test_equipment_ai_context_bundle(), test_get_update_delete_equipment(), test_import_legacy_equipment(), test_import_legacy_equipment_no_data() (+6 more)

### Community 76 - "test_urs_lifecycle.py"
Cohesion: 0.17
Nodes (19): _make_urs(), tests/test_urs_lifecycle.py — Regression coverage for Stabilization Iteration 2, performed_by is derived from the authenticated tenant, so an     authenticated, Priority 5: these move to the approval workflow, so creation must     never acc, The `client` fixture bypasses real auth, but tests/conftest.py's     tenant-sco, test_approval_rejects_skip_ahead_transition(), test_approval_requires_performed_by(), test_approval_valid_transition_sequence_reaches_approved() (+11 more)

### Community 77 - "test_qms_dual_write.py"
Cohesion: 0.11
Nodes (6): authed(), client(), fixture, tests/test_qms_dual_write.py — Phase 3.5 dual-write coverage (docs/PHASE3_EXECU, Super Admin has no standing access to tenant content (PLATFORM_ARCHITECTURE.md, test_super_admin_cannot_create_risk_assessment()

### Community 78 - "job_runner.py"
Cohesion: 0.17
Nodes (12): CeleryJobRunner, JobRunner, ABC, services/job_runner.py — Strategy interface for background job execution.  Today, Strategy interface: "run this function in the background, somehow"., Active implementation: runs jobs on a small in-process thread pool.      Suitabl, Future extension point. Left unimplemented on purpose: adding Celery +     Redis, ThreadPoolJobRunner (+4 more)

### Community 79 - "test_lifecycle_engine.py"
Cohesion: 0.16
Nodes (13): Raise InvalidTransitionError unless `requested` is a legal next status     from, validate_transition(), parametrize, tests/test_lifecycle_engine.py — Regression coverage for the shared lifecycle en, The registry must be the *same* dict object urs_lifecycle.py owns, not     a cop, test_noop_transition_always_allowed(), test_qms_document_illegal_transitions_rejected(), test_qms_document_legal_transitions() (+5 more)

### Community 80 - "auth.js"
Cohesion: 0.25
Nodes (15): boot(), clearStoredSession(), el(), handleLoginSubmit(), hideUserBadge(), logout(), requireCompanyContext(), setSubmitting() (+7 more)

### Community 81 - "test_urs_audit_logging.py"
Cohesion: 0.14
Nodes (8): _FakeCandidate, _FakeClient, _FakeModels, _FakeResponse, _FakeUsage, tests/test_urs_audit_logging.py — Regression coverage for Stabilization Iterati, test_generation_logs_failed_when_every_batch_errors(), test_generation_logs_started_and_completed()

### Community 82 - "test_urs_routes.py"
Cohesion: 0.14
Nodes (8): _FakeCandidate, _FakeClient, _FakeModels, _FakeResponse, _FakeUsage, tests/test_urs_routes.py — Integration tests for URS AI generation through Flask, test_generate_endpoint_returns_immediately_then_completes(), _wait_for_terminal_status()

### Community 83 - "app.py"
Cohesion: 0.18
Nodes (14): errorhandler, handle_404(), handle_405(), handle_500(), health(), index(), route, app.py — Flask application factory for PharmaGPT.  Responsibilities --------- (+6 more)

### Community 84 - "extract_sync"
Cohesion: 0.21
Nodes (15): extract_sync(), Extract text from a document file, choosing the best available engine     chain, slow, tests/test_document_processor.py — Integration tests for services/document_proce, Stress test for the 1000+ page vendor manuals mentioned in the     background re, test_corrupted_pdf_never_raises(), test_empty_pdf(), test_engineering_manual_pdf() (+7 more)

### Community 85 - "test_projects_dual_write.py"
Cohesion: 0.21
Nodes (14): authed(), client(), _create_payload(), fixture, tests/test_projects_dual_write.py — Phase 3.2 dual-write coverage (docs/PHASE3_, Super Admin has no standing access to tenant content (PLATFORM_ARCHITECTURE.md, Context manager: patches the middleware to authenticate every     request in `c, test_dual_write_create_calls_repo_and_stores_postgres_id() (+6 more)

### Community 86 - "chat.js"
Cohesion: 0.26
Nodes (13): appendMessage(), appendSources(), clearBtn, clearConversation(), createStreamingBubble(), getTime(), inputEl, messagesEl (+5 more)

### Community 87 - "notifications.js"
Cohesion: 0.27
Nodes (13): closeDropdown(), esc(), fetchAll(), openCapa(), openChange(), openDoc(), openQual(), openRisk() (+5 more)

### Community 88 - "test_migrations_rls_recursion.py"
Cohesion: 0.21
Nodes (13): _all_up_migrations(), _effective_policies(), _extract_policy_statements(), parametrize, tests/test_migrations_rls_recursion.py — static regression guard against self-re, No policy, as it will actually exist after all migrations are     applied in ord, Regression pin for the exact incident: after 0013 is applied, these     two poli, Yield (policy_name, table_name, statement_body) for every     CREATE POLICY stat (+5 more)

### Community 89 - "test_project_workspace.py"
Cohesion: 0.20
Nodes (12): _create_project(), tests/test_project_workspace.py — PharmaGPT v1.0 Module 3: Project Workspace nav, RBF-001 Fix 2: a status-changing update now emits both the generic     'Project, The 'Project deleted' entry is written (and the qms_audit_trail row     itself i, The polymorphic qms_common endpoints (attachments/comments/approval)     should, routes/workspace.py was deleted (PharmaGPT v1.0 Module 3) — its     /val-project, test_create_project_logs_audit_entry(), test_delete_project_logs_audit_entry_before_removal() (+4 more)

### Community 90 - "document_processor.py"
Cohesion: 0.26
Nodes (10): Kind, _finalize(), process_document_async(), services/document_processor.py — The single entry point for every uploaded docum, The actual background job body. Runs on services/job_runner.py's     thread pool, Submit background extraction for a just-uploaded (or retried) document     and r, _run_extraction_job(), _write_progress() (+2 more)

### Community 91 - "test_approval_engine.py"
Cohesion: 0.21
Nodes (9): services/approval_engine.py — shared, configurable approval-workflow definitions, Return the stage definition matching `action` in the named workflow,     or None, stage_for_action(), tests/test_approval_engine.py — Regression coverage for the shared, configurable, New document types (including a future MFR/BMR/BPR onboarding, per     PHASE_3_I, test_stage_for_action_finds_matching_stage(), test_stage_for_action_returns_none_for_unknown_action(), test_stage_for_action_returns_none_for_unknown_workflow() (+1 more)

### Community 92 - "urs_lifecycle.py"
Cohesion: 0.17
Nodes (11): bump_revision(), InvalidTransitionError, Exception, services/urs_lifecycle.py — URS document status state machine.  Enforces the GMP, Raised when a requested status change is not a legal lifecycle     transition fr, Raise InvalidTransitionError unless `requested` is a legal next     status from, Spreadsheet-column-style increment: A -> B -> ... -> Z -> AA -> AB...      Calle, validate_transition() (+3 more)

### Community 93 - "test_app_auth_integration.py"
Cohesion: 0.15
Nodes (3): client(), fixture, tests/test_app_auth_integration.py — Phase 2 step 2.5 integration tests.  Exer

### Community 94 - "test_kb_dual_write.py"
Cohesion: 0.24
Nodes (12): authed(), client(), fixture, tests/test_kb_dual_write.py — Phase 3.3 dual-write coverage (docs/PHASE3_EXECUT, Super Admin has no standing access to tenant content (PLATFORM_ARCHITECTURE.md, test_dual_write_create_calls_repo_and_stores_postgres_id(), test_dual_write_create_failure_does_not_break_response(), test_dual_write_delete_archives_instead_of_hard_delete() (+4 more)

### Community 95 - "test_urs_docx_download_auth.py"
Cohesion: 0.19
Nodes (12): client(), _login(), fixture, tests/test_urs_docx_download_auth.py — Regression coverage for the DOCX export d, Log in through the real /auth/login route so the session-cookie     fallback is, A request with no Authorization header and no session cookie — a     cold browse, Reproduces the reported bug end-to-end: log in (establishing the     session coo, The session-cookie fallback only applies when a request has *no*     Authorizati (+4 more)

### Community 96 - "audit.py"
Cohesion: 0.26
Nodes (11): _current_ip(), _current_session_id(), _diff(), log(), log_failure(), pharmagpt/audit.py — Phase F: unified, non-spoofable audit-trail logging.  Every, Convenience wrapper for logging a blocked/rejected attempt (e.g. an     illegal, Restrict `old`/`new` to only the keys that actually differ, so an     audit row (+3 more)

### Community 97 - "project_workspace.js"
Cohesion: 0.35
Nodes (10): PW_TABS, pwEsc(), pwField(), pwOpenWorkspace(), pwRenderDqFatSat(), pwRenderHistory(), pwRenderOverview(), pwRenderTab() (+2 more)

### Community 98 - "test_creator_attribution.py"
Cohesion: 0.17
Nodes (7): tests/test_creator_attribution.py — RBF-001 Fix 2 (P0 release blocker): Projects, No matching audit-trail entry exists — created_by must stay '' rather     than b, get_kb_documents() (the list projection, used by GET /kb/documents)     curates, Simulates a pre-Fix-2 row (created before created_by/updated_by/     updated_at, test_kb_document_list_endpoint_includes_creator_fields(), test_legacy_project_backfilled_created_by_from_audit_trail(), test_legacy_project_without_audit_entry_stays_blank_not_fabricated()

### Community 99 - "_investigation_lock"
Cohesion: 0.22
Nodes (10): accept_investigation_kb_suggestion(), add_investigation_evidence(), add_investigation_sop_review(), _investigation_lock(), save_investigation_root_cause(), add_sop_review(), AI output (possible_cause) is written by run_ai_assistant/callers     separately, save_root_cause() (+2 more)

### Community 100 - "search_project_documents"
Cohesion: 0.29
Nodes (9): chunk_text(), services/document_search.py — Relevance search over extracted document text.  Ke, Split text into overlapping word-based chunks.      overlap ensures sentences th, Lowercase, strip punctuation, return a set of tokens longer than 2 chars., Score a chunk against query tokens using Jaccard-style keyword overlap., Search all extracted texts for a project and return the most relevant     chunks, score_chunk(), search_project_documents() (+1 more)

### Community 101 - "urs_requirement_library.py"
Cohesion: 0.24
Nodes (9): build_numbered_requirements(), get_library_requirements(), get_sections_for_type(), list_equipment_types(), urs_requirement_library.py — Pre-built pharmaceutical requirement libraries.  Ar, Return merged requirement library for the given equipment type.      Always prep, Convert library into a flat list with auto-generated req_id codes., Return all equipment types that have library requirements. (+1 more)

### Community 102 - "validation_dashboard.js"
Cohesion: 0.47
Nodes (9): fetchJSON(), fmtDateShort(), loadApprovalQueue(), loadValidationDashboard(), renderActivity(), renderKPIs(), renderProjectsSummary(), renderQuality() (+1 more)

### Community 103 - "test_equipment_links.py"
Cohesion: 0.33
Nodes (8): _make_equipment(), tests/test_equipment_links.py — Regression coverage for the Phase 3 (Enterprise, test_invalid_source_type_rejected(), test_link_equipment_to_capa(), test_link_equipment_to_change_control(), test_link_equipment_to_deviation(), test_link_equipment_to_risk_assessment(), test_nonexistent_qms_record_rejected()

### Community 104 - "test_login_ui.py"
Cohesion: 0.31
Nodes (9): client(), _get_shell(), fixture, tests/test_login_ui.py — IMPLEMENTATION_ROADMAP.md Phase 2 step 2.6.  The proj, test_auth_js_loads_before_business_logic_scripts(), test_login_view_hidden_by_default_in_markup(), test_login_view_markup_present(), test_session_check_view_present() (+1 more)

### Community 105 - "investigation_prompt.py"
Cohesion: 0.39
Nodes (8): build_assistant_prompt(), build_report_prompt(), _context_lines(), _evidence_lines(), _list_lines(), prompts/investigation_prompt.py — AI prompt builders for the Investigation Engin, Itemized rendering of _evidence_summary() (services/investigation_engine.py) —, test_never_invent_rules_and_refusal_statement_are_in_both_prompts()

### Community 106 - "dashboard.py"
Cohesion: 0.28
Nodes (8): get_avg_score(), Return the average validation score across all reviewed documents in this sessio, dashboard_stats(), dashboard_validation_score(), route, routes/dashboard.py — Home Dashboard statistics endpoints.  Routes ------ GE, Return aggregated statistics for the Home Dashboard, scoped to the caller's comp, Return the average validation score from the in-session review cache.      Res

### Community 107 - "admin_assume_context.js"
Cohesion: 0.50
Nodes (8): applyRoleBasedVisibility(), closePicker(), el(), handleAssumeSubmit(), handleEndAssume(), openPicker(), refreshMe(), renderBanner()

### Community 108 - "test_equipment_library.py"
Cohesion: 0.31
Nodes (8): _as(), client(), fixture, tests/test_equipment_library.py — Regression coverage for Phase 2's "Equipment L, Overrides conftest.py's auth-bypassing `client` fixture: this file     needs the, test_equipment_library_includes_owning_project_name(), test_equipment_library_is_tenant_scoped(), test_equipment_library_lists_equipment_across_multiple_projects()

### Community 109 - "test_validation_retired_doc_types.py"
Cohesion: 0.25
Nodes (8): parametrize, tests/test_validation_retired_doc_types.py — Regression coverage for the Generat, No project_id is supplied — if the retired-type guard didn't fire     first, thi, These types have no dedicated suite yet and remain generated here.     Omitting, Locks the retirement list to REPOSITORY_AUDIT.md / DUPLICATE_FUNCTION_     ANALY, test_active_doc_type_not_rejected_by_retirement_guard(), test_retired_doc_type_rejected_before_project_lookup(), test_retired_doc_types_cover_exactly_the_ten_consolidated_types()

### Community 110 - "urs_service.py"
Cohesion: 0.25
Nodes (7): build_ai_review_prompt(), build_generation_prompt(), build_urs_markdown(), urs_service.py — Business logic for the URS Management Suite.  Responsibilities, Convert URS data to a professional Markdown document for DOCX export., Build a structured Gemini prompt for AI requirement generation., Build a Gemini prompt for AI review of a complete URS.

### Community 111 - "admin_companies.js"
Cohesion: 0.54
Nodes (7): closeModal(), el(), escapeHtml(), handleSubmit(), loadAdminCompanies(), openModal(), setCompanyStatus()

### Community 112 - "admin_users.js"
Cohesion: 0.54
Nodes (7): closeModal(), el(), escapeHtml(), handleSubmit(), loadAdminUsers(), openModal(), updateUser()

### Community 113 - "qms_document_prompt.py"
Cohesion: 0.38
Nodes (6): build_draft_prompt(), build_review_prompt(), _doc_context(), prompts/qms_document_prompt.py — AI prompt builders for the Document Control mod, Return a prompt whose response is the full markdown content of the controlled do, Return a prompt whose response is a JSON regulatory-compliance review of the doc

### Community 114 - "finalize_summary"
Cohesion: 0.33
Nodes (7): get_investigation_summary(), save_investigation_summary(), finalize_summary(), get_summary(), _now(), test_finalize_summary_records_who_and_when(), test_summary_open_questions_round_trip()

### Community 115 - "favorites.js"
Cohesion: 0.52
Nodes (6): getAllFlat(), getFavorites(), isFavorite(), readStore(), toggleFavorite(), writeStore()

### Community 116 - "recent_items.js"
Cohesion: 0.52
Nodes (6): getRecent(), readStore(), record(), recordEdited(), recordOpened(), writeStore()

### Community 117 - "ui_states.js"
Cohesion: 0.62
Nodes (6): emptyState(), errorState(), iconSpan(), resolveEl(), skeleton(), uid()

### Community 118 - "test_project_equipment_link.py"
Cohesion: 0.29
Nodes (5): tests/test_project_equipment_link.py — Regression coverage for Phase 2's "every, No-op, exactly like the manual import-legacy endpoint: nothing to     import mea, Companion fix found during the Phase 2 RBAC/audit-trail pass: the     audit entr, test_project_creation_audit_entry_attributes_the_authenticated_user(), test_project_without_equipment_info_creates_no_equipment_record()

### Community 119 - "test_routes_upload_async.py"
Cohesion: 0.43
Nodes (5): tests/test_routes_upload_async.py — Integration tests through Flask's test clie, test_kb_document_upload_and_retry_flow(), test_project_document_retry_requires_file_present_on_disk(), test_project_document_upload_is_fast_then_completes(), _wait_for_terminal_status()

### Community 120 - "backend.py"
Cohesion: 0.40
Nodes (5): get_backend_name(), is_postgres_backend(), backend.py — reads which database backend is active for the current process., Return the configured backend name: "sqlite" (default) or "postgres"., True once DATABASE_BACKEND=postgres — always False until a later phase     sets

### Community 121 - "qms_deviation_prompt.py"
Cohesion: 0.53
Nodes (5): build_capa_suggestion_prompt(), build_impact_prompt(), build_investigation_prompt(), _deviation_context(), prompts/qms_deviation_prompt.py — AI prompt builders for the Deviation Managemen

### Community 122 - "equipment_service.py"
Cohesion: 0.33
Nodes (5): get_equipment_context_bundle(), get_equipment_type_catalog(), services/equipment_service.py — Equipment support services (PharmaGPT v1.0 Modul, Canonical equipment-type names from the static Equipment Intelligence     Engine, Assemble the full context a future AI document-generation feature should     ret

### Community 123 - "lifecycle_engine.py"
Cohesion: 0.33
Nodes (4): InvalidTransitionError, Exception, services/lifecycle_engine.py — shared document/record lifecycle state machine, g, Raised when a requested status change is not a legal lifecycle     transition fo

### Community 124 - "search.js"
Cohesion: 0.53
Nodes (4): closeResults(), esc(), renderResults(), runSearch()

### Community 125 - "_FakeCandidate"
Cohesion: 0.33
Nodes (3): _FakeCandidate, _FakeResponse, _FakeUsage

### Community 126 - "hello.py"
Cohesion: 0.40
Nodes (4): Send user_input to Gemini with full history and return the reply text., Print a numbered summary of the conversation so far., send_message(), show_history()

### Community 127 - "backfill_deviation_status_v2.py"
Cohesion: 0.60
Nodes (4): main(), migrate_deviation(), _now(), scripts/backfill_deviation_status_v2.py — One-time local remap of existing `qms_

### Community 128 - "migrate_investigation_v2.py"
Cohesion: 0.60
Nodes (4): _fishbone_five_why_summary(), main(), migrate_deviation(), scripts/migrate_investigation_v2.py — One-time local backfill for the architectu

### Community 129 - "docx_reader.py"
Cohesion: 0.50
Nodes (3): extract(), services/docx_reader.py — Extract text from Word (.docx) files using python-docx, Extract text from a .docx file and return (text, estimated_page_count).      Par

### Community 130 - "excel_reader.py"
Cohesion: 0.50
Nodes (3): extract(), services/excel_reader.py — Extract text from Excel (.xlsx) files using openpyxl., Extract text from a .xlsx file and return (text, sheet_count).      Each non-emp

### Community 131 - "insights.js"
Cohesion: 0.83
Nodes (3): formatWords(), loadInsights(), renderInsights()

### Community 133 - "mock_gemini"
Cohesion: 0.67
Nodes (3): mock_gemini(), fixture, Monkeypatch call_gemini/stream_gemini across all three QMS services to     retur

## Knowledge Gaps
- **57 isolated node(s):** `PharmaTheme`, `messagesEl`, `inputEl`, `sendBtn`, `clearBtn` (+52 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `markdown_to_docx()` connect `qual.py` to `DocxGenerator`, `risk.py`, `qms_change_control.py`, `qms_documents.py`, `report.py`, `qms_capa.py`, `qms_deviations.py`, `urs.py`, `review_engine.py`, `validation.py`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `require_role()` connect `require_role` to `qual.py`, `docs.py`, `projects.py`, `Flask`, `risk.py`, `qms_change_control.py`, `qms_documents.py`, `qms_common.py`, `report.py`, `qms_deviations.py`, `knowledge_base.py`, `validation.py`, `qms_capa.py`, `equipment.py`, `urs.py`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `run_review()` connect `review_engine.py` to `qual.py`, `validation.py`, `review_rules.py`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **What connects `PharmaTheme`, `messagesEl`, `inputEl` to the rest of the system?**
  _57 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `database.py` be split into smaller, more focused modules?**
  _Cohesion score 0.024057738572574178 - nodes in this community are weakly interconnected._
- **Should `qual.py` be split into smaller, more focused modules?**
  _Cohesion score 0.057911392405063294 - nodes in this community are weakly interconnected._
- **Should `test_companies.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05333333333333334 - nodes in this community are weakly interconnected._