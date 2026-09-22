"""Rebuild static/index.html with all fixes applied correctly"""
import re

p = 'static/index.html'
html = open(p, encoding='utf-8').read()

# Extract the CSS and HTML structure (everything before <script>)
m = re.search(r'^(.*?)<script>(.*?)</script>(.*?)$', html, re.DOTALL)
if not m:
    print('Could not parse HTML')
    exit(1)

before_script = m.group(1)
old_script = m.group(2)
after_script = m.group(3)

# Write a completely new script that's clean and correct
new_script = r"""
// ---- constants ----
const API = window.location.origin + "/api";
const PREFIX = window.location.origin + "/";
const STATE = {
  panels: [],
  groups: [],
  activeTab: null,
  skin: "city",
  theme: "dark",
  filter: "",
  nextId: 1,
};

// ---- tiny helpers ----
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const path = window.location.pathname + window.location.search;
const toast = (msg, err=false) => {
  const t = $("#toast");
  t.textContent = msg || "done";
  t.classList.toggle("err", !!err);
  t.classList.add("show");
  clearTimeout(t._t);
  t._t = setTimeout(()=>t.classList.remove("show"), 2200);
};
const api = async (url, opts={}) => {
  const r = await fetch(url, { headers: {"Content-Type":"application/json"}, ...opts });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t.slice(0,200)}`); }
  return r.json();
};
const get = qs => api(API + "/" + qs);
const post = (ep, body) => api(API + "/" + ep, { method:"POST", body: JSON.stringify(body) });

// ---- panel system ----
function createPanel(type, title, opts={}) {
  const id = STATE.nextId++;
  const p = {
    id, type, title: title || typeLabel(type),
    x: opts.x || 20 + (STATE.panels.length % 4) * 14,
    y: opts.y || 60 + (Math.floor(STATE.panels.length / 4) % 3) * 80,
    w: opts.w || (type==="topology" ? 640 : type==="cabinet" ? 480 : 360),
    h: opts.h || (type==="topology" ? 420 : 340),
    group: opts.group || null,
    config: opts.config || {},
    color: typeColor(type),
  };
  STATE.panels.push(p);
  renderPanel(p);
  positionPanel(p);
  attachPanelEvents(p);
  savePanels();
  return p;
}
function renderPanel(p) {
  let el = document.getElementById("panel-"+p.id);
  if (!el) {
    el = document.createElement("div");
    el.className = "panel" + (p.group ? " grouped" : "") + (p.solo?" solo":"");
    el.id = "panel-"+p.id;
    el.style.left = p.x+"px"; el.style.top = p.y+"px";
    el.style.width = p.w+"px"; el.style.height = p.h+"px";
    el.dataset.color = p.color;
    el.innerHTML = `<div class="ph"><span>${esc(p.title)}</span><span class="close" data-act="close">×</span></div><div class="pb" id="pb-${p.id}"></div>`;
    if (p.group) $("#group-panels-"+p.group).appendChild(el);
    else $("#workspace").appendChild(el);
  }
  $("#pb-"+p.id).innerHTML = renderPanelBody(p);
}
function renderPanelBody(p) {
  const renderers = {
    input: renderInputPanel, stream: renderStreamPanel, search: renderSearchPanel,
    chunks: renderChunksPanel, topology: renderTopologyPanel, cabinet: renderCabinetPanel,
    files: renderFilesPanel, parse: renderParsePanel, skin: renderSkinPanel,
    dashboard: renderDashboardPanel, cluster: renderClusterPanel, wiki: renderWikiPanel,
    timeline: renderTimelinePanel, wordcloud: renderWordCloudPanel, custom: renderCustomPanel,
  };
  const fn = renderers[p.type];
  if (!fn) return `<div class="empty"><div class="big">?</div>unsupported panel type: ${esc(p.type)}</div>`;
  return fn(p);
}
function positionPanel(p) {
  const el = document.getElementById("panel-"+p.id);
  if (!el) return;
  el.style.left = p.x+"px"; el.style.top = p.y+"px";
  el.style.width = p.w+"px"; el.style.height = p.h+"px";
}
function attachPanelEvents(p) {
  const el = $("#panel-"+p.id);
  if (!el) return;
  el.querySelector(".ph .close").onclick = () => removePanel(p.id);
}
function removePanel(id) {
  STATE.panels = STATE.panels.filter(p => p.id !== id);
  const el = $("#panel-"+id);
  if (el) el.remove();
  for (const g of STATE.groups) { g.panel_ids = g.panel_ids.filter(i => i !== id); }
  savePanels();
}
function typeLabel(t) {
  const L = { input:"Input", stream:"Stream", search:"Search", chunks:"Chunks",
    topology:"Topography", cabinet:"Cabinet", files:"Files", parse:"Parse",
    skin:"Skin Editor", dashboard:"Dashboard", cluster:"Cluster",
    wiki:"Wiki Map", timeline:"Timeline", wordcloud:"Word Cloud", custom:"Custom" };
  return L[t] || t;
}
function typeColor(t) {
  const C = { input:"input", stream:"recent", search:"search", chunks:"cluster",
    topology:"topology", cabinet:"cabinet", files:"files", parse:"parse",
    skin:"skin", dashboard:"summary", cluster:"cluster", wiki:"wiki",
    timeline:"timeline", wordcloud:"wordcloud", custom:"custom" };
  return C[t] || "summary";
}
function colorFor(c) {
  const M = { input:"#6C63FF", recent:"#FFA94D", search:"#43B581", cluster:"#FF6584",
    topology:"#6C63FF", cabinet:"#6B9BD2", files:"#43B581", parse:"#FFA94D",
    skin:"#845EF7", summary:"#6C63FF", wiki:"#6B9BD2", timeline:"#845EF7",
    wordcloud:"#2EC4B6", custom:"#FF871E" };
  return M[c] || "#6C63FF";
}
function savePanels() {
  try { localStorage.setItem("signum_v11_panels", JSON.stringify({panels:STATE.panels, groups:STATE.groups, activeTab:STATE.activeTab})); } catch(e) {}
}
function loadPanels() {
  try {
    const raw = localStorage.getItem("signum_v11_panels");
    if (!raw) return;
    const d = JSON.parse(raw);
    STATE.panels = d.panels || []; STATE.groups = d.groups || []; STATE.activeTab = d.activeTab;
  } catch(e) {}
}

/* ---- Panel renderers ---- */

function renderInputPanel(p) {
  setTimeout(() => {
    $("#input-send").onclick = async () => {
      const text = $("#input-text").value.trim();
      if (!text) return toast("nothing to send", true);
      const el = $("#input-result");
      el.textContent = "processing…"; el.style.color = "var(--accent)";
      try {
        const r = await post("input", {text, parse:false});
        el.textContent = `note ${r.note_id} · ${r.chunks_count} chunks · ${r.cluster_count} clusters`;
        el.style.color = "var(--green)"; refreshAll(); toast("input processed");
      } catch(e) { el.textContent = "error: " + e.message; el.style.color = "var(--danger)"; toast(e.message, true); }
    };
    $("#input-parse").onclick = async () => {
      const text = $("#input-text").value.trim();
      if (!text) return toast("nothing to parse", true);
      const el = $("#input-result"); el.textContent = "parsing + saving…";
      try {
        const r = await post("parse_and_save", {text, path:"/input_parse.md"});
        el.textContent = r.ok ? `saved note ${r.note_id} · ${r.chunks_count} chunks` : "error: "+r.error;
        el.style.color = r.ok ? "var(--green)" : "var(--danger)"; refreshAll();
      } catch(e) { el.textContent = "error: " + e.message; el.style.color = "var(--danger)"; toast(e.message, true); }
    };
    $("#input-clear").onclick = () => { $("#input-text").value = ""; $("#input-result").textContent = ""; };
  }, 10);
  return `
    <textarea id="input-text" style="width:100%;min-height:140px;display:block" placeholder="Paste text here — stream of consciousness, notes, journal entry, thoughts..."></textarea>
    <div class="panel-actions">
      <button id="input-send">Send to Signum</button>
      <button class="ghost sm" id="input-parse">Parse → DB</button>
      <button class="ghost sm" id="input-clear">Clear</button>
    </div>
    <div id="input-result" style="margin-top:8px;font-size:11px;color:var(--muted);font-family:var(--font)"></div>
  `;
}

function renderStreamPanel(p) {
  setTimeout(() => {
    $("#stream-refresh").onclick = () => renderStreamPanel(p);
    $("#stream-filter-go").onclick = () => { STATE.filter = $("#stream-filter").value.trim(); renderStreamList(p); };
    $("#stream-clear-filter").onclick = () => { STATE.filter = ""; $("#stream-filter").value = ""; renderStreamList(p); };
    renderStreamList(p);
  }, 10);
  return `
    <div class="btn-row">
      <input id="stream-filter" placeholder="filter: @tag, date, text…" style="flex:1;font-size:11px">
      <button class="ghost sm" id="stream-filter-go">Filter</button>
      <button class="ghost sm" id="stream-clear-filter">Clear</button>
    </div>
    <div id="stream-list" style="flex:1;overflow:auto;min-height:120px">
      <div class="empty"><div class="big">💬</div>No stream entries yet. Use Input panel to send text.</div>
    </div>
    <div class="btn-row" style="margin-top:6px"><button class="ghost sm" id="stream-refresh">Refresh</button></div>
  `;
}
function renderStreamList(p) {
  get("notes?limit=50").then(r => {
    const list = $("#stream-list"); if (!list) return;
    let notes = r.notes || [];
    if (STATE.filter) {
      const f = STATE.filter.toLowerCase();
      notes = notes.filter(n => {
        if (n.filename && n.filename.toLowerCase().includes(f)) return true;
        if (n.tags) { for (const t of n.tags) if (t.toLowerCase().includes(f)) return true; }
        return false;
      });
    }
    if (notes.length === 0) {
      list.innerHTML = `<div class="empty"><div class="big">${STATE.filter?"🔍":"💬"}</div>${STATE.filter?"No notes match that filter.":"No stream entries yet."}</div>`;
      return;
    }
    list.innerHTML = notes.slice(0, 40).map(n => `
      <div class="stream-msg">
        <div class="sm-head"><span>${esc(n.filename||"note")}</span><span>${n.modified?new Date(n.modified).toLocaleString():""}</span></div>
        <div class="sm-body">${esc((n.content||"").slice(0, 400))}</div>
        ${n.tags && n.tags.length ? `<div class="sm-tags">${n.tags.map(t=>"#"+esc(t)).join(" ")}</div>` : ""}
      </div>
    `).join("");
  }).catch(e => { const l=$("#stream-list"); if(l) l.innerHTML=`<div class="empty">error: ${esc(e.message)}</div>`; });
}

function renderSearchPanel(p) {
  setTimeout(() => {
    $("#search-go").onclick = async () => {
      const q = $("#search-q").value.trim();
      if (!q) return toast("empty query", true);
      $("#search-results").innerHTML = '<div class="empty"><div class="spinner"></div>searching…</div>';
      try {
        const r = await get("search?q="+encodeURIComponent(q)+"&engine="+$("#search-engine").value+"&limit="+encodeURIComponent($("#search-limit").value||10));
        const res = r.results || [];
        if (res.length === 0) { $("#search-results").innerHTML = `<div class="empty">no results for "${esc(q)}"</div>`; return; }
        $("#search-results").innerHTML = res.map(x => `
          <div class="chunk-card" style="border-left-color:var(--green)">
            <div class="cid">${esc(x.chunk_id)} · ${esc(x.filename)} · sim ${x.similarity}</div>
            <div class="ctext">${esc(x.text||"").slice(0,300)}</div>
            <div class="cmeta">${esc(x.path)} · ${x.start}-${x.end} · cluster ${x.cluster}</div>
          </div>
        `).join("");
      } catch(e) { $("#search-results").innerHTML = `<div class="empty" style="color:var(--danger)">error: ${esc(e.message)}</div>`; }
    };
  }, 10);
  return `
    <div class="btn-row">
      <input id="search-q" placeholder="search text…" style="flex:1">
      <select id="search-engine"><option value="semantic">semantic</option><option value="keyword">keyword</option></select>
      <input id="search-limit" type="number" value="10" min="1" max="100" style="width:50px">
      <button id="search-go">Search</button>
    </div>
    <div id="search-results" style="margin-top:8px;max-height:300px;overflow:auto">
      <div class="empty"><div class="big">🔍</div>Type a query and hit Search.</div>
    </div>
  `;
}

function renderChunksPanel(p) {
  setTimeout(() => {
    $("#chunks-refresh").onclick = () => refreshChunksList(p);
    refreshChunksList(p);
  }, 10);
  return `
    <div class="btn-row">
      <select id="chunks-note" style="flex:1"><option value="">— all notes —</option></select>
      <button class="ghost sm" id="chunks-refresh">Refresh</button>
    </div>
    <div id="chunks-list" style="margin-top:6px;max-height:340px;overflow:auto">
      <div class="empty"><div class="big">📝</div>Load a note to see its chunks.</div>
    </div>
  `;
}
function refreshChunksList(p) {
  get("notes").then(r => {
    const sel = $("#chunks-note"); if (!sel) return;
    sel.innerHTML = '<option value="">— all notes —</option>' + (r.notes||[]).map(n => `<option value="${esc(n.id)}">${esc(n.filename)}</option>`).join("");
    sel.onchange = () => renderChunksForNote(p, sel.value);
    renderChunksForNote(p, null);
  }).catch(e => toast(e.message, true));
}
function renderChunksForNote(p, noteId) {
  const list = $("#chunks-list"); if (!list) return;
  if (!noteId) { list.innerHTML = `<div class="empty"><div class="big">📝</div>Select a note above to see its chunks.</div>`; return; }
  get("chunks?note_id="+encodeURIComponent(noteId)).then(r => {
    const cs = r.chunks || r || [];
    if (!Array.isArray(cs) || cs.length === 0) { list.innerHTML = `<div class="empty">no chunks found</div>`; return; }
    list.innerHTML = cs.map(c => `
      <div class="chunk-card">
        <div class="cid">chunk ${esc(c.id)} · ${c.start}-${c.end} · cluster ${c.cluster||-1} · bs ${c.boundary_strength||0}</div>
        <div class="ctext">${esc((c.text||"").slice(0,400))}</div>
        <div class="cmeta">${(c.tags||[]).map(t=>"#"+esc(t)).join(" ")}</div>
      </div>
    `).join("");
  }).catch(e => { list.innerHTML = `<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
}

function renderTopologyPanel(p) {
  setTimeout(() => {
    $("#topo-reset").onclick = () => { _topoRotX = 0.4; _topoRotY = 0; _topoZoom = 1; };
    $("#topo-refresh").onclick = () => refreshTopology();
    initTopology(p);
  }, 50);
  return `
    <div class="canvas-wrap" id="topo-canvas-wrap"><canvas id="topo-canvas"></canvas></div>
    <div class="btn-row" style="padding:6px;border-top:1px solid var(--border)">
      <span style="font-size:11px;color:var(--muted)">drag to rotate · scroll to zoom</span>
      <button class="ghost sm" id="topo-reset">Reset</button>
      <button class="ghost sm" id="topo-refresh">Refresh</button>
    </div>
  `;
}

function renderCabinetPanel(p) {
  setTimeout(() => {
    $("#cabinet-refresh").onclick = () => renderCabinetPanel(p);
    get("clusters").then(r => {
      const host = $("#cabinet-view"); if (!host) return;
      const cls = r.clusters || [];
      if (cls.length === 0) { host.innerHTML = `<div class="empty"><div class="big">🗄</div>No clusters yet.</div>`; return; }
      host.innerHTML = cls.map(c => `<div class="card" style="border-left:3px solid var(--blue)"><h3>🗂 ${esc(c.name)} <span style="float:right;color:var(--muted);font-size:11px">${c.member_count||0} papers</span></h3><div class="meta">id: ${c.id} · tags: ${(c.tags||[]).map(t=>"#"+esc(t)).join(" ")}</div></div>`).join("");
    }).catch(e => { const h=$("#cabinet-view"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div id="cabinet-view" style="flex:1;overflow:auto"><div class="empty"><div class="big">🗄</div>Loading cabinet…</div></div><div class="btn-row" style="padding:6px;border-top:1px solid var(--border)"><span style="font-size:11px;color:var(--muted)">file cabinet</span><button class="ghost sm" id="cabinet-refresh">Refresh</button></div>`;
}

function renderFilesPanel(p) {
  setTimeout(() => {
    $("#files-refresh").onclick = () => renderFilesPanel(p);
    get("folders").then(r => {
      const host = $("#files-tree"); if (!host) return;
      const folders = r.folders || ["/"];
      let html = '';
      for (const f of folders) { html += `<div class="ft-item${f==='/'?' active':''}" data-folder="${esc(f)}"><span class="ft-icon">📁</span>${esc(f)}</div>`; }
      host.innerHTML = html;
      $$(".ft-item", host).forEach(el => { el.onclick = () => $$(".ft-item", host).forEach(e => e.classList.remove("active")); el.classList.add("active"); });
    }).catch(e => { const h=$("#files-tree"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div class="btn-row"><button class="ghost sm" id="files-refresh">Refresh</button><span style="font-size:11px;color:var(--muted);align-self:center">vault folders</span></div><div id="files-tree" class="folder-tree" style="margin-top:8px;flex:1;overflow:auto"><div class="empty"><div class="big">📁</div>Loading…</div></div>`;
}

function renderParsePanel(p) {
  setTimeout(() => {
    $("#parse-parse").onclick = async () => {
      const text = $("#parse-text").value.trim(); if (!text) return toast("empty", true);
      try { const r = await post("parse", {text}); displayParseResult(r, $("#parse-result")); } catch(e) { $("#parse-result").innerHTML = `<div class="empty" style="color:var(--danger)">error: ${esc(e.message)}</div>`; }
    };
    $("#parse-save").onclick = async () => {
      const text = $("#parse-text").value.trim(); if (!text) return toast("empty", true);
      try { const r = await post("parse_and_save", {text, path:"/parse_"+Date.now()+".md"}); if (r.ok) { displayParseResult(r, $("#parse-result")); toast("saved note "+r.note_id); refreshAll(); } else { $("#parse-result").innerHTML = `<div class="empty" style="color:var(--danger)">${esc(r.error)}</div>`; } } catch(e) { $("#parse-result").innerHTML = `<div class="empty" style="color:var(--danger)">error: ${esc(e.message)}</div>`; }
    };
    $("#parse-clear").onclick = () => { $("#parse-text").value=""; $("#parse-result").innerHTML='<div class="empty"><div class="big">⚡</div>Rules-only parser</div>'; };
  }, 10);
  return `<textarea id="parse-text" style="width:100%;min-height:120px;display:block" placeholder="Text to parse — [[wikilinks]], #tags, dates, names auto-detected"></textarea><div class="panel-actions"><button id="parse-parse">Parse</button><button class="ghost sm" id="parse-save">Parse + Save</button><button class="ghost sm" id="parse-clear">Clear</button></div><div id="parse-result" style="margin-top:8px"><div class="empty"><div class="big">⚡</div>Rules-only parser — no API key needed.</div></div>`;
}

function renderSkinPanel(p) {
  setTimeout(() => {
    get("skins").then(r => { const sel = $("#skin-editor-select"); sel.innerHTML = (r.skins||[]).map(s => `<option value="${esc(s.name)}">${esc(s.name)} (${s.kind})</option>`).join(""); }).catch(()=>{});
    $("#skin-editor-refresh").onclick = () => renderSkinPanel(p);
    $("#skin-editor-load").onclick = () => {};
    $("#skin-editor-save").onclick = () => toast("save not implemented");
    $("#skin-editor-new").onclick = () => { $("#skin-editor-text").value = "Render = function(ctx, clusters, proj, t, pw, ph, pts) {\n  // your code here\n};"; };
  }, 50);
  return `<div class="btn-row"><select id="skin-editor-select" style="flex:1"></select><button class="ghost sm" id="skin-editor-refresh">Refresh</button><button id="skin-editor-new">New</button></div><div class="editor"><div class="toolbar"><button id="skin-editor-load">Load</button><button id="skin-editor-save">Save</button><span style="flex:1"></span><span id="skin-editor-info" style="font-size:10px;color:var(--muted)"></span></div><textarea id="skin-editor-text" spellcheck="false" placeholder="// skin JS code"></textarea></div>`;
}

function renderDashboardPanel(p) {
  setTimeout(() => {
    $("#dash-refresh").onclick = () => renderDashboardPanel(p);
    Promise.all([get("status"), get("clusters"), get("notes?limit=5")]).then(([st, cl, ns]) => {
      const host = $("#dash-body"); if (!host) return;
      const notes = ns.notes || []; const clusters = cl.clusters || [];
      host.innerHTML = `<div class="card"><h3>Status</h3><div class="meta">pid: ${st.pid} · embed: ${st.embed_mode}</div></div><div class="card"><h3>Statistics</h3><div class="meta">notes: ${notes.length} · clusters: ${clusters.length}</div></div><div class="card"><h3>Recent Notes</h3>${notes.slice(0,5).map(n => `<div style="padding:4px 0;border-bottom:1px solid var(--border)"><span style="color:var(--accent)">${esc(n.filename)}</span><span style="color:var(--muted);font-size:10px">${n.chunks_count||0}ch</span></div>`).join("")||"no notes"}</div><div class="card"><h3>Clusters</h3>${clusters.length ? clusters.map(c => `<div style="padding:4px 0;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:center"><span style="width:8px;height:8px;border-radius:50%;background:var(--blue)"></span><span>${esc(c.name)}</span><span style="color:var(--muted);font-size:10px">${c.member_count}ch</span></div>`).join("") : "no clusters"}</div>`;
    }).catch(e => { const h=$("#dash-body"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div id="dash-body"><div class="empty"><div class="big">📊</div>Loading dashboard…</div></div><div class="btn-row" style="padding:6px;border-top:1px solid var(--border)"><button class="ghost sm" id="dash-refresh">Refresh</button></div>`;
}

function renderClusterPanel(p) {
  setTimeout(() => {
    $("#cluster-refresh").onclick = () => renderClusterPanel(p);
    get("clusters").then(r => {
      const host = $("#cluster-list"); if (!host) return;
      const cls = r.clusters || [];
      if (cls.length === 0) { host.innerHTML = `<div class="empty">no clusters yet</div>`; return; }
      host.innerHTML = cls.map(c => `<div class="card" style="border-left:3px solid var(--accent-2)"><div style="display:flex;align-items:center;gap:8px"><span style="width:10px;height:10px;border-radius:50%;background:var(--accent-2)"></span><span style="font-weight:600">${esc(c.name)}</span><span style="color:var(--muted);font-size:10px">${c.member_count} members</span><span style="margin-left:auto;font-size:10px;color:var(--muted)">id:${c.id}</span></div><div class="meta">tags: ${(c.tags||[]).map(t=>"#"+esc(t)).join(" ")}</div></div>`).join("");
    }).catch(e => { const h=$("#cluster-list"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div class="btn-row"><span style="font-size:11px;color:var(--muted)">clusters</span><button class="ghost sm" id="cluster-refresh">Refresh</button></div><div id="cluster-list" style="margin-top:6px;max-height:340px;overflow:auto"><div class="empty"><div class="big">🔵</div>Loading…</div></div>`;
}

function renderWikiPanel(p) {
  setTimeout(() => {
    $("#wiki-refresh").onclick = () => renderWikiPanel(p);
    get("notes?limit=100").then(r => {
      const host = $("#wiki-body"); if (!host) return;
      const linkRe = /\[\[([^\]]+)\]\]/g; const links = [];
      for (const n of r.notes || []) { let m; const c = n.content||""; while ((m = linkRe.exec(c)) !== null) links.push({from:n.filename, target:m[1]}); }
      if (links.length === 0) { host.innerHTML = `<div class="empty"><div class="big">🔗</div>No wikilinks found. Use [[target]] syntax.</div>`; return; }
      const byTarget = {}; for (const l of links) (byTarget[l.target] ||= []).push(l.from);
      host.innerHTML = Object.entries(byTarget).map(([t,sources]) => `<div class="card" style="border-left:3px solid var(--blue)"><div style="font-weight:600;color:var(--blue)">[[${esc(t)}]]</div><div class="meta">referenced by ${sources.length}: ${sources.slice(0,5).map(s=>"→ "+esc(s)).join(", ")}</div></div>`).join("");
    }).catch(e => { const h=$("#wiki-body"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div class="btn-row"><span style="font-size:11px;color:var(--muted)">wiki map — wikilink graph</span><button class="ghost sm" id="wiki-refresh">Refresh</button></div><div id="wiki-body" style="flex:1;overflow:auto"><div class="empty"><div class="big">🔗</div>Loading wikilinks…</div></div>`;
}

function renderTimelinePanel(p) {
  setTimeout(() => {
    $("#timeline-refresh").onclick = () => renderTimelinePanel(p);
    get("notes?limit=100").then(r => {
      const host = $("#timeline-body"); if (!host) return;
      const notes = (r.notes||[]).sort((a,b) => (b.modified||"").localeCompare(a.modified||""));
      if (notes.length === 0) { host.innerHTML = `<div class="empty">no notes</div>`; return; }
      host.innerHTML = notes.slice(0,20).map((n,i) => `<div style="display:flex;gap:8px;align-items:flex-start;padding:4px 0;border-bottom:1px solid var(--border)"><div style="width:30px;height:30px;border-radius:50%;background:${i===0?"var(--accent)":"var(--panel-2)"};border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:10px;color:${i===0?"#fff":"var(--muted)"};flex-shrink:0">${i+1}</div><div style="flex:1"><div style="font-size:12px"><span style="color:var(--accent)">${esc(n.filename)}</span></div><div style="font-size:10px;color:var(--muted)">${n.chunks_count||0}ch</div></div></div>`).join("");
    }).catch(e => { const h=$("#timeline-body"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div class="btn-row"><span style="font-size:11px;color:var(--muted)">timeline</span><button class="ghost sm" id="timeline-refresh">Refresh</button></div><div id="timeline-body" style="flex:1;overflow:auto"><div class="empty"><div class="big">⏱</div>Loading…</div></div>`;
}

function renderWordCloudPanel(p) {
  setTimeout(() => {
    $("#wc-refresh").onclick = () => renderWordCloudPanel(p);
    get("search?q=&limit=200").then(r => {
      const host = $("#wc-body"); if (!host) return;
      const stop = new Set(["the","a","an","and","or","but","in","on","at","to","for","of","with","by","from","is","are","was","were","be","been","have","has","had","do","does","did","will","would","could","should","may","might","can","this","that","these","those","my","your","his","her","its","our","their"]);
      const freq = {};
      for (const c of r.results||[]) { const words = (c.text||"").toLowerCase().split(/[^a-z0-9_]+/); for (const w of words) { if (w.length<2||stop.has(w)) continue; freq[w]=(freq[w]||0)+1; } }
      const sorted = Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,80);
      if (sorted.length===0) { host.innerHTML=`<div class="empty" style="width:100%">no words</div>`; return; }
      const max=sorted[0][1];
      host.innerHTML = sorted.map(([w,c]) => `<span style="font-size:${10+(c/max)*24}px;color:hsl(${w.length*30%360},70%,70%);padding:2px 6px;border-radius:4px;cursor:pointer" title="${c}×">${esc(w)}</span>`).join("");
    }).catch(e => { const h=$("#wc-body"); if(h) h.innerHTML=`<div class="empty" style="color:var(--danger)">${esc(e.message)}</div>`; });
  }, 50);
  return `<div class="btn-row"><span style="font-size:11px;color:var(--muted)">word cloud</span><button class="ghost sm" id="wc-refresh">Refresh</button></div><div id="wc-body" style="flex:1;overflow:auto;display:flex;flex-wrap:wrap;align-content:flex-start;gap:6px;padding:10px"><div class="empty" style="width:100%"><div class="big">☁</div>Loading…</div></div>`;
}

function renderCustomPanel(p) {
  return `<div class="empty"><div class="big">🧩</div>Custom panel — type: ${esc(p.type)}</div>`;
}

/* ---- topology canvas ---- */
let _topoCanvas = null, _topoCtx = null, _topoPoints = [], _topoClusters = [];
let _topoRotX = 0.4, _topoRotY = 0, _topoZoom = 1, _topoMouse = {x:0,y:0,down:false,px:0,py:0};

function initTopology(p) {
  const cv = $("#topo-canvas"); const wrap = $("#topo-canvas-wrap");
  if (!cv || !wrap) return;
  const rect = wrap.getBoundingClientRect();
  cv.width = rect.width * devicePixelRatio; cv.height = rect.height * devicePixelRatio;
  cv.style.width = rect.width+"px"; cv.style.height = rect.height+"px";
  _topoCanvas = cv; _topoCtx = cv.getContext("2d"); _topoCtx.scale(devicePixelRatio, devicePixelRatio);
  cv.onmousedown = e => { _topoMouse.down = true; _topoMouse.px = e.clientX; _topoMouse.py = e.clientY; };
  window.onmouseup = () => { _topoMouse.down = false; };
  cv.onmousemove = e => { if (!_topoMouse.down) return; _topoRotY += (e.clientX-_topoMouse.px)*0.01; _topoRotX += (e.clientY-_topoMouse.py)*0.01; _topoRotX=Math.max(-1.4,Math.min(1.4,_topoRotX)); _topoMouse.px=e.clientX; _topoMouse.py=e.clientY; };
  cv.onwheel = e => { e.preventDefault(); _topoZoom *= (1+e.deltaY*0.001); _topoZoom=Math.max(0.2,Math.min(5,_topoZoom)); };
  refreshTopology();
  requestAnimationFrame(()=>drawLoop(p));
}
function drawLoop(p) {
  if (_topoCanvas && _topoCtx) drawTopology();
  requestAnimationFrame(()=>drawLoop(p));
}
function drawTopology() {
  const ctx = _topoCtx, cv = _topoCanvas; if (!ctx||!cv) return;
  const W=cv.width/devicePixelRatio, H=cv.height/devicePixelRatio;
  ctx.fillStyle="#0e0e12"; ctx.fillRect(0,0,W,H);
  if (_topoPoints.length===0) { ctx.fillStyle="#8888a0"; ctx.font="12px "+getComputedStyle(document.body).fontFamily; ctx.textAlign="center"; ctx.fillText("no data — send some text first",W/2,H/2); return; }
  const colors=["#6C63FF","#FF6584","#43B581","#FFA94D","#6B9BD2","#845EF7","#2EC4B6","#FF871E","#E53935","#7C4DFF"];
  const proj = (x,y,z) => { const cx=Math.cos(_topoRotX),sx=Math.sin(_topoRotX),cy=Math.cos(_topoRotY),sy=Math.sin(_topoRotY); let y1=y*cy-z*sy,z1=y*sy+z*cy,y2=y1*cx-z1*sx,z2=y1*sx+z1*cx,s=1/(1+z2*0.05)*_topoZoom*60; return {x:W/2+x*s,y:H/2+y2*s,z:z2,s}; };
  const pts = _topoPoints.map(p => { const pp=proj(p.x,p.y,p.z); return {...p,px:pp.x,py:pp.y,pz:pp.z,ps:pp.s}; }).sort((a,b)=>a.pz-b.pz);
  for (const p of pts) { ctx.beginPath(); ctx.arc(p.px,p.py,Math.max(2,Math.min(8,p.ps*0.5)),0,Math.PI*2); ctx.fillStyle=colors[p.cluster%colors.length]; ctx.globalAlpha=0.7+0.3*(1/(1+p.pz*0.1)); ctx.fill(); ctx.globalAlpha=1; }
}
function refreshTopology() { get("topology").then(r => { _topoPoints=r.points||[]; _topoClusters=r.clusters||[]; }).catch(()=>{}); }

function refreshAll() { STATE.panels.filter(p => ["chunks","search","cluster","wiki","timeline","wordcloud","dashboard","cabinet","files"].includes(p.type)).forEach(p => renderPanel(p)); }

/* ---- workspace init ---- */
function initWorkspace() {
  localStorage.removeItem("signum_v11_panels");
  loadPanels();
  $("#topbar").innerHTML = `<div class="brand"><span class="dot"></span><span>Signum v11</span></div><div class="spacer"></div><div class="status"><span id="status-time">—</span><span id="status-chunks" class="pill">0 chunks</span><span id="status-clusters" class="pill">0 clusters</span></div>`;
  document.querySelector("#topbar .spacer").insertAdjacentHTML("afterend", '<select id="skin-select"></select>');
  get("skins").then(s => { const sel=$("#skin-select"); (s.skins||[]).forEach(x => { sel.innerHTML += `<option value="${x.name}">${x.name}${x.kind==="user"?" ★":""}</option>`; }); }).catch(()=>{});
  $("#skin-select").onchange = () => { STATE.skin = $("#skin-select").value; refreshTopology(); };
  setInterval(async () => { try { const s=await get("status"); $("#status-time").textContent=new Date(s.time).toLocaleTimeString(); } catch(e){} }, 5000);
  document.querySelector("#topbar .spacer").insertAdjacentHTML("afterend", '<div id="panel-add-bar" style="display:flex;gap:4px;align-items:center"></div>');
  ["input","stream","search","chunks","topology","cabinet","files","parse","cluster"].forEach(t => $("#panel-add-bar").innerHTML += `<button class="ghost sm" data-type="${t}">${t}</button>`);
  $$("#panel-add-bar button").forEach(b => b.onclick = () => createPanel(b.dataset.type, null, {x:20+Math.random()*200, y:60+Math.random()*120}));
  document.querySelector("#workspace").insertAdjacentHTML("afterend", '<div id="groups-host" style="padding:8px;overflow:auto;max-height:20vh;flex-shrink:0"></div>');
  if (STATE.panels.length === 0) {
    createPanel("input", null, {x:20, y:60, w:360, h:300});
    createPanel("search", null, {x:420, y:60, w:360, h:300});
    createPanel("topology", null, {x:20, y:400, w:640, h:420});
    createPanel("files", null, {x:700, y:60, w:320, h:300});
    createPanel("dashboard", null, {x:700, y:400, w:320, h:300});
  }
  refreshAll();
}

document.addEventListener("DOMContentLoaded", initWorkspace);
window.refreshAll = refreshAll;
window.refreshTopology = refreshTopology;
"""

# Reconstruct HTML
new_html = before_script + "<script>" + new_script + "</script>" + after_script
open(p, 'w', encoding='utf-8').write(new_html)
print(f"Rebuilt index.html ({len(new_html)} chars)")
