const API_BASE = "http://127.0.0.1:8000";

const state = {
  tasks: [],
  trashTasks: [],
  selectedTaskId: null,
  selectedEmailId: null,
  sidebarPinned: false,
  viewerMode: "summary",
  configReady: false,
  progressTimer: null,
  draftProgressTimer: null,
};

const els = {
  healthDot: document.querySelector("#healthDot"),
  healthText: document.querySelector("#healthText"),
  setupPanel: document.querySelector("#setupPanel"),
  settingsBtn: document.querySelector("#settingsBtn"),
  closeConfigBtn: document.querySelector("#closeConfigBtn"),
  configNotice: document.querySelector("#configNotice"),
  setupStatus: document.querySelector("#setupStatus"),
  setupError: document.querySelector("#setupError"),
  configForm: document.querySelector("#configForm"),
  missingConfig: document.querySelector("#missingConfig"),
  testImapBtn: document.querySelector("#testImapBtn"),
  testSmtpBtn: document.querySelector("#testSmtpBtn"),
  saveConfigBtn: document.querySelector("#saveConfigBtn"),
  runSummaryBtn: document.querySelector("#runSummaryBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  busyText: document.querySelector("#busyText"),
  progressPanel: document.querySelector("#progressPanel"),
  progressMessage: document.querySelector("#progressMessage"),
  progressStage: document.querySelector("#progressStage"),
  progressBar: document.querySelector("#progressBar"),
  globalError: document.querySelector("#globalError"),
  taskSidebar: document.querySelector("#taskSidebar"),
  sidebarToggleBtn: document.querySelector("#sidebarToggleBtn"),
  tasks: document.querySelector("#tasks"),
  taskCount: document.querySelector("#taskCount"),
  trashTasks: document.querySelector("#trashTasks"),
  trashCount: document.querySelector("#trashCount"),
  selectedTitle: document.querySelector("#selectedTitle"),
  selectedMeta: document.querySelector("#selectedMeta"),
  deleteTaskBtn: document.querySelector("#deleteTaskBtn"),
  viewerLabel: document.querySelector("#viewerLabel"),
  viewerTitle: document.querySelector("#viewerTitle"),
  summaryViewBtn: document.querySelector("#summaryViewBtn"),
  originalViewBtn: document.querySelector("#originalViewBtn"),
  summaryView: document.querySelector("#summaryView"),
  originalView: document.querySelector("#originalView"),
  summaryPreview: document.querySelector("#summaryPreview"),
  emailGroups: document.querySelector("#emailGroups"),
  originalEmailPreview: document.querySelector("#originalEmailPreview"),
  generateDraftsBtn: document.querySelector("#generateDraftsBtn"),
  draftError: document.querySelector("#draftError"),
  draftPreview: document.querySelector("#draftPreview"),
  llmProvider: document.querySelector("#llmProvider"),
  llmBaseUrlField: document.querySelector("[data-base-url-field]"),
};

const providerConfigs = {
  deepseek: { adapter: "openai_compatible", baseUrl: "https://api.deepseek.com", classification: "deepseek-v4-flash", summary: "deepseek-v4-pro", draft: "deepseek-v4-pro" },
  codex: { adapter: "openai_compatible", baseUrl: "https://api.openai.com/v1", classification: "gpt-4.1-mini", summary: "gpt-4.1", draft: "gpt-4.1" },
  openai: { adapter: "openai_compatible", baseUrl: "https://api.openai.com/v1", classification: "gpt-4.1-mini", summary: "gpt-4.1", draft: "gpt-4.1" },
  qwen: { adapter: "openai_compatible", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", classification: "qwen-plus", summary: "qwen-plus", draft: "qwen-plus" },
  kimi: { adapter: "openai_compatible", baseUrl: "https://api.moonshot.cn/v1", classification: "kimi-k2-0711-preview", summary: "kimi-k2-0711-preview", draft: "kimi-k2-0711-preview" },
  claude: { adapter: "anthropic", classification: "claude-3-5-haiku-latest", summary: "claude-sonnet-4-20250514", draft: "claude-sonnet-4-20250514" },
  gemini: { adapter: "google", classification: "gemini-2.0-flash", summary: "gemini-2.5-pro", draft: "gemini-2.5-pro" },
  openai_compatible: { adapter: "openai_compatible" },
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail?.message || payload.detail || message;
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  return response;
}

function setHidden(el, hidden) {
  el.classList.toggle("hidden", hidden);
}

function setError(el, message) {
  el.classList.remove("success-box");
  el.textContent = message || "";
  setHidden(el, !message);
}

function setSuccess(el, message) {
  el.classList.add("success-box");
  el.textContent = message || "";
  setHidden(el, !message);
}

function selectedProviderConfig() {
  return providerConfigs[els.llmProvider.value] || providerConfigs.openai_compatible;
}

function formPayload() {
  const data = new FormData(els.configForm);
  const payload = {};
  for (const [key, value] of data.entries()) {
    if (String(value).trim()) payload[key] = String(value).trim();
  }
  payload.LLM_PROVIDER = selectedProviderConfig().adapter;
  return payload;
}

function updateProviderFields() {
  const config = selectedProviderConfig();
  const isOpenAICompatible = config.adapter === "openai_compatible";
  setHidden(els.llmBaseUrlField, !isOpenAICompatible);
  const baseUrlInput = els.configForm.elements.LLM_BASE_URL;
  if (baseUrlInput) baseUrlInput.disabled = !isOpenAICompatible;
}

function applyProviderDefaults() {
  const config = selectedProviderConfig();
  const fields = {
    LLM_BASE_URL: config.baseUrl || "",
    LLM_CLASSIFICATION_MODEL: config.classification || "",
    LLM_SUMMARY_MODEL: config.summary || "",
    LLM_DRAFT_MODEL: config.draft || "",
  };
  for (const [name, value] of Object.entries(fields)) {
    const input = els.configForm.elements[name];
    if (input && value) input.value = value;
    if (input && name === "LLM_BASE_URL" && !value) input.value = "";
  }
  updateProviderFields();
}

function inferProvider(values) {
  const adapter = values.LLM_PROVIDER || "openai_compatible";
  const baseUrl = String(values.LLM_BASE_URL || "").replace(/\/+$/, "");
  if (adapter === "anthropic") return "claude";
  if (adapter === "google") return "gemini";
  if (baseUrl === "https://api.openai.com/v1" && values.LLM_CLASSIFICATION_MODEL === "gpt-4.1-mini") return "codex";
  if (baseUrl === "https://api.deepseek.com") return "deepseek";
  if (baseUrl === "https://api.openai.com/v1") return "openai";
  if (baseUrl === "https://dashscope.aliyuncs.com/compatible-mode/v1") return "qwen";
  if (baseUrl === "https://api.moonshot.cn/v1") return "kimi";
  return "openai_compatible";
}

function populateConfigForm(status) {
  const values = status.values || {};
  for (const element of els.configForm.elements) {
    if (!element.name) continue;
    if (element.dataset.secret) {
      element.value = "";
      element.placeholder = status.secrets?.[element.dataset.secret] ? "Saved; leave blank to keep" : "Required";
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(values, element.name)) {
      element.value = values[element.name] || "";
    }
  }
  for (const hint of els.configForm.querySelectorAll("[data-secret-status]")) {
    const key = hint.dataset.secretStatus;
    hint.textContent = status.secrets?.[key] ? "Credential saved. Leave blank to keep it." : "Credential not saved yet.";
  }
  els.llmProvider.value = inferProvider(values);
  updateProviderFields();
}

async function refreshConfigForm() {
  const response = await api("/config/status");
  const status = await response.json();
  state.configReady = Boolean(status.configured);
  populateConfigForm(status);
  els.setupStatus.textContent = state.configReady ? "Configured" : "Missing settings";
  els.missingConfig.textContent = status.missing?.length ? `Missing: ${status.missing.join(", ")}` : "";
  els.configNotice.textContent = state.configReady ? "" : `Configuration required: ${status.missing?.join(", ") || "missing settings"}.`;
  setHidden(els.configNotice, state.configReady);
  setBusy("");
  return status;
}

async function openConfigPanel() {
  setError(els.setupError, "");
  setHidden(els.setupPanel, false);
  try {
    await refreshConfigForm();
  } catch (error) {
    setError(els.setupError, `Could not read configuration: ${error.message}`);
  }
}

function closeConfigPanel() {
  setHidden(els.setupPanel, true);
}

function updateSidebarState() {
  els.taskSidebar.classList.toggle("pinned", state.sidebarPinned);
  els.sidebarToggleBtn.setAttribute("aria-expanded", String(state.sidebarPinned));
  els.sidebarToggleBtn.setAttribute("aria-label", state.sidebarPinned ? "Collapse task sidebar" : "Pin task sidebar open");
  els.sidebarToggleBtn.title = state.sidebarPinned ? "Collapse task sidebar" : "Pin task sidebar open";
}

function toggleSidebarPinned() {
  state.sidebarPinned = !state.sidebarPinned;
  updateSidebarState();
}


function setViewerMode(mode) {
  state.viewerMode = mode === "original" ? "original" : "summary";
  const showingOriginal = state.viewerMode === "original";
  setHidden(els.summaryView, showingOriginal);
  setHidden(els.originalView, !showingOriginal);
  els.summaryViewBtn.classList.toggle("active", !showingOriginal);
  els.originalViewBtn.classList.toggle("active", showingOriginal);
  els.summaryViewBtn.setAttribute("aria-pressed", String(!showingOriginal));
  els.originalViewBtn.setAttribute("aria-pressed", String(showingOriginal));
  els.viewerLabel.textContent = showingOriginal ? "Original Email" : "Summary Email";
  els.viewerTitle.textContent = showingOriginal ? "Fetched Message" : "Generated Summary";
}


function resetSelectedTask(message = "No task selected.") {
  state.selectedTaskId = null;
  els.selectedTitle.textContent = "Select a task";
  els.selectedMeta.textContent = "";
  state.selectedEmailId = null;
  els.summaryPreview.textContent = message;
  setViewerMode("summary");
  els.emailGroups.textContent = "No task selected.";
  renderOriginalEmailEmpty("No task selected.");
  els.draftPreview.textContent = "No drafts loaded.";
  els.generateDraftsBtn.disabled = true;
  els.deleteTaskBtn.disabled = true;
  setHidden(els.progressPanel, true);
  renderTasks();
}

function selectedTask() {
  return state.tasks.find((task) => task.task_id === state.selectedTaskId) || null;
}

function taskDeleteIsDisabled() {
  const task = selectedTask();
  return !task || task.status === "running";
}

function setBusy(message) {
  els.busyText.textContent = message || "";
  const busy = Boolean(message);
  els.runSummaryBtn.disabled = busy || !state.configReady;
  els.refreshBtn.disabled = busy;
  els.generateDraftsBtn.disabled = busy || !state.configReady || !state.selectedTaskId;
  els.deleteTaskBtn.disabled = busy || taskDeleteIsDisabled();
}

function updateProgress(progress) {
  setHidden(els.progressPanel, false);
  els.progressMessage.textContent = progress.message || "Working...";
  els.progressStage.textContent = progress.stage || "";
  const total = Number(progress.total || 0);
  const current = Number(progress.current || 0);
  if (total > 0) {
    const pct = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
    els.progressBar.classList.remove("indeterminate");
    els.progressBar.style.width = `${pct}%`;
  } else {
    els.progressBar.classList.add("indeterminate");
    els.progressBar.style.width = "35%";
  }
}

function stopProgressTimers() {
  clearInterval(state.progressTimer);
  clearInterval(state.draftProgressTimer);
  state.progressTimer = null;
  state.draftProgressTimer = null;
}

async function pollProgress(taskId, draft = false) {
  const path = draft ? `/tasks/${taskId}/draft-progress` : `/tasks/${taskId}/progress`;
  const response = await api(path);
  const progress = await response.json();
  updateProgress(progress);
  if (["completed", "failed"].includes(progress.status)) {
    if (draft) clearInterval(state.draftProgressTimer);
    else clearInterval(state.progressTimer);
    if (progress.status === "failed") setError(els.globalError, progress.message || "The task failed.");
    await loadTasks();
    if (state.selectedTaskId) await selectTask(state.selectedTaskId, { preserveProgress: true });
  }
}

function startProgressPolling(taskId, draft = false) {
  const key = draft ? "draftProgressTimer" : "progressTimer";
  clearInterval(state[key]);
  pollProgress(taskId, draft).catch(() => {});
  state[key] = setInterval(() => pollProgress(taskId, draft).catch(() => {}), 1000);
}

async function checkHealth() {
  try {
    await api("/health");
    els.healthDot.classList.add("ok");
    els.healthText.textContent = "API online";
  } catch {
    els.healthDot.classList.remove("ok");
    els.healthText.textContent = "API offline";
  }
}

async function loadConfigStatus() {
  try {
    await refreshConfigForm();
  } catch (error) {
    state.configReady = false;
    els.configNotice.textContent = `Could not read configuration: ${error.message}`;
    setHidden(els.configNotice, false);
    setError(els.setupError, `Could not read configuration: ${error.message}`);
  }
}

async function saveConfig() {
  setError(els.setupError, "");
  const oldText = els.saveConfigBtn.textContent;
  els.saveConfigBtn.disabled = true;
  els.saveConfigBtn.textContent = "Testing and saving...";
  try {
    const response = await api("/config/save", { method: "POST", body: JSON.stringify(formPayload()) });
    const status = await response.json();
    state.configReady = Boolean(status.configured);
    populateConfigForm(status);
    els.setupStatus.textContent = state.configReady ? "Configured" : "Missing settings";
    els.missingConfig.textContent = status.missing?.length ? `Missing: ${status.missing.join(", ")}` : "";
    els.configNotice.textContent = state.configReady ? "" : `Configuration required: ${status.missing?.join(", ") || "missing settings"}.`;
    setHidden(els.configNotice, state.configReady);
    setSuccess(els.setupError, "Configuration saved.");
    setBusy("");
  } catch (error) {
    setError(els.setupError, error.message);
  } finally {
    els.saveConfigBtn.disabled = false;
    els.saveConfigBtn.textContent = oldText;
  }
}

async function testConfig(kind) {
  setError(els.setupError, "");
  const button = kind === "imap" ? els.testImapBtn : els.testSmtpBtn;
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "Testing...";
  try {
    await api(`/config/test-${kind}`, { method: "POST", body: JSON.stringify(formPayload()) });
    setSuccess(els.setupError, `${kind.toUpperCase()} connection succeeded.`);
  } catch (error) {
    setError(els.setupError, error.message);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}


function iconSvg(name) {
  if (name === "restore") {
    return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7v6h6"/><path d="M4.5 13A8 8 0 1 0 7 5.3L3 9"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 15h10l1-15"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`;
}

function formatDeletedAt(value) {
  if (!value) return "Deleted recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Deleted recently";
  return `Deleted ${date.toLocaleString()}`;
}

function renderTasks() {
  els.tasks.innerHTML = "";
  els.taskCount.textContent = String(state.tasks.length);
  if (!state.tasks.length) {
    els.tasks.textContent = "No tasks found.";
    return;
  }

  for (const task of state.tasks) {
    const button = document.createElement("button");
    button.className = `task-item${task.task_id === state.selectedTaskId ? " active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <span>
        <span class="task-title">${task.display_title || "Email task"}</span>
        <span class="task-id">${task.task_id}</span>
        <span class="task-flags">${task.status || "unknown"} · ${task.email_count || 0} emails · ${task.has_summary ? "summary" : "no summary"} · ${task.has_drafts ? "drafts" : "no drafts"}</span>
      </span>
    `;
    button.addEventListener("click", () => selectTask(task.task_id));
    els.tasks.appendChild(button);
  }
}


function renderTrashTasks() {
  els.trashTasks.innerHTML = "";
  els.trashCount.textContent = String(state.trashTasks.length);
  if (!state.trashTasks.length) {
    els.trashTasks.textContent = "Trash is empty.";
    return;
  }

  for (const task of state.trashTasks) {
    const row = document.createElement("div");
    row.className = "trash-item";
    row.innerHTML = `
      <span class="trash-copy">
        <span class="task-title">${task.display_title || "Email task"}</span>
        <span class="task-id">${task.task_id}</span>
        <span class="task-flags">${formatDeletedAt(task.deleted_at)} · ${task.email_count || 0} emails</span>
      </span>
      <span class="trash-actions">
        <button class="icon-button restore" title="Restore task" aria-label="Restore task">${iconSvg("restore")}</button>
        <button class="icon-button danger-icon" title="Permanently delete task" aria-label="Permanently delete task">${iconSvg("delete")}</button>
      </span>
    `;
    row.querySelector(".restore").addEventListener("click", () => restoreTrashTask(task));
    row.querySelector(".danger-icon").addEventListener("click", () => permanentlyDeleteTrashTask(task));
    els.trashTasks.appendChild(row);
  }
}

async function loadTrashTasks() {
  const response = await api("/trash/tasks");
  state.trashTasks = await response.json();
  renderTrashTasks();
}

async function restoreTrashTask(task) {
  const confirmed = window.confirm(`Restore this task?\n\n${task.display_title || "Email task"}\nTask ID: ${task.task_id}`);
  if (!confirmed) return;
  setError(els.globalError, "");
  setBusy("Restoring task...");
  try {
    await api(`/trash/tasks/${task.task_id}/${task.trash_id}/restore`, { method: "POST" });
    await Promise.all([loadTasks(), loadTrashTasks()]);
  } catch (error) {
    setError(els.globalError, error.message);
  } finally {
    setBusy("");
  }
}

async function permanentlyDeleteTrashTask(task) {
  const confirmed = window.confirm(`Permanently delete this trashed task? This cannot be undone.\n\n${task.display_title || "Email task"}\nTask ID: ${task.task_id}`);
  if (!confirmed) return;
  setError(els.globalError, "");
  setBusy("Permanently deleting task...");
  try {
    await api(`/trash/tasks/${task.task_id}/${task.trash_id}`, { method: "DELETE" });
    await loadTrashTasks();
  } catch (error) {
    setError(els.globalError, error.message);
  } finally {
    setBusy("");
  }
}

async function loadTasks() {
  const response = await api("/tasks");
  state.tasks = await response.json();
  renderTasks();
}

async function loadSummary(taskId) {
  try {
    const response = await api(`/tasks/${taskId}/summary`, { headers: { Accept: "text/markdown" } });
    els.summaryPreview.textContent = await response.text();
  } catch (error) {
    els.summaryPreview.textContent = `Summary unavailable.\n${error.message}`;
  }
}

function markSelectedEmail() {
  for (const row of els.emailGroups.querySelectorAll(".email-row")) {
    row.classList.toggle("active", row.dataset.emailId === state.selectedEmailId);
  }
}

function renderOriginalEmailEmpty(message = "Select an email to view the original fetched message.") {
  els.originalEmailPreview.className = "original-email empty-state";
  els.originalEmailPreview.textContent = message;
}

function fieldValue(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return "Unknown";
}

function appendMetaItem(parent, label, value) {
  const item = document.createElement("div");
  item.className = "email-meta-item";
  const labelEl = document.createElement("span");
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = value;
  item.append(labelEl, valueEl);
  parent.appendChild(item);
}

function renderOriginalEmail(detail) {
  const info = detail.basic_information || {};
  const email = detail.email || {};
  const subject = fieldValue(email.subject, info.subject, detail.slug);
  const sender = fieldValue(email.sender, email.from, info.from);
  const date = fieldValue(email.date, info.date);
  const category = fieldValue(detail.category, info.category);
  const body = fieldValue(email.body, email.text, "No original body was stored for this email.");

  els.originalEmailPreview.className = "original-email";
  els.originalEmailPreview.innerHTML = "";

  const head = document.createElement("div");
  head.className = "original-email-head";
  const title = document.createElement("h4");
  title.textContent = subject;
  const badge = document.createElement("span");
  badge.className = "category-badge";
  badge.textContent = category;
  head.append(title, badge);

  const meta = document.createElement("div");
  meta.className = "email-meta-grid";
  appendMetaItem(meta, "From", sender);
  appendMetaItem(meta, "Date", date);
  appendMetaItem(meta, "Email ID", fieldValue(detail.email_id));

  const bodyEl = document.createElement("pre");
  bodyEl.className = "original-email-body";
  bodyEl.textContent = body;

  els.originalEmailPreview.append(head, meta, bodyEl);
}

async function selectEmail(emailId) {
  if (!state.selectedTaskId) return;
  state.selectedEmailId = emailId;
  markSelectedEmail();
  setViewerMode("original");
  renderOriginalEmailEmpty("Loading original email...");
  try {
    const response = await api(`/tasks/${state.selectedTaskId}/emails/${emailId}`);
    const detail = await response.json();
    if (state.selectedEmailId === emailId) renderOriginalEmail(detail);
  } catch (error) {
    if (state.selectedEmailId === emailId) renderOriginalEmailEmpty(`Original email unavailable. ${error.message}`);
  }
}

function renderEmails(groups) {
  els.emailGroups.innerHTML = "";
  const categories = Object.keys(groups).sort();
  if (!categories.length) {
    els.emailGroups.textContent = "No emails found for this task.";
    return;
  }

  for (const category of categories) {
    const title = document.createElement("div");
    title.className = "category-title";
    title.textContent = `${category} (${groups[category].length})`;
    els.emailGroups.appendChild(title);

    for (const email of groups[category]) {
      const row = document.createElement("div");
      row.className = "email-row";
      row.dataset.emailId = email.email_id;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = email.email_id;
      checkbox.setAttribute("aria-label", `Select email ${email.email_id} for draft generation`);
      checkbox.addEventListener("click", (event) => event.stopPropagation());

      const openButton = document.createElement("button");
      openButton.type = "button";
      openButton.className = "email-open";
      openButton.innerHTML = `
        <span class="email-title"></span>
        <span class="email-meta"></span>
      `;
      openButton.querySelector(".email-title").textContent = email.subject || email.slug || email.email_id;
      openButton.querySelector(".email-meta").textContent = `ID: ${email.email_id}`;
      openButton.addEventListener("click", () => selectEmail(email.email_id));

      row.addEventListener("click", () => selectEmail(email.email_id));
      row.append(checkbox, openButton);
      els.emailGroups.appendChild(row);
    }
  }
  markSelectedEmail();
}

async function loadEmails(taskId) {
  try {
    const response = await api(`/tasks/${taskId}/emails`);
    renderEmails(await response.json());
  } catch (error) {
    els.emailGroups.textContent = error.message;
  }
}

function draftHeaders(markdown) {
  const headers = { to: "", subject: "" };
  for (const line of String(markdown || "").split(/\r?\n/)) {
    const to = line.match(/^To:\s*(.*)$/i);
    if (to) headers.to = to[1].trim();
    const subject = line.match(/^Subject:\s*(.*)$/i);
    if (subject) headers.subject = subject[1].trim();
    if (headers.to && headers.subject) break;
  }
  return headers;
}

async function saveDraft(taskId, emailId, markdown) {
  const response = await api(`/tasks/${taskId}/drafts/${emailId}`, {
    method: "PUT",
    body: JSON.stringify({ markdown }),
  });
  return response.json();
}

async function sendDraft(taskId, emailId, markdown, statusEl, saveBtn, sendBtn) {
  statusEl.textContent = "Saving draft...";
  saveBtn.disabled = true;
  sendBtn.disabled = true;
  try {
    const saved = await saveDraft(taskId, emailId, markdown);
    const headers = draftHeaders(saved.markdown);
    const confirmed = window.confirm(
      `Send this email now?\n\nTask ID: ${taskId}\nEmail ID: ${emailId}\nTo: ${headers.to || "Unknown"}\nSubject: ${headers.subject || "Unknown"}`
    );
    if (!confirmed) {
      statusEl.textContent = "Draft saved. Send canceled.";
      return;
    }
    statusEl.textContent = "Sending email...";
    const response = await api(`/tasks/${taskId}/drafts/${emailId}/send`, {
      method: "POST",
      body: JSON.stringify({ approved: true }),
    });
    const result = await response.json();
    statusEl.textContent = `Sent to ${result.recipient}.`;
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.classList.add("error");
  } finally {
    saveBtn.disabled = false;
    sendBtn.disabled = false;
  }
}

function renderDrafts(drafts) {
  els.draftPreview.innerHTML = "";
  if (!drafts.length) {
    els.draftPreview.textContent = "No drafts found for this task.";
    return;
  }

  for (const draft of drafts) {
    const card = document.createElement("article");
    card.className = "draft-card";

    const head = document.createElement("div");
    head.className = "draft-card-head";
    const title = document.createElement("div");
    title.className = "draft-title";
    title.textContent = `Email ${draft.email_id}`;
    const actions = document.createElement("div");
    actions.className = "draft-actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Save Draft";
    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "primary";
    sendBtn.textContent = "Send";
    actions.append(saveBtn, sendBtn);
    head.append(title, actions);

    const textarea = document.createElement("textarea");
    textarea.className = "draft-editor";
    textarea.value = draft.markdown || "";
    textarea.spellcheck = true;

    const status = document.createElement("div");
    status.className = "draft-status";

    saveBtn.addEventListener("click", async () => {
      status.classList.remove("error");
      status.textContent = "Saving draft...";
      saveBtn.disabled = true;
      try {
        const saved = await saveDraft(draft.task_id, draft.email_id, textarea.value);
        textarea.value = saved.markdown || textarea.value;
        status.textContent = "Draft saved.";
      } catch (error) {
        status.textContent = error.message;
        status.classList.add("error");
      } finally {
        saveBtn.disabled = false;
      }
    });

    sendBtn.addEventListener("click", () => {
      status.classList.remove("error");
      sendDraft(draft.task_id, draft.email_id, textarea.value, status, saveBtn, sendBtn);
    });

    card.append(head, textarea, status);
    els.draftPreview.appendChild(card);
  }
}

async function loadDrafts(taskId) {
  const response = await api(`/tasks/${taskId}/drafts`);
  renderDrafts(await response.json());
}

async function selectTask(taskId, options = {}) {
  state.selectedTaskId = taskId;
  renderTasks();
  els.selectedTitle.textContent = `Task ${taskId}`;
  els.selectedMeta.textContent = "";
  state.selectedEmailId = null;
  setViewerMode("summary");
  els.summaryPreview.textContent = "Loading summary...";
  els.emailGroups.textContent = "Loading fetched emails...";
  renderOriginalEmailEmpty("Select an email to view the original fetched message.");
  els.draftPreview.textContent = "Loading drafts...";
  els.generateDraftsBtn.disabled = !state.configReady;
  els.deleteTaskBtn.disabled = taskDeleteIsDisabled();

  try {
    const metadataResponse = await api(`/tasks/${taskId}`);
    const metadata = await metadataResponse.json();
    els.selectedTitle.textContent = metadata.display_title || `Task ${taskId}`;
    els.selectedMeta.textContent = `${metadata.email_count || 0} emails · ${metadata.status}`;
  } catch (error) {
    els.selectedMeta.textContent = error.message;
  }

  await Promise.all([loadSummary(taskId), loadEmails(taskId), loadDrafts(taskId)]);
  if (!options.preserveProgress) setHidden(els.progressPanel, true);
}

function selectedEmailIds() {
  return Array.from(els.emailGroups.querySelectorAll("input[type='checkbox']:checked")).map((input) => input.value);
}


async function deleteSelectedTask() {
  const task = selectedTask();
  if (!task) return;
  if (task.status === "running") {
    setError(els.globalError, "This task is still running. Wait for it to finish before deleting it.");
    return;
  }
  const label = task.display_title || `Task ${task.task_id}`;
  const confirmed = window.confirm(`Move this task to trash?\n\n${label}\nTask ID: ${task.task_id}`);
  if (!confirmed) return;

  setError(els.globalError, "");
  setBusy("Deleting task...");
  try {
    await api(`/tasks/${task.task_id}`, { method: "DELETE" });
    await Promise.all([loadTasks(), loadTrashTasks()]);
    resetSelectedTask();
  } catch (error) {
    setError(els.globalError, error.message);
  } finally {
    setBusy("");
  }
}

async function runSummary() {
  setError(els.globalError, "");
  setBusy("Running summary agent...");
  updateProgress({ message: "Starting summary agent...", stage: "initializing", current: 0, total: 0 });
  try {
    const response = await api("/tasks/summary", { method: "POST" });
    const result = await response.json();
    await loadTasks();
    await selectTask(result.task_id, { preserveProgress: true });
    startProgressPolling(result.task_id);
  } catch (error) {
    setError(els.globalError, error.message);
  } finally {
    setBusy("");
  }
}

async function generateDrafts() {
  setError(els.draftError, "");
  const emailIds = selectedEmailIds();
  if (!state.selectedTaskId || !emailIds.length) {
    setError(els.draftError, "Select at least one email first.");
    return;
  }

  setBusy("Generating drafts...");
  updateProgress({ message: "Starting draft agent...", stage: "loading_selected_emails", current: 0, total: 0 });
  startProgressPolling(state.selectedTaskId, true);
  try {
    const response = await api(`/tasks/${state.selectedTaskId}/drafts`, {
      method: "POST",
      body: JSON.stringify({ email_ids: emailIds }),
    });
    const result = await response.json();
    renderDrafts(result.drafts || []);
    await loadTasks();
  } catch (error) {
    setError(els.draftError, error.message);
  } finally {
    setBusy("");
  }
}

els.sidebarToggleBtn.addEventListener("click", toggleSidebarPinned);
els.summaryViewBtn.addEventListener("click", () => setViewerMode("summary"));
els.originalViewBtn.addEventListener("click", () => setViewerMode("original"));
els.settingsBtn.addEventListener("click", openConfigPanel);
els.closeConfigBtn.addEventListener("click", closeConfigPanel);
els.setupPanel.addEventListener("click", (event) => {
  if (event.target === els.setupPanel) closeConfigPanel();
});
els.saveConfigBtn.addEventListener("click", saveConfig);
els.testImapBtn.addEventListener("click", () => testConfig("imap"));
els.testSmtpBtn.addEventListener("click", () => testConfig("smtp"));
els.llmProvider.addEventListener("change", applyProviderDefaults);
els.runSummaryBtn.addEventListener("click", runSummary);
els.refreshBtn.addEventListener("click", async () => {
  setBusy("Refreshing tasks...");
  try {
    await Promise.all([loadTasks(), loadTrashTasks()]);
  } finally {
    setBusy("");
  }
});
els.generateDraftsBtn.addEventListener("click", generateDrafts);
els.deleteTaskBtn.addEventListener("click", deleteSelectedTask);

updateSidebarState();
setViewerMode("summary");
updateProviderFields();
checkHealth();
loadConfigStatus();
loadTasks().catch((error) => setError(els.globalError, error.message));
loadTrashTasks().catch((error) => setError(els.globalError, error.message));
window.addEventListener("beforeunload", stopProgressTimers);
