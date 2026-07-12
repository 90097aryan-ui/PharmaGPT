-- Migration 0009 (down): revoke the grants added in 0009_phase3_grants_up.sql

revoke select, insert
    on audit_trail
    from authenticated;

revoke select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments
    from authenticated;

revoke select, insert, update, delete
    on projects, project_members,
       documents, document_versions, document_categories, tags, document_tags,
       equipment, equipment_links,
       deviations, capas, change_controls, risk_assessments, audit_trail
    from service_role;
