const $ = (id) => document.getElementById(id);
let currentSession = null;
let busy = false;
let hasReasoningBackend = false;
let hasVisionBackend = false;

const request = (method, route, body) => window.sovereign.request(method, route, body);

function addMessage(role, content) {
  $("messages").querySelector(".empty")?.remove();
  const item = document.createElement("div");
  item.className = `message ${role}`;
  const label = document.createElement("small");
  label.textContent = role === "user" ? "You" : role === "error" ? "Error" : "Sovereign";
  item.append(label, document.createTextNode(content));
  $("messages").append(item);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function setBusy(value) {
  busy = value;
  $("resume").disabled = value;
  $("feedback").textContent = value ? "Sovereign is working…" : "";
  updateSendAvailability();
}

function clearApprovals() {
  for (const input of $("approvals").querySelectorAll("input")) input.checked = false;
  $("extra-approval").value = "";
}

function selectedApprovals() {
  const selected = [...$("approvals").querySelectorAll("input:checked")].map((input) => input.value);
  const extra = $("extra-approval").value.trim();
  if (extra) selected.push(extra);
  return selected;
}

function messageText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.filter((item) => item?.type === "text").map((item) => item.text).join("\n");
  return "";
}

async function loadSession(id) {
  showPlugins(false);
  const session = await request("GET", `/v1/sessions/${id}`);
  currentSession = session;
  $("messages").replaceChildren();
  for (const message of session.messages) {
    if (message.role === "user" || (message.role === "assistant" && !message.tool_calls)) {
      const text = messageText(message.content);
      if (text) addMessage(message.role, text);
    }
  }
  if (!session.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const greeting = document.createElement("span");
    greeting.textContent = "What can I help you with?";
    empty.append(greeting);
    if (!hasReasoningBackend) {
      const setup = document.createElement("small");
      setup.textContent = `Add a reasoning backend in ${$("config-path").textContent || "~/.sovereign/config.json"} to start chatting.`;
      empty.append(setup);
    }
    $("messages").append(empty);
  }
  $("title").textContent = "Sovereign";
  $("subtitle").textContent = `${session.status} · ${session.message_count} messages`;
  $("resume").hidden = session.status !== "interrupted";
  for (const item of $("sessions").children) item.classList.toggle("active", item.dataset.id === id);
}

async function refreshSessions(selectId) {
  const {sessions} = await request("GET", "/v1/sessions");
  $("sessions").replaceChildren();
  for (const session of sessions) {
    const button = document.createElement("button");
    button.className = "session";
    button.dataset.id = session.id;
    const title = document.createElement("span");
    title.textContent = `Conversation ${session.id.slice(0, 8)}`;
    const meta = document.createElement("small");
    meta.textContent = `${session.status} · ${session.message_count} messages`;
    button.append(title, meta);
    button.addEventListener("click", () => void loadSession(session.id));
    $("sessions").append(button);
  }
  const target = selectId || currentSession?.id || sessions[0]?.id;
  if (target) await loadSession(target);
}

async function createSession() {
  const session = await request("POST", "/v1/sessions", {});
  await refreshSessions(session.id);
}

async function initialize() {
  try {
    const [status, toolResponse] = await Promise.all([
      request("GET", "/v1/status"), request("GET", "/v1/tools"),
    ]);
    $("connection").textContent = "Core connected";
    $("connection").classList.add("online");
    $("version").textContent = `v${status.version}`;
    hasVisionBackend = status.backends.some((backend) => backend.healthy && backend.enabled && backend.capabilities.includes("vision"));
    const visionAvailable = status.computer_control_enabled && status.visual_autonomy_enabled && hasVisionBackend;
    hasReasoningBackend = status.backends.some((backend) => backend.healthy && backend.enabled && backend.capabilities.includes("reasoning"));
    $("visual").disabled = !visionAvailable;
    if (!visionAvailable) $("visual").checked = false;
    $("mode-note").textContent = visionAvailable ? "Reasoning conversation" : "Desktop vision needs computer control, visual autonomy, and a vision backend";
    updateSendAvailability();
    $("prompt").placeholder = hasReasoningBackend
      ? "Ask Sovereign to help with a task…"
      : "Configure a reasoning backend to start chatting…";
    $("config-path").textContent = status.config_path || "~/.sovereign/config.json";
    renderPlugins(toolResponse.mcp_servers || []);
    $("approvals").replaceChildren();
    const actions = ["sovereign__write_text", ...toolResponse.visual_action_tools];
    for (const name of actions) {
      if (name === "sovereign__write_text" && !toolResponse.native_tools.includes(name)) continue;
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = name;
      label.append(checkbox, document.createTextNode(name.replace("sovereign__", "")));
      $("approvals").append(label);
    }
    const {sessions} = await request("GET", "/v1/sessions");
    if (sessions.length) await refreshSessions(sessions[0].id);
    else await createSession();
  } catch (error) {
    $("connection").textContent = "Core unavailable";
    addMessage("error", error.message);
  }
}

function renderPlugins(plugins) {
  const list = $("plugin-list");
  list.replaceChildren();
  if (!plugins.length) {
    const empty = document.createElement("p");
    empty.className = "empty plugin-empty";
    empty.textContent = "No MCP plugins are configured on this device yet.";
    list.append(empty);
    return;
  }
  for (const name of plugins) {
    const card = document.createElement("article");
    card.className = "plugin-card";
    const title = document.createElement("strong");
    title.textContent = name;
    const state = document.createElement("small");
    state.textContent = "Configured · exact tool approval required per run";
    card.append(title, state);
    list.append(card);
  }
}

function showPlugins(show) {
  $("plugins-view").hidden = !show;
  $("conversation-view").hidden = show;
  $("plugins-button").classList.toggle("active", show);
  $("chats-button").classList.toggle("selected", !show);
  if (show) {
    $("title").textContent = "Plugins";
    $("subtitle").textContent = "Local integrations configured for Sovereign";
  } else if (currentSession) {
    $("title").textContent = `Conversation ${currentSession.id.slice(0, 8)}`;
    $("subtitle").textContent = `${currentSession.status} · ${currentSession.message_count} messages`;
  }
}

function updateSendAvailability() {
  const backendAvailable = $("visual").checked ? hasVisionBackend : hasReasoningBackend;
  $("send").disabled = busy || !backendAvailable;
}

$("new-session").addEventListener("click", () => {
  showPlugins(false);
  void createSession().catch((error) => addMessage("error", error.message));
});
$("plugins-button").addEventListener("click", () => showPlugins(true));
$("refresh").addEventListener("click", () => void initialize());
$("visual").addEventListener("change", () => {
  $("mode-note").textContent = $("visual").checked
    ? "Desktop screenshot loop"
    : hasReasoningBackend ? "Reasoning conversation" : "Configure a reasoning backend before chatting";
  updateSendAvailability();
});
$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  const visual = $("visual").checked;
  if (visual && !hasVisionBackend) return addMessage("error", "No healthy vision backend is available. Refresh status after configuring one.");
  if (!visual && !hasReasoningBackend) return addMessage("error", "No healthy reasoning backend is available. Configure one, then select Refresh.");
  if (!visual && !currentSession) return addMessage("error", "Create a conversation first.");
  const approved_tools = selectedApprovals();
  clearApprovals();
  $("prompt").value = "";
  addMessage("user", visual ? `[visual] ${prompt}` : prompt);
  setBusy(true);
  try {
    const result = await request("POST", visual ? "/v1/computer/run" : "/v1/run", {
      prompt, approved_tools, ...(visual ? {} : {session_id: currentSession.id}),
    });
    addMessage("assistant", result.text || "Task complete.");
    if (!visual) await refreshSessions(currentSession.id);
  } catch (error) {
    addMessage("error", error.message);
    if (!visual && currentSession) await refreshSessions(currentSession.id);
  } finally { setBusy(false); }
});
$("resume").addEventListener("click", async () => {
  if (busy || !currentSession) return;
  const approved_tools = selectedApprovals();
  clearApprovals();
  setBusy(true);
  try {
    const result = await request("POST", `/v1/sessions/${currentSession.id}/resume`, {approved_tools});
    addMessage("assistant", result.text || "Task complete.");
    await refreshSessions(currentSession.id);
  } catch (error) { addMessage("error", error.message); }
  finally { setBusy(false); }
});

window.sovereign.onUpdate((detail) => {
  if (!detail.available) return;
  $("update-text").textContent = `Sovereign ${detail.version} is available`;
  $("update").hidden = false;
});
$("install-update").addEventListener("click", () => void window.sovereign.installUpdate().catch((error) => addMessage("error", error.message)));
void initialize();
