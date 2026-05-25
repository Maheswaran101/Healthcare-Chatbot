// ===== chat.js — AI Chat component =====
"use strict";

// 2. Generate a unique sessionId with a safe fallback for insecure contexts / older browsers
let sessionId = (function() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Safe fallback UUID generator
  return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)
  );
})();

function timeStr() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmt$(v) { return "$" + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }); }

function buildTable(rows) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const headers = Object.keys(rows[0]).slice(0, 7);
  const thead = headers.map((h) => `<th>${h}</th>`).join("");
  const tbody = rows.slice(0, 10).map((r) =>
    `<tr>${headers.map((h) => {
      let v = r[h];
      if (typeof v === "number" && (String(h).toLowerCase().includes("expense") || String(h).toLowerCase().includes("gap"))) v = fmt$(v);
      return `<td>${v ?? "—"}</td>`;
    }).join("")}</tr>`
  ).join("");
  return `<div style="overflow-x:auto;margin-top:10px"><table class="chat-data-table"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
}

function buildObjectTable(obj) {
  const rows = Object.entries(obj).map(([k, v]) => `<tr><td><strong>${k}</strong></td><td>${v}</td></tr>`).join("");
  return `<div style="overflow-x:auto;margin-top:10px"><table class="chat-data-table"><tbody>${rows}</tbody></table></div>`;
}

function appendMessage(role, html, source) {
  const container = document.getElementById("chat-messages");
  if (!container) return;

  const isUser = role === "user";
  const sourceBadge = source
    ? `<span class="source-badge ${String(source).includes("bedrock") ? "source-bedrock" : "source-local"}">
        ${source === "dataset+bedrock" ? "📊 Dataset + model" : source === "dataset" ? "📊 Dataset" : "🔒 Local"}
       </span>`
    : "";

  const div = document.createElement("div");
  div.className = `message message-${isUser ? "user" : "ai"}`;
  div.innerHTML = `
    <div class="message-avatar" aria-hidden="true">
      ${isUser ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>'}
    </div>
    <div class="message-content">
      <div class="message-bubble">${html}${sourceBadge}</div>
      <span class="message-time">${timeStr()}</span>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function showTyping() {
  const container = document.getElementById("chat-messages");
  if (!container) return null;
  const div = document.createElement("div");
  div.className = "message message-ai";
  div.id = "typing-indicator";
  div.innerHTML = `
    <div class="message-avatar" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
    </div>
    <div class="message-content">
      <div class="message-bubble">
        <div class="typing-indicator"><span></span><span></span><span></span></div>
      </div>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function removeTyping() {
  document.getElementById("typing-indicator")?.remove();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatResponse(result) {
  if (!result || !result.response) {
    return `<p style="color:var(--text2)"><em>No response received from the agent.</em></p>`;
  }

  // Display the main response text
  let html = `<p>${result.response}</p>`;
  
  // Clean up: only display note if different from main response (removes duplicate debug text)
  if (result.model_reply && String(result.model_reply).trim() && String(result.model_reply).trim() !== String(result.response).trim()) {
    html += `<p style="margin-top:8px;font-size:12px;line-height:1.45;color:var(--text3)"><em>Note:</em> ${escapeHtml(String(result.model_reply))}</p>`;
  }
  
  const data = result.data;

  if (Array.isArray(data) && data.length > 0) {
    html += buildTable(data);
  } else if (data && typeof data === "object" && !Array.isArray(data)) {
    if (data.gender || data.race) {
      if (data.gender) html += `<p style="margin-top:8px;font-weight:600;font-size:12px;color:var(--text2)">GENDER</p>` + buildTable(data.gender);
      if (data.race)   html += `<p style="margin-top:8px;font-weight:600;font-size:12px;color:var(--text2)">RACE</p>`   + buildTable(data.race);
    } else {
      html += buildObjectTable(data);
    }
  }

  if (result.error) {
    const cleanErr = String(result.error);
    if (cleanErr.includes("expired") || cleanErr.includes("SSO") || cleanErr.includes("credentials")) {
      html += `<div style="margin-top:12px;padding:10px 14px;background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.18);border-radius:10px;font-size:12.5px;line-height:1.5;color:#f87171;box-shadow:var(--shadow-sm)">
        <span style="font-weight:600;display:flex;align-items:center;gap:6px;margin-bottom:4px"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> AWS Bedrock Offline</span>
        Your AWS SSO session has expired. To run Bedrock, execute:
        <code style="background:rgba(0,0,0,0.35);padding:3px 6px;border-radius:5px;font-family:monospace;color:#fff;display:inline-block;margin-top:4px;font-size:11.5px">aws sso login --profile onedatasoftware-customer-poc</code>
      </div>`;
    } else {
      html += `<div style="margin-top:12px;padding:10px 14px;background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.18);border-radius:10px;font-size:12.5px;line-height:1.5;color:#fbbf24;box-shadow:var(--shadow-sm)">
        <span style="font-weight:600;display:flex;align-items:center;gap:6px;margin-bottom:4px"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Local Analytics Active</span>
        Offline fallback engine resolved this request.
      </div>`;
    }
  }
  return html;
}

window.sendChatMessage = async function (msg) {
  const message = (msg || "").trim();
  if (!message) return;

  // 1. Ensure the frontend sends actual dynamic input
  appendMessage("user", `<p>${escapeHtml(message)}</p>`);

  const sendBtn = document.getElementById("btn-send");
  const input   = document.getElementById("chat-input");
  if (sendBtn) sendBtn.disabled = true;
  if (input) { input.value = ""; input.style.height = "auto"; }

  // 10. Improve UI responsiveness & loading state
  const typingEl = showTyping();

  // 7. Add frontend console logging for userInput and sessionId
  console.log("[HealthAI Debug] User Input:", message);
  console.log("[HealthAI Debug] Session ID:", sessionId);

  try {
    // 9. Prevent reuse of cached API responses
    const res = await fetch(`/api/chat?_t=${Date.now()}`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
      },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    const data = await res.json();
    
    // 7. Add frontend console logging for Bedrock response
    console.log("[HealthAI Debug] Bedrock response:", data);

    removeTyping();

    // 11. Handling empty or failed response payloads
    if (!data || (!data.response && !data.error)) {
      appendMessage("ai", `<p style="color:var(--red)">⚠ Received empty response from the agent. Please try again.</p>`);
    } else if (data.error && !data.response) {
      appendMessage("ai", `<p style="color:var(--red)">⚠ Agent Error: ${escapeHtml(data.error)}</p>`);
    } else {
      appendMessage("ai", formatResponse(data), data.source);
    }
  } catch (err) {
    removeTyping();
    console.error("[HealthAI Debug] Chat error:", err);
    appendMessage("ai", `<p style="color:var(--red)">⚠ Connection failed. Please ensure the Flask server is running and accessible.</p>`);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    if (input) input.focus();
  }
};

// Init chat UI listeners
window.initChat = function () {
  const input   = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");
  const clearBtn = document.getElementById("btn-clear-chat");

  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        window.sendChatMessage(input.value);
      }
    });
    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 140) + "px";
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", () => window.sendChatMessage(document.getElementById("chat-input")?.value));
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const container = document.getElementById("chat-messages");
      if (!container) return;
      container.innerHTML = "";
      // 3. Reset sessionId when chat is cleared to prevent stale state
      sessionId = (function() {
        if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
          return crypto.randomUUID();
        }
        return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
          (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)
        );
      })();
      console.log("[HealthAI Debug] Chat cleared. New Session ID:", sessionId);
      appendMessage("ai", "<p>💬 Conversation cleared. How can I help you with the patient data?</p>");
    });
  }

  // Suggestion buttons
  document.getElementById("suggestion-list")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".suggestion-item");
    if (!btn) return;
    window.sendChatMessage(btn.textContent);
    document.getElementById("chat-input")?.focus();
  });
};
