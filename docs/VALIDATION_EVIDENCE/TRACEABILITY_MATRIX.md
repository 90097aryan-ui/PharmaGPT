# Validation Evidence — Traceability Matrix

**Full detail:** `docs/PHASE_F_FINDING_TRACEABILITY.md`. This is the condensed index required by the Phase F evidence package.

| Finding | Source | Severity | Phase F Status |
|---|---|---|---|
| A1/C1 — Company Admin / Assume Company Context non-functional | Enterprise Acceptance Test + Phase E | Critical | **NOT VERIFIED** — operational (live DB grants), outside this session's reach |
| A2 — User Management fails for company_admin | Enterprise Acceptance Test | Critical | **NOT VERIFIED** — same root cause as A1; application code confirmed correct |
| A3 — Assume Company Context fails | Enterprise Acceptance Test | Critical | **NOT VERIFIED** — same root cause as A1 |
| A4 — Raw exception text leaks to client | Enterprise Acceptance Test | Low/Medium | Open, out of Phase F scope |
| A5 — 403-wording inconsistency | Enterprise Acceptance Test | Cosmetic | Open, out of Phase F scope |
| A6 — No break-glass audit-log viewer | Enterprise Acceptance Test | Medium | Open, explicitly out of scope (new-feature prohibition) |
| C2 — No IQ→OQ→PQ execution sequencing | Phase E | Critical | **FIXED, verified by automated test** |
| C3 — Report approvable without linked qualification's PQ complete | Phase E | Critical | **FIXED, verified by automated test** |
| C4 — PUT/DELETE unaudited | Phase E | Critical | **FIXED, verified by automated test (Equipment) + code read (all other domains)** |
| C5 — Audit schema missing old/new/company_id | Phase E | Critical | **FIXED, verified** |
| C6 — Identity spoofable in several endpoints | Phase E | Critical | **FIXED, verified by automated test (comments) + code read (rest)** |
| C7 — 3 endpoints missing role guards | Phase E | Critical | **FIXED, verified by automated test (all 3)** |
| H7 — CAPA/Change Control have no lifecycle guard | Phase E | High | **Partially fixed** (terminal-state immutability, verified) — full transition graph NOT built, disclosed |
| H1, H2, H3, H4, H5, H6, M2 | Phase E | High/Medium | Open, explicitly out of Phase F scope — see `docs/PHASE_F_FINDING_TRACEABILITY.md` §D |

**Rule applied throughout Phase F, per the brief's explicit instruction:** nothing above is marked "Fixed" without a citation to source code, a passing automated test, or a direct runtime/schema check. Where only a code read (not a dedicated test) backs a fix, that is stated explicitly rather than implied.
