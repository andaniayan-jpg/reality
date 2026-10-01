const api = window.REALITY_API_BASE || `${location.protocol}//${location.hostname}:8000`;
const app = document.querySelector("#app");
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const pathFor = (id, suffix) => `/v1/models/${encodeURIComponent(id)}/${suffix}`;
async function request(path, options = {}) {
  const response = await fetch(`${api}${path}`, { credentials: "include", ...options });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return data;
}
const post = (path, body) => request(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const page = (label, title, intro, body) => `<section class="page-head"><p class="eyebrow">${label}</p>
  <h1>${title}</h1><p class="lede">${intro}</p></section>${body}`;
function showStatus(message, level = "info") {
  const element = document.querySelector("#status");
  if (element) { element.textContent = message; element.className = `status ${level}`; }
}
function showOutput(value) {
  const element = document.querySelector("#output");
  if (element) element.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}
function home() {
  app.innerHTML = page("REALITY / PHYSICAL INTELLIGENCE", "Understand a world before you change it.",
    "Read real 3D and CAD files. Ask precise spatial questions. Test changes and keep the evidence.", `
    <div class="actions"><a class="button" href="/playground">Open playground</a><a class="button secondary" href="/docs">Explore API</a></div>
    <div class="feature-grid"><article><span class="eyebrow">01 / READ</span><h2>Inspect the source</h2><p>OBJ, STL, PLY, GLB, glTF, and optional STEP geometry with named parts, bounds, and topology where available.</p></article>
    <article><span class="eyebrow">02 / REASON</span><h2>Measure what exists</h2><p>Distance, clearance, intersections, and topology. The Python package also supports branching, visibility, and MuJoCo simulations.</p></article>
    <article><span class="eyebrow">03 / CHANGE</span><h2>Make a checked edit</h2><p>Submit a geometry edit and keep the original as a separate model version. Results carry units and evidence.</p></article></div>
    <section class="terminal"><div class="result-head">A small Reality query</div><pre>import reality
model = reality.open("assembly.step")
print(model.summary())
print(model.clearance("shaft", "housing"))</pre></section>
    <p class="muted">STEP support requires the optional CAD dependency. Keep API keys on your server.</p>`);
}
function docs() {
  app.innerHTML = page("DEVELOPER DOCS", "One engine. Two ways in.",
    "Use the Python package directly or create an API key for a backend or agent.", `
    <div class="feature-grid two"><article><span class="eyebrow">PYTHON</span><h2>Local package</h2><pre>pip install reality
import reality
model = reality.open("scene.glb")
print(model.parts)</pre></article><article><span class="eyebrow">HTTP API</span><h2>Hosted service</h2><pre>curl ${escapeHtml(api)}/v1/files \\
  -H "Authorization: Bearer $REALITY_API_KEY" \\
  -F "file=@scene.glb"</pre></article></div>
    <p class="notice">Browser requests use an HttpOnly session. Secret keys belong in server-side storage.</p>
    <a class="button secondary" href="${escapeHtml(api)}/docs" target="_blank" rel="noreferrer">Open API reference</a>`);
}
function signIn() {
  app.innerHTML = page("DEVELOPER ACCESS", "Sign in to Reality.",
    "Use a mobile number and one-time code, or an existing email account.", `
    <div class="feature-grid two auth-grid"><section class="panel"><h2>Mobile number</h2>
      <form id="phone-start"><label>Phone with country code<input name="phone" type="tel" autocomplete="tel" placeholder="+14155552671" pattern="\\+[1-9][0-9]{7,14}" required></label><button>Send code</button></form>
      <form id="phone-check" hidden><label>Verification code<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" required></label><button>Verify and sign in</button></form></section>
      <section class="panel"><h2>Email account</h2><form id="email-login"><label>Email<input name="email" type="email" autocomplete="email" required></label>
      <label>Password<input name="password" type="password" autocomplete="current-password" minlength="12" required></label><div class="actions"><button>Sign in</button><button type="button" class="secondary" id="email-register">Create account</button></div></form></section></div>
    <p id="status" class="status" role="status"></p>`);
  let phone = "";
  document.querySelector("#phone-start").onsubmit = async (event) => {
    event.preventDefault(); phone = new FormData(event.currentTarget).get("phone").trim();
    try { await post("/v1/phone/start", { phone }); document.querySelector("#phone-check").hidden = false; showStatus("Code sent. Check your phone.", "success"); }
    catch (error) { showStatus(error.message, "error"); }
  };
  document.querySelector("#phone-check").onsubmit = async (event) => {
    event.preventDefault();
    try { await post("/v1/phone/check", { phone, code: new FormData(event.currentTarget).get("code") }); location.assign("/dashboard"); }
    catch (error) { showStatus(error.message, "error"); }
  };
  async function emailAuth(path) {
    try { await post(path, Object.fromEntries(new FormData(document.querySelector("#email-login")))); location.assign("/dashboard"); }
    catch (error) { showStatus(error.message, "error"); }
  }
  document.querySelector("#email-login").onsubmit = (event) => { event.preventDefault(); emailAuth("/v1/sessions"); };
  document.querySelector("#email-register").onclick = () => emailAuth("/v1/accounts");
}
async function guarded(render) {
  let account;
  try { account = await request("/v1/me"); }
  catch (error) {
    if (error.status === 401) { signIn(); return; }
    app.innerHTML = page("CONNECTION ERROR", "We couldn't reach your workspace.", escapeHtml(error.message),
      `<a class="button secondary" href="${escapeHtml(location.pathname)}">Retry</a>`);
    return;
  }
  try { await render(account); }
  catch (error) {
    app.innerHTML = page("WORKSPACE ERROR", "The workspace could not load.", escapeHtml(error.message),
      `<a class="button secondary" href="${escapeHtml(location.pathname)}">Retry</a>`);
  }
}
async function dashboard(account) {
  const [usage, files, history] = await Promise.all([request("/v1/usage"), request("/v1/files"), request("/v1/requests")]);
  app.innerHTML = page("DASHBOARD", "Your workspace.", `Signed in as ${escapeHtml(account.phone || account.email || account.id)}.`, `
    <div class="metric-grid"><article><strong>${usage.stored_bytes.toLocaleString()}</strong><span>bytes stored</span></article><article><strong>${usage.request_count.toLocaleString()}</strong><span>API requests</span></article><article><strong>${usage.keys.toLocaleString()}</strong><span>developer keys</span></article></div>
    <div class="actions"><a class="button" href="/playground">Try a model</a><a class="button secondary" href="/dashboard/keys">Manage keys</a><a class="button secondary" href="/dashboard/files">View files</a></div>
    <section class="panel"><h2>Recent models</h2><div class="file-list">${files.length ? files.slice(0, 5).map((file) => `<a href="/playground?id=${encodeURIComponent(file.id)}"><span>${escapeHtml(file.filename)}</span><span class="tag">${escapeHtml(file.status)}</span></a>`).join("") : `<p class="muted">No files yet. Upload a model in the playground.</p>`}</div></section>
    <section class="panel"><h2>Recent API requests</h2><div class="file-list">${history.length ? history.slice(0, 5).map((item) => `<div><span>${escapeHtml(item.method)} ${escapeHtml(item.path)}</span><span class="tag">${escapeHtml(item.status_code)}</span></div>`).join("") : `<p class="muted">No requests yet.</p>`}</div></section><button id="logout" class="secondary">Sign out</button>`);
  document.querySelector("#logout").onclick = async () => { await request("/v1/sessions", { method: "DELETE" }); location.assign("/"); };
}
async function keys() {
  const data = await request("/v1/keys");
  app.innerHTML = page("DEVELOPER KEYS", "Connect your applications.", "Each key is shown once. Store it in your server's secret manager.", `
    <section class="panel"><form id="key-create" class="inline-form"><label>Environment<select name="environment"><option value="test">Test</option><option value="live">Live</option></select></label><button>Create API key</button></form>
    <div id="key-reveal" class="reveal" hidden><p>Copy this key now. It will not appear again.</p><code id="new-key"></code><button type="button" id="copy-key" class="secondary">Copy</button></div></section>
    <section class="panel"><h2>Existing keys</h2><div class="file-list">${data.length ? data.map((key) => `<div><span><code>${escapeHtml(key.prefix)}…</code> <small>${escapeHtml(key.environment)} · ${escapeHtml(key.status)}</small></span><button class="secondary revoke" data-id="${escapeHtml(key.id)}" ${key.status !== "active" ? "disabled" : ""}>Revoke</button></div>`).join("") : `<p class="muted">No keys created.</p>`}</div></section><p id="status" class="status" role="status"></p>`);
  document.querySelector("#key-create").onsubmit = async (event) => {
    event.preventDefault();
    try { const key = await post("/v1/keys", { environment: new FormData(event.currentTarget).get("environment") });
      document.querySelector("#new-key").textContent = key.key;
      document.querySelector("#key-reveal").hidden = false;
      document.querySelector("#copy-key").onclick = () => navigator.clipboard.writeText(key.key);
      showStatus("Key created. Copy it now.", "success");
    } catch (error) { showStatus(error.message, "error"); }
  };
  document.querySelectorAll(".revoke").forEach((button) => button.onclick = async () => {
    if (!confirm("Revoke this key? Applications using it will stop working.")) return;
    try { await post(`/v1/keys/${encodeURIComponent(button.dataset.id)}/revoke`, {}); await keys(); }
    catch (error) { showStatus(error.message, "error"); }
  });
}
async function filesPage() {
  const files = await request("/v1/files");
  app.innerHTML = page("MODEL LIBRARY", "Your files.", "Uploads belong only to your account. Open a ready model to inspect it.", `
    <section class="panel"><form id="upload"><label>Choose a 3D or CAD file<input name="file" type="file" accept=".obj,.stl,.ply,.glb,.gltf,.step,.stp" required></label><button>Upload and analyze</button></form></section>
    <section class="panel"><h2>Models</h2><div class="file-list">${files.length ? files.map((file) => `<div><a href="/playground?id=${encodeURIComponent(file.id)}">${escapeHtml(file.filename)}</a><span class="tag">${escapeHtml(file.status)}</span><button class="secondary delete-file" data-id="${escapeHtml(file.id)}">Delete</button></div>`).join("") : `<p class="muted">No files uploaded yet.</p>`}</div></section><p id="status" class="status" role="status"></p>`);
  document.querySelector("#upload").onsubmit = async (event) => {
    event.preventDefault(); showStatus("Uploading and analyzing…");
    try { const file = await request("/v1/files", { method: "POST", body: new FormData(event.currentTarget) }); location.assign(`/playground?id=${encodeURIComponent(file.id)}`); }
    catch (error) { showStatus(error.message, "error"); }
  };
  document.querySelectorAll(".delete-file").forEach((button) => button.onclick = async () => {
    if (!confirm("Delete this file and its stored source?")) return;
    try { await request(`/v1/files/${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" }); await filesPage(); }
    catch (error) { showStatus(error.message, "error"); }
  });
}
async function waitReady(id) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const file = await request(`/v1/files/${encodeURIComponent(id)}`);
    if (file.status === "ready") return file;
    if (file.status === "failed") throw new Error(file.error || "Analysis failed");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Analysis is still running. Reopen this model in a moment.");
}
async function showPreview(id) {
  const response = await fetch(`${api}${pathFor(id, "preview")}`, { credentials: "include" });
  if (!response.ok) throw new Error(`Preview unavailable (${response.status})`);
  const viewer = document.querySelector("#viewer");
  const url = URL.createObjectURL(await response.blob());
  if (viewer.dataset.blobUrl) URL.revokeObjectURL(viewer.dataset.blobUrl);
  viewer.dataset.blobUrl = url;
  viewer.setAttribute("src", url);
}
async function playground() {
  const files = await request("/v1/files");
  const requested = new URLSearchParams(location.search).get("id");
  app.innerHTML = page("PLAYGROUND", "Ask the model.", "Upload a file, choose a query, and inspect the result from Reality.", `
    <div class="workbench"><section class="panel controls"><form id="upload"><label>Upload a model<input name="file" type="file" accept=".obj,.stl,.ply,.glb,.gltf,.step,.stp" required></label><button>Upload</button></form>
    <label>Selected model<select id="model"><option value="">Choose a model</option>${files.map((file) => `<option value="${escapeHtml(file.id)}" ${file.id === requested ? "selected" : ""}>${escapeHtml(file.filename)} · ${escapeHtml(file.status)}</option>`).join("")}</select></label>
    <form id="query"><label>Query<select name="query"><option value="summary">Summary</option><option value="parts">Parts</option><option value="measure">Measure part</option><option value="topology">Topology</option><option value="distance">Distance</option><option value="clearance">Clearance</option><option value="intersections">Intersections</option></select></label>
    <label>First part<input name="first" placeholder="part name"></label><label>Second part<input name="second" placeholder="part name"></label><button>Run query</button></form>
    <form id="edit"><label>Edit operations (JSON)<textarea name="operations" rows="5" spellcheck="false">[{"operation":"translate","parameters":{"target":"part-name","x":1.0}}]</textarea></label><button class="secondary">Apply validated edit</button></form></section>
    <section class="results"><div class="viewer-panel"><div class="result-head"><span>3D preview</span><small>Display only · calculations use source geometry</small></div><model-viewer id="viewer" camera-controls auto-rotate alt="Selected model preview"></model-viewer></div>
    <div class="result-head"><span>Reality response</span><span id="status" class="status">Ready</span></div><pre id="output" aria-live="polite">Run a query to see the result.</pre></section></div>`);
  const model = document.querySelector("#model");
  async function selectModel(id) {
    if (!id) return;
    showStatus("Analyzing model…");
    try { await waitReady(id); showOutput(await request(pathFor(id, "summary"))); showStatus("Model ready", "success");
      await showPreview(id).catch((error) => showStatus(error.message, "error"));
    } catch (error) { showStatus(error.message, "error"); showOutput(error.message); }
  }
  model.onchange = () => selectModel(model.value);
  document.querySelector("#upload").onsubmit = async (event) => {
    event.preventDefault(); showStatus("Uploading…");
    try { const uploaded = await request("/v1/files", { method: "POST", body: new FormData(event.currentTarget) });
      model.add(new Option(uploaded.filename, uploaded.id, true, true)); await selectModel(uploaded.id);
    } catch (error) { showStatus(error.message, "error"); }
  };
  document.querySelector("#query").onsubmit = async (event) => {
    event.preventDefault(); if (!model.value) return showStatus("Choose a model first.", "error");
    const values = new FormData(event.currentTarget);
    const kind = values.get("query"); const first = values.get("first").trim(); const second = values.get("second").trim();
    try { showStatus("Running query…"); let result;
      if (kind === "summary" || kind === "parts") result = await request(pathFor(model.value, kind));
      else if (kind === "measure") { if (!first) throw new Error("Enter the first part name."); result = await post(pathFor(model.value, "measure"), { part: first }); }
      else if (kind === "topology") result = await post(pathFor(model.value, "topology"), { part: first || null });
      else if (kind === "intersections") result = await post(pathFor(model.value, "intersections"), {});
      else { if (!first || !second) throw new Error("Enter both part names."); result = await post(pathFor(model.value, kind), { first, second }); }
      showOutput(result); showStatus("Query complete", "success");
    } catch (error) { showOutput(error.message); showStatus(error.message, "error"); }
  };
  document.querySelector("#edit").onsubmit = async (event) => {
    event.preventDefault(); if (!model.value) return showStatus("Choose a model first.", "error");
    try { const operations = JSON.parse(new FormData(event.currentTarget).get("operations"));
      if (!Array.isArray(operations) || !operations.length) throw new Error("Enter a non-empty operation list.");
      if (!confirm("Apply these operations as a new model version?")) return;
      showStatus("Validating edit…");
      const job = await post(pathFor(model.value, "edits"), { operations });
      let current = job;
      for (let attempt = 0; attempt < 40 && !["ready", "failed"].includes(current.status); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500)); current = await request(`/v1/edits/${encodeURIComponent(job.id)}`);
      }
      if (current.status !== "ready" || !current.result_model_id) throw new Error(current.error || "Edit is still processing.");
      await waitReady(current.result_model_id);
      showOutput({ edit: current, summary: await request(pathFor(current.result_model_id, "summary")) });
      model.add(new Option(`Edited · ${current.result_model_id.slice(0, 8)}`, current.result_model_id, true, true));
      await showPreview(current.result_model_id); showStatus("New version ready", "success");
    } catch (error) { showOutput(error.message); showStatus(error.message, "error"); }
  };
  if (requested) await selectModel(requested);
}
const route = location.pathname;
if (route === "/") home();
else if (route === "/docs") docs();
else if (route === "/dashboard/keys") guarded(keys);
else if (route === "/dashboard/files") guarded(filesPage);
else if (route === "/playground") guarded(playground);
else guarded(dashboard);
