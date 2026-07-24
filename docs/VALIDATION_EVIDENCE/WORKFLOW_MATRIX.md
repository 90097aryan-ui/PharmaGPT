# Validation Evidence — Workflow Enforcement Matrix

**Full detail:** `docs/WORKFLOW_VALIDATION_REPORT.md`.

| Requirement | Mechanism | Verified by |
|---|---|---|
| OQ cannot begin before IQ complete | `routes/qual.py::execute_test_case` blocks (409) unless a sibling IQ protocol is `completed`/`completed_with_deviations` | Automated test (`test_oq_test_execution_blocked_before_iq_complete`, `::_allowed_once_iq_complete`) |
| PQ cannot begin before OQ complete | Same mechanism, `_PROTOCOL_PREREQUISITE = {"PQ": "OQ"}` | Same code path as above; no dedicated PQ test added — code-read verified |
| Validation Report cannot be approved before PQ complete | `routes/report.py::add_approval` blocks (409) the "approved" transition when a linked qualification's `pq_status` isn't complete | Automated tests (3, covering blocked / allowed / no-link-is-unaffected cases) |
| Effective impossible before Approval | Pre-existing `lifecycle_engine.validate_transition()` / `urs_lifecycle` on every wired module | Re-verified by direct code read of every transition map; unchanged, no regression |
| Archived/terminal records immutable | New terminal-state guard on PUT + approval endpoints across 8 modules (Document, URS, Qualification, Validation Report, Risk, Deviation, CAPA, Change Control) | Automated test for CAPA; code-read for the other 7 |
| Rejected cannot bypass review | Pre-existing `Rejected → Draft/Open` mapping on every module, re-verified unchanged | Code read of every `_STATUS_MAP` |

**Explicitly NOT built in Phase F (disclosed, not silently passed):** a full arbitrary-transition-prevention state machine for CAPA and Change Control (H7's broader scope) — only the terminal-state immutability slice was implemented, since building a full 13-status transition graph from scratch risked inventing unverified business rules, which the Phase F brief prohibits ("do not add features").
