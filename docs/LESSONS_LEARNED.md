# YUKTAV / PHARMAGPT — ENGINEERING & PRODUCT LESSONS REVIEW
## Lessons Learned, Guardrails, and Operating Rules
**Purpose:** Prevent repeated mistakes during further development, deployment, validation, and production hardening.

---

## 1. Executive Principle

**Build the system behavior first; patch screens second.**

Before changing code, define:
1. Who performs the action?
2. At what lifecycle state?
3. What data is the source of truth?
4. Who is allowed to change it?
5. What happens after the action?
6. What must be visible/auditable?
7. What existing modules could be affected?

Never solve a workflow problem merely by moving a button or dropdown to another screen.

---

## 2. Product Scope Discipline

Yuktav is being built as a practical pharmaceutical/nutraceutical operations system.

When working on one module:

- Work only on the requested module.
- Do not build future suites "because they may be useful."
- Do not create speculative architecture.
- Do not add upcoming document types.
- Do not redesign unrelated modules.
- Do not use R&D creativity to expand scope unless explicitly requested.

### Rule

> **One problem → one controlled change → verify → freeze.**

---

## 3. Document Control — Correct Business Model

For SOP creation, there are two creation routes:

### Route A — Controlled Template
Author downloads the real controlled DOCX template and prepares the SOP from scratch.

### Route B — AI-Assisted SOP Creation
Author selects the relevant equipment and the system uses the equipment Knowledge Base as reference.

The AI must not invent missing equipment information.

If information is absent:

> `[INFORMATION GAP — not found in Knowledge Base; confirm with equipment owner/manual]`

The generated result must ultimately become a real controlled document, not a Markdown download.

---

## 4. SOP Approval Responsibility

The correct responsibility model is:

```text
AUTHOR / INITIATOR
    |
    | Assigns complete chain
    |
    ├── Reviewer
    ├── Department Head
    ├── Quality Head
    └── Plant Head (Optional)
    |
    | Submit
    |
    | LOCK
    v
REVIEWER
    |
    v
DEPARTMENT HEAD
    |
    v
QUALITY HEAD
    |
    v
PLANT HEAD (if assigned)
    |
    v
APPROVED
    |
    v
EFFECTIVE
```

### Critical rule

**The Author assigns the chain.**

The Reviewer and Approvers do not assign other people.

Once submitted, the chain is locked.

This is a business/workflow rule, not merely a UI preference.

---

## 5. User Directory — Single Source of Truth

Existing tenant users already exist.

Do not create:
- duplicate users
- duplicate user tables
- manual UUID entry
- a second identity source

Use the existing tenant-scoped user directory.

The application should display names and store user IDs internally.

### Important lesson

Do not assume designation names match workflow role names.

Example:

- `Quality Reviewer`
- `Production Reviewer`
- `Production Head`
- `Quality Head`

are not equivalent to exact strings:

- `Reviewer`
- `Approver`

Exact-string filtering can silently hide legitimate users.

### Better rule

Use the existing directory as the source of truth and let the Author select the appropriate person unless a proven business rule requires filtering.

---

## 6. Shared Components Require Regression Analysis

A shared component such as:

- `user_picker.js`
- `/users/directory`
- workflow panels

can affect multiple suites.

Before modifying a shared component:

1. Find every consumer.
2. Identify current behavior in each consumer.
3. Record the existing behavior.
4. Make the smallest compatible change.
5. Run regression tests for every affected consumer.

Do not assume a change is isolated merely because the visible feature belongs to one suite.

---

## 7. Reference Existing Working Implementations

When one module already performs the desired behavior correctly:

> **Use it as the reference implementation before designing a new mechanism.**

Example:

Deviation already had a working searchable user directory.

Therefore, before inventing a Document Control-specific user-selection mechanism, compare:

- data source
- loading function
- filtering
- rendering
- search
- ID resolution

Avoid creating a second pattern when the existing one is proven.

---

## 8. UI vs Business Logic

A UI that looks correct is not proof that the workflow is correct.

For controlled workflows:

- Backend must enforce permissions.
- Lifecycle state must be checked server-side.
- Assignment locking must be server-side.
- Out-of-turn decisions must be blocked server-side.
- UI controls should reflect backend rules, not replace them.

### Example

Hiding "Assign" from an Approver is insufficient.

The backend must reject unauthorized reassignment.

---

## 9. Controlled Document Review

A Reviewer must see the actual SOP they are reviewing.

Required review experience:

```text
SOP
↓
Read-only controlled PDF
↓
UNDER REVIEW watermark
↓
Comments
↓
Request Changes / Accept
```

The PDF must represent the exact version under review.

It must not be:
- an unrelated template
- Markdown
- an editable Word document as the primary review surface
- an old version
- an Effective copy

During review/approval, the PDF carries:

> **UNDER REVIEW**

The watermark is removed when the document reaches the appropriate Effective/Released state.

---

## 10. Download/Export Lessons

If a system already has a valid DOCX export path:

**Reuse it.**

Do not create a second Markdown download mechanism for an intermediate step.

When a download bug appears:

1. Trace the actual browser request.
2. Identify endpoint.
3. Check response MIME type.
4. Check Content-Disposition.
5. Check actual file bytes.
6. Confirm the browser receives DOCX, not merely a renamed file.

Do not declare success because the server-side function exists.

---

## 11. Production Debugging — Follow the Evidence

A major lesson from the upload failure:

A button displaying:

> `Upload failed: Not found`

does not necessarily mean the upload endpoint is wrong.

The actual evidence showed:

```text
POST /qms/documents
    → 201

GET /qms/documents/1
    → 200

GET /qms/documents/1/versions/current
    → 200

Render/Gunicorn restart

GET /qms/documents/1
    → 404
```

Therefore the upload failure was downstream of document persistence.

### Rule

> **Trace the entire request chain before changing the failing endpoint.**

Never patch the visible symptom before proving the root cause.

---

## 12. Render Persistent Storage

SQLite/local filesystem persistence on Render is dangerous unless explicitly configured for persistent storage.

The application configuration documented the hazard:

- `DB_PATH` fallback can point to the package filesystem.
- `UPLOAD_FOLDER` can also point to an ephemeral filesystem.
- A Render restart/redeploy can therefore make records/files disappear.

### Rule

For any production deployment using filesystem-backed persistence:

Verify the LIVE service, not only `render.yaml`:

- `DB_PATH`
- `UPLOAD_FOLDER`
- attached Render Disk
- mount path
- actual runtime paths
- persistence after restart

A configuration file is not proof that the live service has the configuration.

---

## 13. Environment Separation

Having Staging and Production can be valid.

The mistake is allowing them to become confusing or competing sources of truth.

Maintain an explicit map:

```text
PRODUCTION
Render Production
    ↓
Supabase Production

STAGING
Render Staging
    ↓
Supabase Staging
```

Document:

- production URL
- staging URL
- production Supabase project
- staging Supabase project
- environment variables
- database/storage ownership

Never troubleshoot environment differences without first confirming which environment is actually being used.

---

## 14. Supabase / SQLite Architecture

Different domains may currently have different persistence paths.

That is architectural debt and must be acknowledged.

Do not falsely assume that because some QMS domains use Postgres dual-write, Document Control does too.

Evidence showed:

- Document Control documents were SQLite-backed.
- `QMS_BACKEND` did not include documents.
- Documents had no Postgres dual-write path.
- A separate deviation RLS error was unrelated to Document Control.

### Rule

Before claiming Postgres/RLS is the cause:

> Prove that the affected domain actually writes to Postgres.

Do not generalize architecture from one module to another.

---

## 15. Production vs Code Investigation

Claude does not necessarily have access to:

- Render dashboard
- Supabase dashboard
- live credentials
- authenticated production sessions

Do not ask Claude to verify things it cannot access.

Instead, collect evidence:

- Render logs
- Environment screen
- Network request
- `/auth/me`
- `/users/directory`
- actual response status/body
- Git history

Then give the evidence to Claude.

### Never provide secrets unnecessarily.

URLs, company IDs, status codes, and non-secret API responses are usually sufficient for diagnosis.

---

## 16. Live Testing Is Essential

Passing tests is not the same as proving the production workflow.

Use three layers:

### Layer 1 — Unit/automated tests
Prove individual logic.

### Layer 2 — Local/integration tests
Prove connected workflow behavior.

### Layer 3 — Real tenant/live smoke test
Prove the actual user experience.

For Document Control, the real journey should be tested end-to-end:

```text
Create SOP
↓
Controlled Template OR AI-assisted generation
↓
Final Author Version upload
↓
Author self-check
↓
Assign complete chain
↓
Submit
↓
Reviewer sees PDF
↓
UNDER REVIEW watermark
↓
Reviewer decision
↓
Department Head
↓
Quality Head
↓
Plant Head (optional)
↓
Effective
↓
Audit trail
```

---

## 17. Never Confuse "Implemented" With "Deployed"

A Git push does not prove production is updated.

A successful local test does not prove Render is running that commit.

A Render deployment event does not prove the browser is serving the newest JavaScript.

For every production change verify:

1. Commit SHA.
2. Render deployment status.
3. Running version/commit if available.
4. Browser/network behavior.
5. Actual user workflow.

---

## 18. Browser Cache Can Hide Fixes

If JavaScript changed but production still behaves as before:

Check:

- Network → JS file
- response/source
- cache status
- hard refresh
- deployed commit
- actual script version/cache-busting

Do not immediately rewrite working code because an old browser bundle may still be loaded.

---

## 19. Do Not Bypass Safety Gates

If Submit for Review is blocked because:

- Final Author Version missing
- Self-check incomplete
- Approval chain incomplete

that may be correct.

Never remove a control simply because it blocks testing.

Fix the prerequisite that is genuinely broken.

---

## 20. Use Existing Architecture Before Creating New Architecture

Before adding a table/service/module:

Ask:

1. Does this already exist?
2. Can it be reused?
3. Which module already solves this?
4. Is the new abstraction actually necessary?
5. Will it create a second source of truth?

The Approver Pool lesson is particularly important:

A separate SQLite approval pool duplicated information already available in the tenant user directory.

That created unnecessary complexity.

---

## 21. Avoid "Future-Proofing" During Current Work

Do not build:

- future suites
- speculative workflows
- unused document types
- generic frameworks without a current requirement
- architecture for hypothetical customers

A simple system that works is better than a sophisticated system that creates ambiguity.

---

## 22. Git Discipline

Before every commit:

1. Check current branch.
2. Check `git status`.
3. Inspect changed files.
4. Verify unrelated changes are not included.
5. Run tests.
6. Commit only intended changes.
7. Confirm commit SHA.
8. Push only after approval.

Never assume the working tree contains only your current task.

---

## 23. Change Approval Protocol

For significant work:

### Claude must:
- investigate
- report root cause
- propose smallest fix
- test
- stop

### We review:
- business correctness
- architecture impact
- regression risk
- scope

### Then:
- approve
- commit
- deploy

Do not let an implementation agent silently expand scope.

---

## 24. R&D Mindset vs Production Mindset

For production fixes, Claude should not "explore" endlessly.

Use:

> **Diagnose → propose → implement → test → report → stop.**

Not:

> Diagnose → redesign → add abstraction → improve unrelated module → future-proof → deploy.

---

## 25. The Most Important Lesson

When something looks wrong:

### Ask five questions first

1. **What is the intended business behavior?**
2. **Who owns the action?**
3. **What is the source of truth?**
4. **Where is the state stored?**
5. **What exact evidence proves the failure?**

Only then change code.

---

## 26. Current Project Direction

The project is NOT being abandoned or restarted.

The current strategy is:

```text
Finish Document Control
        ↓
Freeze the module
        ↓
Complete regression testing
        ↓
Deploy the complete system to Oracle
        ↓
Establish one clear production architecture
        ↓
Run systematic real-world testing
        ↓
Fix proven defects at the correct architectural level
        ↓
Only then expand functionality
```

Do not repeatedly rebuild the same workflow while testing it.

---

## 27. Final Operating Contract for Future Development

Before starting any task, Claude/agent must answer internally:

### SCOPE
What exact module am I changing?

### OWNER
Who performs this action?

### STATE
At what lifecycle state is it allowed?

### SOURCE
Where does the data already live?

### AUTHORITY
Who is allowed to change it?

### STORAGE
Where is the authoritative record stored?

### REGRESSION
Which existing modules consume the code I am changing?

### EVIDENCE
What proves the defect exists?

### MINIMALITY
What is the smallest change that solves it?

### VERIFICATION
How will I prove it works end-to-end?

### STOP CONDITION
When the requested behavior works, stop.

---

## 28. Golden Rules

1. **Do not create data that already exists.**
2. **Do not create a second source of truth without a documented reason.**
3. **Do not solve backend problems with UI patches.**
4. **Do not solve workflow problems by moving controls between screens.**
5. **Do not let the wrong role perform the right action.**
6. **Do not trust exact designation strings unless verified against real data.**
7. **Do not assume staging and production are configured identically.**
8. **Do not assume `render.yaml` equals live Render configuration.**
9. **Do not assume tests equal production verification.**
10. **Do not change shared components without checking every consumer.**
11. **Do not expand scope during a production fix.**
12. **Do not bypass safety/control gates.**
13. **Trace the actual request before changing the endpoint.**
14. **Use existing working implementations as references.**
15. **One source of truth wherever practical.**
16. **Author assigns; Reviewer reviews; Approver approves.**
17. **Lock controlled assignments after submission.**
18. **Controlled documents must visibly distinguish draft/review from effective copies.**
19. **Prove the root cause before proposing the fix.**
20. **When the requirement is complete, stop.**

---

## 29. Decision Standard

Every proposed change should pass this test:

> **Does this make the system simpler, more controlled, more traceable, and more reliable?**

If not, stop and reassess.

---

**Status:** Working lessons learned  
**Use:** Internal engineering/product review before future Yuktav/PharmaGPT changes  
**Priority:** Prevent recurrence of architectural drift, duplicated data sources, incorrect workflow ownership, and symptom-level fixes.
