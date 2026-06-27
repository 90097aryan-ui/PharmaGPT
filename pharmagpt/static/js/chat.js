// chat.js — handles all user interactions, API calls, and message rendering

// ── DOM references ────────────────────────────────────────────────────────────
const messagesEl  = document.getElementById("messages");
const inputEl     = document.getElementById("user-input");
const sendBtn     = document.getElementById("send-btn");
const clearBtn    = document.getElementById("btn-clear");
const useDocsChk  = document.getElementById("use-docs-checkbox");

// ── Helpers ───────────────────────────────────────────────────────────────────

function getTime() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Append a completed (non-streaming) message bubble to the chat window.
 * @param {string}  role    - "user" | "ai" | null (null = error)
 * @param {string}  text    - message content
 * @param {boolean} isError - render as error style
 */
function appendMessage(role, text, isError = false) {
  if (isError) {
    const div = document.createElement("div");
    div.className = "error-bubble";
    div.textContent = text;
    messagesEl.appendChild(div);
    scrollToBottom();
    return;
  }

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "U" : "Rx";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (role === "ai") {
    bubble.innerHTML = marked.parse(text);
  } else {
    bubble.textContent = text;
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = getTime();

  const content = document.createElement("div");
  content.style.display = "flex";
  content.style.flexDirection = "column";
  content.appendChild(bubble);
  content.appendChild(meta);

  if (role === "user") {
    row.appendChild(content);
    row.appendChild(avatar);
  } else {
    row.appendChild(avatar);
    row.appendChild(content);
  }

  messagesEl.appendChild(row);
  scrollToBottom();
}

/**
 * Create an AI message row that starts with "PharmaGPT is thinking…"
 * Returns references to the bubble and inner elements so the stream loop
 * can update them as tokens arrive.
 */
function createStreamingBubble() {
  const row = document.createElement("div");
  row.className = "message-row ai";
  row.id = "streaming-row";

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = "Rx";

  const bubble = document.createElement("div");
  bubble.className = "bubble streaming";

  const thinkingEl = document.createElement("div");
  thinkingEl.className = "thinking-label";
  thinkingEl.id = "thinking-label";
  thinkingEl.innerHTML =
    '<span class="thinking-dots"><span></span><span></span><span></span></span> PharmaGPT is thinking…';

  const contentEl = document.createElement("div");
  contentEl.id = "stream-content";

  bubble.appendChild(thinkingEl);
  bubble.appendChild(contentEl);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.id = "stream-meta";
  meta.textContent = getTime();

  const wrapper = document.createElement("div");
  wrapper.style.display = "flex";
  wrapper.style.flexDirection = "column";
  wrapper.appendChild(bubble);
  wrapper.appendChild(meta);

  row.appendChild(avatar);
  row.appendChild(wrapper);
  messagesEl.appendChild(row);
  scrollToBottom();

  return { row, bubble, contentEl, thinkingEl, wrapper };
}

function removeStreamingRow() {
  const el = document.getElementById("streaming-row");
  if (el) el.remove();
}

/**
 * Render a "Sources:" strip below the AI wrapper element.
 * @param {HTMLElement} wrapper  - the flex column wrapper inside the AI row
 * @param {Array}       sources  - [{id, name}, ...]
 */
function appendSources(wrapper, sources) {
  if (!sources || sources.length === 0) return;

  const strip = document.createElement("div");
  strip.className = "sources-strip";

  const label = document.createElement("span");
  label.className = "sources-label";
  label.textContent = "Sources:";
  strip.appendChild(label);

  sources.forEach(src => {
    const pill = document.createElement("span");
    pill.className = "sources-pill";
    pill.textContent = src.name;
    strip.appendChild(pill);
  });

  wrapper.appendChild(strip);
  scrollToBottom();
}

// ── Send message (streaming) ──────────────────────────────────────────────────

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  if (!window.activeProject) {
    appendMessage(null, "Please select or create a project before sending a message.", true);
    return;
  }

  appendMessage("user", text);
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendBtn.disabled = true;

  const useDocs = useDocsChk ? useDocsChk.checked : false;
  const { bubble, contentEl, thinkingEl, wrapper } = createStreamingBubble();

  let accumulatedText = "";
  let firstChunkReceived = false;

  try {
    const response = await fetch("/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        project_id: window.activeProject.id,
        use_documents: useDocs,
      }),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;

        let event;
        try { event = JSON.parse(line.slice(5).trim()); } catch { continue; }

        if (event.error) {
          removeStreamingRow();
          appendMessage(null, event.error, true);
          return;
        }

        if (event.chunk) {
          if (!firstChunkReceived) {
            thinkingEl.style.display = "none";
            bubble.classList.add("has-content");
            firstChunkReceived = true;
          }
          accumulatedText += event.chunk;
          contentEl.innerHTML = marked.parse(accumulatedText);
          scrollToBottom();
        }

        if (event.done) {
          bubble.classList.remove("streaming");
          // Render Sources strip if documents were used
          if (event.sources && event.sources.length > 0) {
            appendSources(wrapper, event.sources);
          }
        }
      }
    }

  } catch (err) {
    removeStreamingRow();
    appendMessage(null, "Network error — please check your connection and try again.", true);
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// ── Clear conversation ────────────────────────────────────────────────────────

async function clearConversation() {
  if (!window.activeProject) return;
  if (!confirm(`Clear all messages in "${window.activeProject.name}"? This cannot be undone.`)) return;

  try {
    await fetch("/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: window.activeProject.id }),
    });
    messagesEl.innerHTML = "";
  } catch (err) {
    appendMessage(null, "Could not clear the conversation. Please try again.", true);
  }
}

// ── Event listeners ───────────────────────────────────────────────────────────

sendBtn.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
});

clearBtn.addEventListener("click", clearConversation);

// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener("load", () => {
  sendBtn.disabled = true;
  inputEl.placeholder = "Select or create a project to start chatting…";
  inputEl.focus();
});
