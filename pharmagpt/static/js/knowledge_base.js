// knowledge_base.js — Knowledge Base panel for PharmaGPT v0.7
// Global document library: permanent storage, independent of projects.

(function () {
  'use strict';

  const KB_FOLDERS = [
    'SOP', 'Validation', 'Qualification', 'Protocols',
    'Reports', 'Regulations', 'Vendor Documents', 'Others',
  ];

  const FILE_ICONS = { pdf: '<span class=\'icon\' data-lucide=\'book\'></span>', docx: '<span class=\'icon\' data-lucide=\'book\'></span>', xlsx: '<span class=\'icon\' data-lucide=\'book\'></span>', txt: '<span class=\'icon\' data-lucide=\'file-text\'></span>' };

  const FOLDER_ICONS = {
    SOP: '<span class=\'icon\' data-lucide=\'clipboard-list\'></span>', Validation: '<span class=\'icon\' data-lucide=\'check-circle-2\'></span>', Qualification: '<span class=\'icon\' data-lucide=\'microscope\'></span>',
    Protocols: '<span class=\'icon\' data-lucide=\'test-tube-2\'></span>', Reports: '<span class=\'icon\' data-lucide=\'bar-chart-3\'></span>', Regulations: '<span class=\'icon\' data-lucide=\'scale\'></span>',
    'Vendor Documents': '<span class=\'icon\' data-lucide=\'factory\'></span>', Others: '<span class=\'icon\' data-lucide=\'folder\'></span>',
  };

  const state = {
    activeFolder: null,   // null = show All
    searchTitle: '',
    searchTag: '',
    searchFileType: '',
    searchKeyword: '',
    documents: [],
    selectedDoc: null,
    folderCounts: {},
  };

  // Statuses considered "still working" — polled until terminal.
  const EXTRACTION_IN_PROGRESS_STATUSES = new Set(['pending', 'processing']);
  const EXTRACTION_FAILED_STATUSES = new Set(['failed', 'error', 'partial']);
  const extractionPollTimers = new Map(); // kbId -> interval handle

  // ── Load & render ──────────────────────────────────────────────────────────

  async function loadKBDocuments() {
    const params = new URLSearchParams();
    if (state.activeFolder)   params.set('folder',    state.activeFolder);
    if (state.searchTitle)    params.set('title',     state.searchTitle);
    if (state.searchTag)      params.set('tag',       state.searchTag);
    if (state.searchFileType) params.set('file_type', state.searchFileType);
    if (state.searchKeyword)  params.set('keyword',   state.searchKeyword);

    try {
      const resp = await fetch(`/kb/documents?${params}`);
      if (!resp.ok) return;
      state.documents = await resp.json();
    } catch { return; }

    renderKBList();
    await refreshFolderCounts();
    renderFolderSidebar();
  }

  async function refreshFolderCounts() {
    try {
      const resp = await fetch('/kb/folders/counts');
      if (resp.ok) state.folderCounts = await resp.json();
    } catch { /* ignore */ }
  }

  function renderFolderSidebar() {
    const el = document.getElementById('kb-folder-list');
    if (!el) return;

    const total = Object.values(state.folderCounts).reduce((s, n) => s + n, 0);
    const isAll = state.activeFolder === null;

    let html = `
      <div class="kb-folder-item ${isAll ? 'active' : ''}" onclick="kbSetFolder(null)">
        <span class="kb-folder-icon"><span class=\'icon\' data-lucide=\'book-open\'></span></span>
        <span class="kb-folder-name">All Documents</span>
        <span class="kb-folder-count">${total || ''}</span>
      </div>`;

    KB_FOLDERS.forEach(folder => {
      const count  = state.folderCounts[folder] || 0;
      const active = state.activeFolder === folder;
      html += `
        <div class="kb-folder-item ${active ? 'active' : ''}" onclick="kbSetFolder('${folder}')">
          <span class="kb-folder-icon">${FOLDER_ICONS[folder] || '<span class=\'icon\' data-lucide=\'folder\'></span>'}</span>
          <span class="kb-folder-name">${folder}</span>
          ${count ? `<span class="kb-folder-count">${count}</span>` : ''}
        </div>`;
    });

    el.innerHTML = html;
  }

  function renderKBList() {
    const list   = document.getElementById('kb-doc-list');
    const empty  = document.getElementById('kb-doc-empty');
    const countEl = document.getElementById('kb-doc-count');
    if (!list) return;

    const docs = state.documents;
    if (countEl) countEl.textContent = docs.length
      ? `${docs.length} document${docs.length !== 1 ? 's' : ''}`
      : '';

    if (!docs.length) {
      list.innerHTML = '';
      if (empty) empty.style.display = 'flex';
      return;
    }
    if (empty) empty.style.display = 'none';

    list.innerHTML = docs.map(doc => {
      const tagsHtml = buildTagsHtml(doc.tags);
      const selected = state.selectedDoc && state.selectedDoc.id === doc.id;
      return `
        <div class="kb-doc-row ${selected ? 'selected' : ''}" onclick="kbSelectDoc(${doc.id})">
          <div class="kb-doc-type-icon">${FILE_ICONS[doc.file_type] || '<span class=\'icon\' data-lucide=\'file-text\'></span>'}</div>
          <div class="kb-doc-info">
            <div class="kb-doc-name">${escHtml(doc.title)}</div>
            <div class="kb-doc-meta-row">
              <span class="kb-folder-pill">${FOLDER_ICONS[doc.folder] || '<span class=\'icon\' data-lucide=\'folder\'></span>'} ${doc.folder}</span>
              <span class="kb-version-pill">v${doc.doc_version || '1.0'}</span>
              <span class="kb-type-pill">${doc.file_type.toUpperCase()}</span>
              ${doc.effective_date ? `<span class="kb-date-pill"><span class=\'icon\' data-lucide=\'calendar\'></span> Eff: ${doc.effective_date}</span>` : ''}
              ${doc.review_date ? `<span class="kb-date-pill kb-review-pill"><span class=\'icon\' data-lucide=\'repeat\'></span> Rev: ${doc.review_date}</span>` : ''}
              ${renderExtractionBadge(doc)}
            </div>
            ${tagsHtml ? `<div class="kb-tags-row">${tagsHtml}</div>` : ''}
          </div>
          <div class="kb-doc-row-actions">
 <button class="kb-row-btn"onclick="event.stopPropagation();kbViewDoc(${doc.id})"title="View"></button>
 <button class="kb-row-btn kb-row-btn-del"onclick="event.stopPropagation();kbDeleteDoc(${doc.id})"title="Delete"></button>
          </div>
        </div>`;
    }).join('');

    docs.forEach(doc => {
      if (EXTRACTION_IN_PROGRESS_STATUSES.has(doc.extraction_status)) {
        kbPollExtraction(doc.id);
      }
    });
  }

  function renderExtractionBadge(doc) {
    const status = doc.extraction_status;
    if (!status || status === 'ok') return '';

    if (EXTRACTION_IN_PROGRESS_STATUSES.has(status)) {
      const total = doc.extraction_progress_total || 0;
      const current = doc.extraction_progress_current || 0;
      const label = total ? `Extracting page ${current}/${total}…` : 'Extracting…';
      return `<span class="kb-date-pill kb-ext-badge-pending">${label}</span>`;
    }
    if (status === 'empty') {
      return `<span class="kb-date-pill kb-ext-badge-empty">No text found</span>`;
    }
    if (status === 'partial') {
      return `<span class="kb-date-pill kb-ext-badge-partial">Partial (${doc.quality_score ?? 0}%)</span>`;
    }
    return `<span class="kb-date-pill kb-ext-badge-failed">Extraction failed</span>`;
  }

  // ── Extraction progress polling ─────────────────────────────────────────────

  function kbPollExtraction(id) {
    if (extractionPollTimers.has(id)) return;

    const timer = setInterval(async () => {
      try {
        const resp = await fetch(`/kb/documents/${id}/status`);
        const status = await resp.json();

        if (!EXTRACTION_IN_PROGRESS_STATUSES.has(status.extraction_status)) {
          clearInterval(timer);
          extractionPollTimers.delete(id);
          await loadKBDocuments();
          if (state.selectedDoc && state.selectedDoc.id === id) await kbSelectDoc(id);
        }
      } catch {
        clearInterval(timer);
        extractionPollTimers.delete(id);
      }
    }, 1500);

    extractionPollTimers.set(id, timer);
  }

  async function kbRetryExtraction(id) {
    try {
      const resp = await fetch(`/kb/documents/${id}/retry`, { method: 'POST' });
      if (!resp.ok) throw new Error();
      await loadKBDocuments();
      if (state.selectedDoc && state.selectedDoc.id === id) await kbSelectDoc(id);
    } catch {
      alert('Could not retry extraction. Please try again.');
    }
  }

  // ── Document detail panel ──────────────────────────────────────────────────

  async function kbSelectDoc(id) {
    try {
      const resp = await fetch(`/kb/documents/${id}`);
      if (!resp.ok) return;
      state.selectedDoc = await resp.json();
    } catch { return; }

    renderKBList();
    renderKBDetail(state.selectedDoc);
  }

  function renderKBDetail(doc) {
    const panel = document.getElementById('kb-detail-panel');
    if (!panel) return;
    panel.style.display = 'flex';

    const tagsHtml  = buildTagsHtml(doc.tags) || '<span class="kb-no-tags">No tags</span>';
    const previewHtml = buildPreview(doc);

    panel.innerHTML = `
      <div class="kb-detail-header">
        <div class="kb-detail-title-wrap">
          <span class="kb-detail-file-icon">${FILE_ICONS[doc.file_type] || '<span class=\'icon\' data-lucide=\'file-text\'></span>'}</span>
          <div>
            <div class="kb-detail-title">${escHtml(doc.title)}</div>
            <div class="kb-detail-fname">${escHtml(doc.original_name)}</div>
          </div>
        </div>
 <button class="kb-close-detail-btn"onclick="kbCloseDetail()"title="Close"></button>
      </div>

      <div class="kb-detail-toolbar">
        <button class="kb-dtool-btn kb-dtool-view" onclick="kbViewDoc(${doc.id})"><span class=\'icon\' data-lucide=\'eye\'></span> View</button>
        <button class="kb-dtool-btn kb-dtool-dl"   onclick="kbDownloadDoc(${doc.id})"><span class=\'icon\' data-lucide=\'arrow-down-to-line\'></span> Download</button>
        ${EXTRACTION_FAILED_STATUSES.has(doc.extraction_status)
          ? `<button class="kb-dtool-btn kb-dtool-retry" onclick="kbRetryExtraction(${doc.id})"><span class=\'icon\' data-lucide=\'repeat\'></span> Retry Extraction</button>`
          : ''
        }
        <div class="kb-dtool-sep"></div>
        <button class="kb-dtool-btn kb-dtool-del"  onclick="kbDeleteDoc(${doc.id})"><span class=\'icon\' data-lucide=\'trash-2\'></span> Delete</button>
      </div>

      <div class="kb-meta-section">
        <div class="kb-meta-grid">
          <div class="kb-meta-row"><span class="kb-meta-label">Folder</span><span class="kb-meta-val">${FOLDER_ICONS[doc.folder] || '<span class=\'icon\' data-lucide=\'folder\'></span>'} ${doc.folder}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Version</span><span class="kb-meta-val">v${doc.doc_version || '1.0'}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">File Type</span><span class="kb-meta-val">${doc.file_type.toUpperCase()}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">File Size</span><span class="kb-meta-val">${formatBytes(doc.file_size)}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Effective Date</span><span class="kb-meta-val">${doc.effective_date || '—'}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Review Date</span><span class="kb-meta-val ${doc.review_date && isOverdue(doc.review_date) ? 'kb-overdue' : ''}">${doc.review_date || '—'}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Pages</span><span class="kb-meta-val">${doc.page_count || '—'}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Words</span><span class="kb-meta-val">${doc.word_count ? Number(doc.word_count).toLocaleString() : '—'}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Uploaded</span><span class="kb-meta-val">${formatDate(doc.upload_date)}</span></div>
          <div class="kb-meta-row"><span class="kb-meta-label">Extraction</span><span class="kb-meta-val kb-ext-${doc.extraction_status}">${doc.extraction_status}</span></div>
        </div>
        <div class="kb-meta-tags-row">
          <span class="kb-meta-label">Tags</span>
          <div class="kb-tags-row">${tagsHtml}</div>
        </div>
      </div>

      <div class="kb-preview-section">
        <div class="kb-preview-header">Document Preview</div>
        ${previewHtml}
      </div>`;
  }

  function buildPreview(doc) {
    if (EXTRACTION_IN_PROGRESS_STATUSES.has(doc.extraction_status)) {
      const total = doc.extraction_progress_total || 0;
      const current = doc.extraction_progress_current || 0;
      const label = total ? `Extracting page ${current}/${total}…` : 'Extraction starting…';
      return `<div class="kb-preview-empty">${label}</div>`;
    }
    if (!doc.text_content || (doc.extraction_status !== 'ok' && doc.extraction_status !== 'partial')) {
      return `<div class="kb-preview-empty">No text preview available${EXTRACTION_FAILED_STATUSES.has(doc.extraction_status) ? ' (extraction failed)' : ''}.</div>`;
    }
    const snippet = doc.text_content.slice(0, 2500);
    const truncated = doc.text_content.length > 2500;
    return `<div class="kb-preview-text">${escHtml(snippet)}${truncated ? '\n\n[… document continues …]' : ''}</div>`;
  }

  function kbCloseDetail() {
    const panel = document.getElementById('kb-detail-panel');
    if (panel) panel.style.display = 'none';
    state.selectedDoc = null;
    renderKBList();
  }

  // ── File actions ───────────────────────────────────────────────────────────

  function kbViewDoc(id) {
    window.open(`/kb/documents/${id}/view`, '_blank');
  }

  function kbDownloadDoc(id) {
    window.location.href = `/kb/documents/${id}/download`;
  }

  async function kbDeleteDoc(id) {
    const doc = state.documents.find(d => d.id === id) || state.selectedDoc;
    const name = doc ? doc.title : `Document #${id}`;
    if (!confirm(`Delete "${name}" from the Knowledge Base?\n\nThis cannot be undone.`)) return;

    try {
      const resp = await fetch(`/kb/documents/${id}`, { method: 'DELETE' });
      if (resp.ok) {
        if (state.selectedDoc && state.selectedDoc.id === id) kbCloseDetail();
        await loadKBDocuments();
      } else {
        alert('Failed to delete document. Please try again.');
      }
    } catch {
      alert('Network error. Please try again.');
    }
  }

  // ── Upload modal ───────────────────────────────────────────────────────────

  function openKBUploadModal() {
    document.getElementById('kb-upload-modal')?.classList.add('open');
    document.getElementById('kb-modal-overlay')?.classList.add('open');
    const sel = document.getElementById('kb-folder-select');
    if (sel && state.activeFolder) sel.value = state.activeFolder;
    document.getElementById('kb-upload-status').style.display = 'none';
  }

  function closeKBUploadModal() {
    document.getElementById('kb-upload-modal')?.classList.remove('open');
    document.getElementById('kb-modal-overlay')?.classList.remove('open');
    document.getElementById('kb-upload-form')?.reset();
    const fn = document.getElementById('kb-upload-file-name');
    if (fn) fn.textContent = 'No file chosen';
    document.getElementById('kb-upload-status').style.display = 'none';
  }

  async function submitKBUpload(e) {
    e.preventDefault();

    const fileInput = document.getElementById('kb-upload-file-input');
    if (!fileInput || !fileInput.files[0]) {
      showUploadStatus('error', 'Please select a file.');
      return;
    }

    const fd = new FormData();
    fd.append('file',           fileInput.files[0]);
    fd.append('title',          document.getElementById('kb-title').value.trim() || fileInput.files[0].name);
    fd.append('folder',         document.getElementById('kb-folder-select').value);
    fd.append('tags',           document.getElementById('kb-tags').value.trim());
    fd.append('doc_version',    document.getElementById('kb-version').value.trim() || '1.0');
    fd.append('effective_date', document.getElementById('kb-effective-date').value);
    fd.append('review_date',    document.getElementById('kb-review-date').value);

    const btn = document.getElementById('kb-upload-submit');
    btn.disabled = true;
    showUploadStatus('uploading', 'Uploading and extracting text…');

    try {
      const resp = await fetch('/kb/documents', { method: 'POST', body: fd });
      const data = await resp.json();
      if (resp.ok) {
        showUploadStatus('success', `<span class=\'icon\' data-lucide=\'check\'></span> "${data.title}" added — extracting text in the background…`);
        setTimeout(() => { closeKBUploadModal(); loadKBDocuments(); }, 1200);
        kbPollExtraction(data.id);
      } else {
        showUploadStatus('error', data.error || 'Upload failed.');
      }
    } catch {
      showUploadStatus('error', 'Network error. Please try again.');
    } finally {
      btn.disabled = false;
    }
  }

  function showUploadStatus(type, msg) {
    const el = document.getElementById('kb-upload-status');
    if (!el) return;
    el.style.display = 'block';
    el.className = `kb-upload-status kb-status-${type}`;
    el.textContent = msg;
  }

  // ── Filter / search handlers ───────────────────────────────────────────────

  function kbSetFolder(folder) {
    state.activeFolder = folder;
    state.selectedDoc  = null;
    const panel = document.getElementById('kb-detail-panel');
    if (panel) panel.style.display = 'none';
    loadKBDocuments();
  }

  function kbSearch() {
    state.searchTitle    = document.getElementById('kb-search-title')?.value.trim()    || '';
    state.searchTag      = document.getElementById('kb-search-tag')?.value.trim()      || '';
    state.searchFileType = document.getElementById('kb-search-filetype')?.value        || '';
    state.searchKeyword  = document.getElementById('kb-search-keyword')?.value.trim()  || '';
    state.selectedDoc    = null;
    const panel = document.getElementById('kb-detail-panel');
    if (panel) panel.style.display = 'none';
    loadKBDocuments();
  }

  function kbClearSearch() {
    ['kb-search-title', 'kb-search-tag', 'kb-search-keyword'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    const ft = document.getElementById('kb-search-filetype');
    if (ft) ft.value = '';
    state.searchTitle = state.searchTag = state.searchFileType = state.searchKeyword = '';
    loadKBDocuments();
  }

  // ── Utilities ──────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function buildTagsHtml(tags) {
    if (!tags) return '';
    return tags.split(',').map(t => t.trim()).filter(Boolean)
      .map(t => `<span class="kb-tag">${escHtml(t)}</span>`).join('');
  }

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function formatDate(ts) {
    if (!ts) return '—';
    try {
      return new Date(ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return ts; }
  }

  function isOverdue(dateStr) {
    if (!dateStr) return false;
    try { return new Date(dateStr) < new Date(); } catch { return false; }
  }

  // ── Initialise when KB view is first opened ────────────────────────────────

  function initKB() {
    loadKBDocuments();

    // Enter key triggers search
    ['kb-search-title', 'kb-search-tag', 'kb-search-keyword'].forEach(id => {
      document.getElementById(id)?.addEventListener('keydown', e => {
        if (e.key === 'Enter') kbSearch();
      });
    });

    // File input: update label + auto-fill title
    const fileInput = document.getElementById('kb-upload-file-input');
    if (fileInput) {
      fileInput.addEventListener('change', () => {
        const f = fileInput.files[0];
        const label = document.getElementById('kb-upload-file-name');
        if (label) label.textContent = f ? f.name : 'No file chosen';
        const titleEl = document.getElementById('kb-title');
        if (titleEl && !titleEl.value && f) {
          titleEl.value = f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
        }
      });
    }

    // Close modal on overlay click
    document.getElementById('kb-modal-overlay')?.addEventListener('click', closeKBUploadModal);
  }

  // ── Expose to window ───────────────────────────────────────────────────────

  window.loadKBDocuments    = loadKBDocuments;
  window.kbSetFolder        = kbSetFolder;
  window.kbSelectDoc        = kbSelectDoc;
  window.kbViewDoc          = kbViewDoc;
  window.kbDownloadDoc      = kbDownloadDoc;
  window.kbDeleteDoc        = kbDeleteDoc;
  window.kbRetryExtraction  = kbRetryExtraction;
  window.kbSearch           = kbSearch;
  window.kbClearSearch      = kbClearSearch;
  window.kbCloseDetail      = kbCloseDetail;
  window.openKBUploadModal  = openKBUploadModal;
  window.closeKBUploadModal = closeKBUploadModal;
  window.submitKBUpload     = submitKBUpload;
  window.initKB             = initKB;

})();
