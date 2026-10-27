/* End-to-end browser scenarios for the Validation approval workflow.
 *
 * Runs inside a real (headless) browser against the isolated e2e server. Every
 * approval action is performed THROUGH THE REAL UI COMPONENT (validation_approval_ui.js
 * + esignature_dialog.js): buttons are located by their visible text and clicked, the
 * e-signature dialog is filled in and submitted. Record setup (create/self-check/upload)
 * and ground-truth reads use the real HTTP API / the server's /e2e/state endpoint.
 * The result is written as JSON into <pre id="result"> for the pytest wrapper.
 */
(function () {
  "use strict";

  const results = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const host = () => document.getElementById("host");

  function check(name, ok, detail) {
    results.push({ name, ok: !!ok, detail: ok ? "" : String(detail === undefined ? "" : detail) });
    return !!ok;
  }

  async function waitFor(fn, label, tries = 400) {
    for (let i = 0; i < tries; i++) {
      const v = await fn();
      if (v) return v;
      await sleep(25);
    }
    throw new Error("timed out waiting for: " + label);
  }

  async function api(method, url, body, form) {
    const opts = { method, credentials: "same-origin" };
    if (form) opts.body = form;
    else if (body !== undefined) { opts.headers = { "Content-Type": "application/json" }; opts.body = JSON.stringify(body); }
    const r = await fetch(url, opts);
    let json = null;
    try { json = await r.json(); } catch (e) { /* non-JSON */ }
    return { status: r.status, json };
  }

  async function persona(name) { await fetch("/e2e/persona?name=" + name, { credentials: "same-origin" }); }
  async function state(kind, id, qid) {
    return (await api("GET", `/e2e/state?kind=${kind}&id=${id}&qid=${qid || 0}`)).json;
  }

  /* ── UI helpers ───────────────────────────────────────────────────────── */
  async function openPanel(base, id) {
    host().innerHTML = "";
    const box = document.createElement("div");
    host().appendChild(box);
    window.ValidationApproval.render(box, { base, id });
    await waitFor(() => box.querySelector("table.va-table") || box.querySelector(".va-error"), "approval panel");
    return box;
  }
  const rows = (box) => Array.from(box.querySelectorAll("table.va-table tbody tr"));
  const completed = (box) => box.querySelectorAll(".va-chip.va-completed").length;
  const buttonTexts = (box) => Array.from(box.querySelectorAll("button.va-btn")).map((b) => b.textContent.trim());
  function button(box, text) {
    return Array.from(box.querySelectorAll("button.va-btn")).find((b) => b.textContent.trim() === text);
  }

  /* Fill the e-signature dialog the way a user would, then submit. Returns the dialog error text ("" on success). */
  async function sign(password, reason) {
    await waitFor(() => document.getElementById("esign-modal") && document.getElementById("esign-modal").classList.contains("open"), "e-sign dialog");
    document.getElementById("esign-password").value = password;
    document.getElementById("esign-reason").value = reason;
    document.getElementById("esign-form").requestSubmit();
    await waitFor(() => {
      const modal = document.getElementById("esign-modal");
      const err = document.getElementById("esign-error");
      const closed = !modal.classList.contains("open");
      const failed = err && err.style.display !== "none" && err.textContent.trim();
      return closed || failed;
    }, "e-sign result");
    const err = document.getElementById("esign-error");
    const text = (err && err.style.display !== "none") ? err.textContent.trim() : "";
    if (text) document.getElementById("esign-modal-cancel").click();
    await sleep(60);
    return text;
  }

  /* Click a UI action and complete the e-signature. Returns {error}. */
  async function act(box, label, { password, reason } = {}) {
    const b = button(box, label);
    if (!b) throw new Error(`no "${label}" button; have: ${buttonTexts(box).join(" | ")}`);
    b.click();
    const error = await sign(password || window.E2E_PASSWORD, reason || `e2e: ${label}`);
    return { error };
  }

  async function reopen(base, id) { return openPanel(base, id); }

  /* ── setup helpers ────────────────────────────────────────────────────── */
  const KINDS = {
    URS: async () => {
      const r = await api("POST", "/urs/", { title: "E2E URS", equipment_name: "E2E Autoclave" });
      return { id: r.json.id, base: "/urs", ledger: "URS", qid: 0 };
    },
    DQ: async () => {
      const r = await api("POST", "/qms/documents", { title: "E2E DQ", doc_type: "DQ", content: "# DQ\nbody" });
      return { id: r.json.id, base: "/qms/documents", ledger: "DQ", qid: 0 };
    },
    QUAL: async (type) => {
      const q = await api("POST", "/qual/", { title: "E2E Qualification", equipment_name: "E2E Autoclave" });
      const ids = {};
      for (const t of ["IQ", "OQ", "PQ"]) {
        ids[t] = (await api("POST", `/qual/${q.json.id}/protocols`, { protocol_type: t })).json.id;
      }
      return { id: ids[type], base: `/qual/${q.json.id}/protocols`, ledger: type, qid: q.json.id, siblings: ids };
    },
  };

  async function prepareDraft(rec) {          // Document Control safeguards for DQ
    if (rec.ledger !== "DQ") return;
    await api("POST", `/qms/documents/${rec.id}/self-check`);
    const fd = new FormData();
    fd.append("file", new Blob(["final author version"], { type: "text/plain" }), "final.txt");
    const up = await api("POST", `/qms/documents/${rec.id}/versions/upload`, undefined, fd);
    if (up.status !== 201) throw new Error("final version upload failed: " + up.status);
  }

  const CHAIN = [
    ["reviewed_by", "Sign as Reviewed By", "technical_review"],
    ["engineering_manager", "Sign as Engineering", "technical_review"],
    ["production_manager", "Sign as Production", "qa_review"],
    ["qa_manager", "Sign as Quality Assurance", "validation_review"],
    ["validation_manager", "Sign as Validation", "final_approval"],
    ["final_approval", "Sign as Final Approval", "approved"],
  ];

  async function submitViaUi(rec, tag) {
    await persona("prepared_by");
    let box = await openPanel(rec.base, rec.id);
    check(`${tag}: Prepared By line is the first, awaiting signature`, rows(box)[0].textContent.includes("Validation Engineer") && rows(box)[0].textContent.includes("Awaiting signature"));
    // wrong password is refused by the UI flow and nothing changes
    let r = await act(box, "Submit for Review", { password: "wrong-password" });
    check(`${tag}: wrong e-signature password is refused`, /password/i.test(r.error), r.error);
    check(`${tag}: ...and the record is still Draft`, (await state(rec.ledger, rec.id, rec.qid)).status === "draft");
    // correct password submits
    box = await reopen(rec.base, rec.id);
    r = await act(box, "Submit for Review");
    check(`${tag}: author submits through the UI`, r.error === "", r.error);
    box = await reopen(rec.base, rec.id);
    check(`${tag}: Prepared By shown as completed with name, designation and e-signature`, completed(box) === 1 && /E2E prepared_by/.test(rows(box)[0].textContent) && /Created/.test(rows(box)[0].textContent));
    check(`${tag}: now Under Review`, (await state(rec.ledger, rec.id, rec.qid)).status === "under_review");
  }

  async function signChain(rec, tag, { upTo } = {}) {
    for (const [who, label, expected] of CHAIN) {
      await persona(who);
      const box = await reopen(rec.base, rec.id);
      const before = completed(box);
      check(`${tag}: "${label}" is offered to ${who}`, !!button(box, label), buttonTexts(box).join(" | "));
      const r = await act(box, label);
      check(`${tag}: ${who} signs`, r.error === "", r.error);
      const after = completed(await reopen(rec.base, rec.id));
      check(`${tag}: signed count ${before} -> ${before + 1}`, after === before + 1, `${before} -> ${after}`);
      const st = (await state(rec.ledger, rec.id, rec.qid)).status;
      check(`${tag}: status after ${who} is ${expected}`, st === expected, st);
      if (who === "engineering_manager") {
        // parallel stage: the Production line must still be open
        const b2 = await reopen(rec.base, rec.id);
        check(`${tag}: Production still awaiting after Engineering signs`, !!button(b2, "Sign as Production"));
      }
      if (upTo && who === upTo) return;
    }
  }

  async function runDocument(name, makeRec) {
    const tag = name;
    await persona("prepared_by");            // the author creates the record (only the author may submit it)
    const rec = await makeRec();
    await prepareDraft(rec);

    // ── authorship: another initiator with Submit permission is refused in the UI ──
    await persona("other_initiator");
    let box = await openPanel(rec.base, rec.id);
    let r = await act(box, "Submit for Review");
    check(`${tag}: a non-author cannot submit someone else's document`, /author/i.test(r.error), r.error);
    check(`${tag}: ...record still Draft`, (await state(rec.ledger, rec.id, rec.qid)).status === "draft");

    await submitViaUi(rec, tag);

    // ── department authorization: a QC approver cannot sign the Reviewed By line ──
    await persona("qc_manager");
    box = await openPanel(rec.base, rec.id);
    r = await act(box, "Sign as Reviewed By");
    check(`${tag}: an unauthorized department cannot sign`, /requires|role|permission/i.test(r.error), r.error);
    check(`${tag}: ...still Under Review with 1 signature`, completed(await reopen(rec.base, rec.id)) === 1);

    // ── rejection with a reason, then resubmission ──
    await persona("reviewed_by");
    box = await openPanel(rec.base, rec.id);
    r = await act(box, "Reject", { reason: "e2e: scope incomplete" });
    check(`${tag}: reviewer rejects through the UI`, r.error === "", r.error);
    let st = await state(rec.ledger, rec.id, rec.qid);
    check(`${tag}: rejected -> Draft, history kept, current cycle empty`, st.status === "draft" && st.ledger_current === 0 && st.ledger_all === 1, JSON.stringify(st));
    await persona("prepared_by");
    await prepareDraft(rec);                      // DQ: the forked draft needs its own Self-Check + final version
    await submitViaUi(rec, tag + " (resubmission)");

    // ── full chain ──
    await signChain(rec, tag);
    st = await state(rec.ledger, rec.id, rec.qid);
    check(`${tag}: Approved with seven current sign-offs`, st.status === "approved" && st.ledger_current === 7, JSON.stringify(st));
    check(`${tag}: NOT published to the Knowledge Base before Effective`, st.kb_published === false);

    // ── revision (not for DQ: its version cannot be un-approved) ──
    await persona("final_approval");
    box = await reopen(rec.base, rec.id);
    const revBefore = st.revision;
    r = await act(box, "Send back for revision", { reason: "e2e: revise after approval" });
    st = await state(rec.ledger, rec.id, rec.qid);
    if (rec.ledger === "DQ") {
      check(`DQ: cannot be sent back from Approved (Document Control versions are immutable)`, r.error !== "" && st.status === "approved", r.error + " / " + st.status);
    } else {
      check(`${tag}: revision after approval -> Draft with a new revision`, r.error === "" && st.status === "draft" && st.revision !== revBefore, JSON.stringify(st) + r.error);
      await persona("prepared_by");
      await submitViaUi(rec, tag + " (revision)");
      await signChain(rec, tag + " (revision)");
    }

    // ── Effective ──
    await persona("admin");
    if (rec.ledger === "DQ") {
      await persona("final_approval");
      box = await reopen(rec.base, rec.id);
      r = await act(box, "Make Effective");
      check(`DQ: Make Effective is blocked until the training gate clears`, /training/i.test(r.error), r.error);
      await api("POST", `/e2e/training?id=${rec.id}`);
    }
    await persona("final_approval");
    box = await reopen(rec.base, rec.id);
    r = await act(box, "Make Effective");
    check(`${tag}: Make Effective through the UI`, r.error === "", r.error);
    st = await state(rec.ledger, rec.id, rec.qid);
    box = await reopen(rec.base, rec.id);
    check(`${tag}: final status Effective, seven completed lines`, st.status === "effective" && completed(box) === 7, JSON.stringify(st));
    check(`${tag}: published to the Knowledge Base at Effective`, st.kb_published === true);
    return rec;
  }

  async function main() {
    try {
      await runDocument("URS", () => KINDS.URS());
      await runDocument("DQ", () => KINDS.DQ());

      // Protocols: IQ first; OQ and PQ must be unaffected until they are approved themselves.
      let siblings = null, qid = 0;
      const iq = await runDocument("IQ", async () => { const r = await KINDS.QUAL("IQ"); siblings = r.siblings; qid = r.qid; return r; });
      await persona("prepared_by");
      for (const t of ["OQ", "PQ"]) {
        const base = `/qual/${qid}/protocols`;
        const st = await state(t, siblings[t], qid);
        check(`${t}: independent of IQ — still Draft with no sign-offs after IQ is Effective`, st.status === "draft" && st.ledger_all === 0, JSON.stringify(st));
        const box = await openPanel(base, siblings[t]);
        check(`${t}: its own approval page offers Submit for Review`, !!button(box, "Submit for Review") && completed(box) === 0);
        check(`${t}: not published to the Knowledge Base`, st.kb_published === false);
      }
      const parentAfterIq = (await state("IQ", siblings.IQ, qid)).parent_status;
      check("parent Qualification is not approved just because IQ is Effective", parentAfterIq !== "approved" && parentAfterIq !== "effective", parentAfterIq);

      // OQ goes the whole way on its own; PQ stays Draft.
      const oqRec = { id: siblings.OQ, base: `/qual/${qid}/protocols`, ledger: "OQ", qid };
      await submitViaUi(oqRec, "OQ");
      await signChain(oqRec, "OQ");
      await persona("final_approval");
      let box = await reopen(oqRec.base, oqRec.id);
      const r = await act(box, "Make Effective");
      check("OQ: Make Effective through the UI", r.error === "", r.error);
      const pq = await state("PQ", siblings.PQ, qid);
      check("PQ: still Draft after IQ and OQ are Effective", pq.status === "draft" && pq.ledger_all === 0, JSON.stringify(pq));
      check("parent stays under review until all three protocols are Effective", pq.parent_status === "under_review", pq.parent_status);

      // PQ last: parent becomes Effective only now.
      const pqRec = { id: siblings.PQ, base: `/qual/${qid}/protocols`, ledger: "PQ", qid };
      await submitViaUi(pqRec, "PQ");
      await signChain(pqRec, "PQ");
      await persona("final_approval");
      box = await reopen(pqRec.base, pqRec.id);
      await act(box, "Make Effective");
      const fin = await state("PQ", siblings.PQ, qid);
      check("PQ: Effective", fin.status === "effective" && fin.kb_published === true, JSON.stringify(fin));
      check("parent Qualification is Effective only after all three protocols are", fin.parent_status === "effective", fin.parent_status);
    } catch (e) {
      check("scenario aborted", false, (e && e.stack) || String(e));
    }
    const failed = results.filter((x) => !x.ok);
    document.getElementById("result").textContent = JSON.stringify({ done: true, total: results.length, failed: failed.length, results });
  }

  window.addEventListener("load", main);
})();
