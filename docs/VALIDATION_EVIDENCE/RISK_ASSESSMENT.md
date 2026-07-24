# Validation Evidence — Risk Assessment

Risk view of what remains open after Phase F, ranked by consequence to a GxP release decision.

| Risk | Likelihood it matters | Impact if it does | Mitigation status |
|---|---|---|---|
| Company Administration / Assume Company Context still non-functional live (A1/C1) | **Certain** — confirmed root cause (Postgres GRANTs), not a maybe | High — Super Admin's only sanctioned support path is unusable; Company Admins can't manage their own users | **Unmitigated by this session** — requires a live database action outside this environment's reach. This is the single largest blocker to GO. |
| CAPA/Change Control still have no full transition-graph guard (H7 residual) | Medium — requires a user to deliberately post an out-of-sequence action name | Medium — a GAMP5 auditor could flag it, but the terminal-state (Closed) protection now in place catches the most damaging case (post-closure edits) | Partially mitigated — terminal immutability shipped and tested; full graph not built, disclosed |
| Postgres/Users/Companies audit writes unverified live | High (given A1/C1) that they are currently failing silently (best-effort, wrapped in try/except) | Low-Medium — an admin action would go unaudited until A1 is fixed, but the primary action itself still succeeds/fails correctly | Code-level fix shipped; live behavior unverified, disclosed |
| DQ/FAT/SAT traceability gap, dead prompt modules (H1/H2) | Certain (unchanged) | Medium — content-quality and traceability gap, not a functional failure | Explicitly out of Phase F scope, unaddressed |
| Performance items (H3-H5) | Certain (unchanged) | Medium under load, none at current pilot scale | Explicitly out of Phase F scope, unaddressed |
| SQLite→Postgres cutover soak/spot-check (H6) | Certain (unchanged) | High if/when multi-tenant production load increases | Operational, outside Phase F's code-level scope |
| `_score_cache` cross-tenant statistic leak (new finding, WP5) | Certain if multiple companies share a server process | Low — a single aggregate float, not identifying data | Disclosed, not fixed (see `docs/MULTI_TENANT_SECURITY_REPORT.md` §7) |

**Net read:** Phase F closed every Critical finding this session could reach with source-code changes (C2-C7), all with real evidence. The one Critical item it could **not** close (A1/C1) is explicitly an operational/database action, not a code gap — and it remains the deciding factor for the final GO/NO-GO call.
