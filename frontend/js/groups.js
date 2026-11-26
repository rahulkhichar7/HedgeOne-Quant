/* =====================================================================
   Security groups ("playlists") + the shared security tree.

   The tree is used by the symbol picker, Bulk download and Universe test:
     • your groups on top, then the three built-in groups (Upstox / CoinDCX / Delta)
     • a group row shows only its name; click it to expand / collapse its securities
     • the group's checkbox selects / unselects all of it — ticking two groups selects A ∪ B
     • search finds any security on the platform
     • the ＋ on a row adds it to (or removes it from) any of your groups
   ===================================================================== */
import { api } from "./api.js";
import { $, $$, esc, toast } from "./ui.js";

export const G = { list: [], symbols: [], byName: new Map(), listeners: new Set(), sources: {} };

export function setSymbols(list) {
  G.symbols = list;
  G.byName = new Map(list.map((s) => [s.name, s]));
  _builtinCache = null;
  changed();
}
export async function loadGroups() {
  G.list = (await api.groups()).groups || [];
  changed();
}
function changed() { G.listeners.forEach((f) => { try { f(); } catch (e) { console.error(e); } }); }
export const onGroupsChange = (f) => G.listeners.add(f);

export const SRC_LABEL = { upstox: "Upstox", coindcx: "CoinDCX", delta: "Delta", csv: "CSV" };
const BUILTIN = [
  { id: "src:upstox", source: "upstox", label: "Stocks & indices", sub: "NSE · BSE — Upstox" },
  { id: "src:coindcx", source: "coindcx", label: "CoinDCX", sub: "crypto spot pairs" },
  { id: "src:delta", source: "delta", label: "Delta Exchange India", sub: "crypto perpetual futures" },
];
const rank = (s) => (s.stored.length ? 0 : s.own ? 1 : 2);
const byRank = (a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name);

let _builtinCache = null;
export function builtinGroups() {
  if (_builtinCache) return _builtinCache;
  _builtinCache = BUILTIN.map((b) => ({ ...b, builtin: true,
    names: G.symbols.filter((s) => s.source === b.source).sort(byRank).map((s) => s.name) })).filter((g) => g.names.length);
  return _builtinCache;
}
export const userGroups = () => G.list.map((g) => ({ id: g.id, label: g.name, names: g.members, user: true, raw: g }));

/* ---------- search ---------- */
export function searchSymbols(query, filter) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const toks = q.split(/\s+/);
  const out = [];
  for (const s of G.symbols) {
    if (filter && !filter(s)) continue;
    const nm = s.name.toLowerCase(), sym = s.symbol.toLowerCase();
    const hay = nm + " " + sym;
    if (!toks.every((t) => hay.includes(t))) continue;
    const tick = sym.includes(":") ? sym.split(":").pop() : sym;
    const score = tick === q || nm === q ? 0 : nm.startsWith(q) || tick.startsWith(q) ? 1 : 2;
    out.push([score, s]);
  }
  out.sort((a, b) => a[0] - b[0] || byRank(a[1], b[1]));
  return out.map((x) => x[1]);
}

/* ---------- group API helpers ---------- */
function replaceLocal(g) {
  const i = G.list.findIndex((x) => x.id === g.id);
  if (i >= 0) G.list[i] = g; else G.list.push(g);
  changed();
}
export async function addToGroup(id, names) { replaceLocal(await api.patchGroup(id, { add: names })); }
export async function removeFromGroup(id, names) { replaceLocal(await api.patchGroup(id, { remove: names })); }

/* =====================================================================
   SecTree — renders into a <table>
   options:
     key          remembers which groups are expanded (per place)
     el           the <table>
     head         optional <tr> for <thead> (checkbox column first when checkable)
     cols         number of extra columns after the name column
     cells(s)     html of the extra <td>s of a security row
     checkable    true → checkboxes, isOn(name) / setOn(names, on)
     onPick(name) picker mode (no checkboxes) — a click on a row picks it; active() = current name
     filter(s)    which securities may appear here (e.g. only those with a downloader)
     query()      the search text
     pinned()     extra groups shown first: [{id, label, names, open, sub}]
     extra()      extra groups shown first under "All securities" (after your groups)
     disabled()   true → checkboxes locked (e.g. while downloading)
     after()      called after each render
   ===================================================================== */
export class SecTree {
  constructor(o) {
    this.o = { page: 100, cols: 0, checkable: true, ...o };
    this.el = o.el;
    try { this.state = JSON.parse(localStorage.getItem("h1-tree-" + o.key) || "{}"); } catch (e) { this.state = {}; }
    this.shown = {};
    this.el.addEventListener("click", (e) => this._click(e));
    this.el.addEventListener("change", (e) => this._change(e));
    onGroupsChange(() => { if (this.el.isConnected && this.el.offsetParent !== null) this.render(); });
  }
  _save() { try { localStorage.setItem("h1-tree-" + this.o.key, JSON.stringify(this.state)); } catch (e) { /* ignore */ } }
  _ok(n) { const s = G.byName.get(n); return !!s && (!this.o.filter || this.o.filter(s)); }
  _names(g) { return g.names.filter((n) => this._ok(n)); }
  isOpen(g) { return g.id in this.state ? this.state[g.id] : !!g.open; }

  render() {
    const o = this.o, q = o.query ? o.query().trim() : "";
    const ck = o.checkable, all = (ck ? 1 : 0) + 1 + o.cols;
    this._groups = {};
    let h = (o.head ? `<thead>${o.head}</thead>` : "") + "<tbody>";
    const sec = (title, extra = "") => `<tr class="t-sec"><td colspan="${all}"><div><span>${title}</span><span class="spacer"></span>${extra}</div></td></tr>`;
    const sel = ck ? G.symbols.filter((s) => this._ok(s.name) && o.isOn(s.name)).map((s) => s.name) : [];
    const newBtns = `<button class="btn ghost sm" data-newgroup>＋ New group</button>` +
      (sel.length ? `<button class="btn ghost sm" data-savesel title="Create a group from the ${sel.length} ticked securities">Save selection as group</button>` : "");

    (o.pinned ? o.pinned() : []).forEach((g) => { h += this._group(g, all); });
    if (q) {
      const ql = q.toLowerCase();
      const ug = userGroups().filter((g) => g.label.toLowerCase().includes(ql));
      if (ug.length) { h += sec("Your groups"); ug.forEach((g) => { h += this._group(g, all); }); }
      const hits = searchSymbols(q, (s) => this._ok(s.name)).map((s) => s.name);
      h += this._group({ id: "search", label: `Search results for “${esc(q)}”`, names: hits, open: true, search: true }, all, true);
    } else {
      if (ck && sel.length) h += this._group({ id: "selected", label: "Selected", names: sel, sub: "everything ticked, from any group" }, all);
      const ug = userGroups();
      h += sec("Your groups", newBtns);
      h += ug.length ? ug.map((g) => this._group(g, all)).join("")
        : `<tr class="t-empty"><td colspan="${all}">No groups yet. A group is a list you make once — e.g. “Banks”, “My crypto” — and then select in one click everywhere. Use <b>＋ New group</b>, or the <b>＋</b> next to any security.</td></tr>`;
      h += sec("All securities");
      [...(o.extra ? o.extra() : []), ...builtinGroups()].forEach((g) => { h += this._group(g, all); });
    }
    this.el.innerHTML = h + "</tbody>";
    $$("input[data-ind='1']", this.el).forEach((c) => { c.indeterminate = true; });
    if (o.after) o.after();
  }

  _group(g, all, forceOpen = false) {
    const o = this.o, ck = o.checkable;
    const names = this._names(g);
    this._groups[g.id] = { ...g, names };
    const open = forceOpen || this.isOpen(g);
    const k = ck ? names.reduce((a, n) => a + (o.isOn(n) ? 1 : 0), 0) : 0;
    const dis = ck && o.disabled && o.disabled();
    const missing = g.user ? g.names.length - names.length : 0;
    let h = `<tr class="t-g ${open ? "open" : ""} ${g.user ? "user" : ""} ${g.search ? "search" : ""}" data-g="${esc(g.id)}">` +
      (ck ? `<td class="t-ck"><input type="checkbox" data-gck title="Select / unselect all ${names.length}" ${names.length && k === names.length ? "checked" : ""}
              data-ind="${k && k < names.length ? 1 : 0}" ${dis || !names.length ? "disabled" : ""}></td>` : "") +
      `<td colspan="${all - (ck ? 1 : 0)}" class="t-gl"><div><span class="t-arr">${g.search ? "⌕" : "▸"}</span><b>${g.user ? esc(g.label) : g.label}</b>
        <span class="t-n">${names.length.toLocaleString()}</span>${k ? `<span class="t-k">${k.toLocaleString()} selected</span>` : ""}
        ${g.sub ? `<span class="t-sub">${g.sub}</span>` : ""}${missing ? `<span class="t-sub warn" title="Not in the security list (renamed or removed), or not usable here">${missing} not available here</span>` : ""}
        <span class="spacer"></span>${g.user ? `<button class="btn ghost sm" data-gedit title="Rename, add or remove securities, delete">✎ Edit</button>` : ""}</div></td></tr>`;
    if (!open) return h;
    const n = this.shown[g.id] || o.page;
    h += names.slice(0, n).map((nm) => this._row(nm, g.id)).join("");
    if (names.length > n) {
      const left = names.length - n;
      h += `<tr class="t-more"><td colspan="${all}"><button class="btn ghost sm" data-more="${esc(g.id)}">Show ${Math.min(o.page * 2, left).toLocaleString()} more</button>
        <span class="muted small">${left.toLocaleString()} more not shown${g.search ? " — type more to narrow the search" : ""}</span></td></tr>`;
    }
    if (!names.length) h += `<tr class="t-empty"><td colspan="${all}">${g.search ? "No security matches." : g.user ? "Empty — use ✎ Edit or the ＋ next to any security to add some." : "—"}</td></tr>`;
    return h;
  }

  _row(nm, gid) {
    const o = this.o, s = G.byName.get(nm);
    const on = o.checkable && o.isOn(nm);
    const dis = o.checkable && o.disabled && o.disabled();
    const act = o.onPick && o.active && o.active() === nm;
    return `<tr class="t-m ${o.checkable && !on ? "off" : ""} ${act ? "active" : ""}" data-n="${esc(nm)}" data-in="${esc(gid)}">` +
      (o.checkable ? `<td class="t-ck"><input type="checkbox" data-mck ${on ? "checked" : ""} ${dis ? "disabled" : ""}></td>` : "") +
      `<td class="t-nm"><div><span class="dot ${s.stored.length ? "ok" : ""}"></span><span class="t-name"><b>${esc(nm)}</b>
        <small>${esc(s.symbol)} · ${SRC_LABEL[s.source] || esc(s.source)}${s.series ? ` · ${esc(s.series)}` : ""}${s.stored.length ? ` · <span class="pos">${esc(s.stored.join(" "))}</span>` : ""}</small></span>
        <button class="t-plus" data-gadd title="Add to / remove from your groups">＋</button></div></td>` +
      (o.cells ? o.cells(s) : "") + `</tr>`;
  }

  _click(e) {
    const t = e.target, o = this.o;
    if (t.closest("input, select, label")) return;
    const btn = t.closest("button");
    if (btn) {
      e.stopPropagation();
      if (btn.hasAttribute("data-gadd")) groupMenu([btn.closest("tr").dataset.n], btn);
      else if (btn.hasAttribute("data-gedit")) openEditor(G.list.find((x) => x.id === btn.closest("tr").dataset.g));
      else if (btn.hasAttribute("data-newgroup")) openEditor(null, []);
      else if (btn.hasAttribute("data-savesel")) openEditor(null, G.symbols.filter((s) => this._ok(s.name) && o.isOn(s.name)).map((s) => s.name));
      else if (btn.dataset.more) { const id = btn.dataset.more; this.shown[id] = (this.shown[id] || o.page) + o.page * 2; this.render(); }
      return;
    }
    const gr = t.closest("tr.t-g");
    if (gr) {
      if (gr.classList.contains("search")) return;
      const g = this._groups[gr.dataset.g];
      this.state[g.id] = !this.isOpen(g);
      this._save();
      this.render();
      return;
    }
    const mr = t.closest("tr.t-m");
    if (mr && o.onPick) o.onPick(mr.dataset.n);
    else if (mr && o.checkable && !(o.disabled && o.disabled()) && t.closest("td.t-nm")) {   // click on the name = tick it
      o.setOn([mr.dataset.n], !o.isOn(mr.dataset.n));
      this.render();
    }
  }

  _change(e) {
    const t = e.target, o = this.o;
    if (t.hasAttribute("data-gck")) {
      const g = this._groups[t.closest("tr").dataset.g];
      o.setOn(g.names, t.checked);
      this.render();
    } else if (t.hasAttribute("data-mck")) {
      o.setOn([t.closest("tr").dataset.n], t.checked);
      this.render();
    }
  }
}

/* =====================================================================
   "＋" menu: tick the groups a security (or several) belongs to
   ===================================================================== */
let MENU = null;
function closeMenu() { if (MENU) { MENU.remove(); MENU = null; } }
document.addEventListener("mousedown", (e) => { if (MENU && !MENU.contains(e.target)) closeMenu(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

export function groupMenu(names, anchor) {
  closeMenu();
  const m = MENU = document.createElement("div");
  m.className = "g-menu";
  const draw = () => {
    m.innerHTML = `<div class="g-mt">${names.length === 1 ? esc(names[0]) : `${names.length} securities`}</div>` +
      (G.list.length ? G.list.map((g) => {
        const k = names.filter((n) => g.members.includes(n)).length;
        return `<label><input type="checkbox" data-mg="${esc(g.id)}" ${k === names.length ? "checked" : ""} data-ind="${k && k < names.length ? 1 : 0}">
          <span>${esc(g.name)}</span><small>${g.members.length}</small></label>`;
      }).join("") : `<div class="g-none">You have no groups yet.</div>`) +
      `<button class="btn ghost sm" data-mnew>＋ New group${names.length === 1 ? " with this" : " with these"}…</button>`;
    $$("input[data-ind='1']", m).forEach((c) => { c.indeterminate = true; });
  };
  draw();
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(r.right - mw, innerWidth - mw - 8)) + "px";
  m.style.top = (r.bottom + mh + 8 > innerHeight ? Math.max(8, r.top - mh - 4) : r.bottom + 4) + "px";
  m.addEventListener("change", async (e) => {
    const c = e.target.closest("[data-mg]");
    if (!c) return;
    c.disabled = true;
    try {
      await (c.checked ? addToGroup(c.dataset.mg, names) : removeFromGroup(c.dataset.mg, names));
      if (MENU === m) draw();
    } catch (err) { toast(err.message, "error"); c.checked = !c.checked; c.disabled = false; }
  });
  m.addEventListener("click", (e) => {
    if (e.target.closest("[data-mnew]")) { closeMenu(); openEditor(null, names); }
  });
}

/* =====================================================================
   Group editor
   ===================================================================== */
let ED = null;
function editorEl() {
  if (ED) return ED;
  const el = document.createElement("div");
  el.id = "grpModal";
  el.className = "modal hidden g-modal";
  el.innerHTML = `
  <div class="modal-box g-ed">
    <div class="modal-head"><h3 id="geTitle">New group</h3><span class="spacer"></span><button class="btn ghost icon" data-close>×</button></div>
    <div class="modal-body">
      <label class="g-name">Group name<input id="geName" maxlength="60" placeholder="e.g. Banks, Nifty IT, My crypto" autocomplete="off"></label>
      <div class="g-cols">
        <div class="g-col">
          <div class="g-h">Add securities</div>
          <input id="geSearch" placeholder="Search any security — name, ticker, BTC, nifty…" autocomplete="off">
          <div class="g-from"><span class="muted small">or add everything from</span><select id="geFrom"></select><button class="btn ghost sm" id="geFromGo">Add</button></div>
          <div id="geRes" class="g-list"></div>
        </div>
        <div class="g-col">
          <div class="g-h">In this group <span id="geN" class="pill"></span><span class="spacer"></span><button class="btn ghost sm" id="geClear">Remove all</button></div>
          <input id="geFilter" placeholder="Filter this group…" autocomplete="off">
          <div id="geMem" class="g-list"></div>
        </div>
      </div>
    </div>
    <div class="g-foot"><button class="btn ghost danger" id="geDel">Delete group</button><span class="spacer"></span>
      <button class="btn ghost" data-close>Cancel</button><button class="btn primary" id="geSave">Save group</button></div>
  </div>`;
  document.body.appendChild(el);
  ED = { el, group: null, members: [] };
  el.addEventListener("click", (e) => { if (e.target === el || e.target.closest("[data-close]")) el.classList.add("hidden"); });
  const res = () => {
    const q = $("#geSearch").value;
    const have = new Set(ED.members);
    const hits = searchSymbols(q);
    if (!q.trim()) { $("#geRes").innerHTML = `<div class="g-none">Type to search all ${G.symbols.length.toLocaleString()} securities.</div>`; return; }
    $("#geRes").innerHTML = (hits.length > 1 ? `<div class="g-all"><button class="btn ghost sm" data-addall>Add all ${hits.length.toLocaleString()} results</button></div>` : "") +
      (hits.slice(0, 80).map((s) => `<div class="g-item ${have.has(s.name) ? "in" : ""}" data-n="${esc(s.name)}"><span class="dot ${s.stored.length ? "ok" : ""}"></span>
        <span class="g-txt"><b>${esc(s.name)}</b><small>${esc(s.symbol)} · ${SRC_LABEL[s.source] || s.source}</small></span>
        <button class="btn ${have.has(s.name) ? "ghost" : ""} sm" data-tog>${have.has(s.name) ? "✓ added" : "＋ Add"}</button></div>`).join("")
        || `<div class="g-none">No match.</div>`) + (hits.length > 80 ? `<div class="g-none">${(hits.length - 80).toLocaleString()} more — type more to narrow down.</div>` : "");
    ED.hits = hits;
  };
  const mem = () => {
    const f = $("#geFilter").value.trim().toLowerCase();
    $("#geN").textContent = ED.members.length.toLocaleString();
    const list = ED.members.filter((n) => !f || n.toLowerCase().includes(f));
    $("#geMem").innerHTML = list.slice(0, 600).map((n) => {
      const s = G.byName.get(n);
      return `<div class="g-item" data-n="${esc(n)}"><span class="dot ${s && s.stored.length ? "ok" : ""}"></span>
        <span class="g-txt"><b>${esc(n)}</b><small>${s ? `${esc(s.symbol)} · ${SRC_LABEL[s.source] || s.source}` : `<span class="neg">not in the security list</span>`}</small></span>
        <button class="btn ghost sm" data-rm title="Remove from the group">×</button></div>`;
    }).join("") + (list.length > 600 ? `<div class="g-none">${list.length - 600} more…</div>` : "")
      || `<div class="g-none">${ED.members.length ? "No match." : "Empty — search on the left and add securities."}</div>`;
  };
  ED.res = res; ED.mem = mem;
  $("#geSearch").oninput = res;
  $("#geFilter").oninput = mem;
  $("#geRes").onclick = (e) => {
    if (e.target.closest("[data-addall]")) {
      ED.members = [...new Set([...ED.members, ...ED.hits.map((s) => s.name)])]; res(); mem(); return;
    }
    const it = e.target.closest(".g-item");
    if (!it) return;
    const n = it.dataset.n;
    ED.members = ED.members.includes(n) ? ED.members.filter((x) => x !== n) : [...ED.members, n];
    res(); mem();
  };
  $("#geMem").onclick = (e) => {
    const b = e.target.closest("[data-rm]");
    if (!b) return;
    const n = b.closest(".g-item").dataset.n;
    ED.members = ED.members.filter((x) => x !== n);
    res(); mem();
  };
  $("#geClear").onclick = () => { ED.members = []; res(); mem(); };
  $("#geFromGo").onclick = () => {
    const id = $("#geFrom").value;
    const g = [...userGroups(), ...builtinGroups()].find((x) => x.id === id);
    if (!g) return;
    const add = g.names.filter((n) => G.byName.has(n));
    ED.members = [...new Set([...ED.members, ...add])];
    res(); mem();
    toast(`Added ${add.length.toLocaleString()} from ${g.label}.`, "ok");
  };
  $("#geName").onkeydown = (e) => { if (e.key === "Enter") $("#geSave").click(); };
  $("#geSave").onclick = async () => {
    const name = $("#geName").value.trim();
    if (!name) { toast("Give the group a name.", "error"); $("#geName").focus(); return; }
    const b = $("#geSave"); b.disabled = true;
    try {
      const g = ED.group ? await api.patchGroup(ED.group.id, { name, members: ED.members })
        : await api.createGroup({ name, members: ED.members });
      replaceLocal(g);
      el.classList.add("hidden");
      toast(`Group “${esc(g.name)}” saved — ${g.members.length} securities.`, "ok", true);
    } catch (err) { toast(err.message, "error"); } finally { b.disabled = false; }
  };
  $("#geDel").onclick = async () => {
    const b = $("#geDel");
    if (!b.classList.contains("sure")) { b.classList.add("sure"); b.textContent = "Click again to delete"; return; }
    try {
      await api.deleteGroup(ED.group.id);
      G.list = G.list.filter((x) => x.id !== ED.group.id);
      changed();
      el.classList.add("hidden");
      toast(`Group “${esc(ED.group.name)}” deleted (the securities and their data are untouched).`, "ok", true);
    } catch (err) { toast(err.message, "error"); }
  };
  return ED;
}

export function openEditor(group, members = []) {
  const ed = editorEl();
  ed.group = group || null;
  ed.members = group ? [...group.members] : [...new Set(members)];
  $("#geTitle").textContent = group ? `Edit group · ${group.name}` : "New group";
  $("#geName").value = group ? group.name : "";
  $("#geSearch").value = ""; $("#geFilter").value = "";
  const del = $("#geDel");
  del.classList.toggle("hidden", !group); del.classList.remove("sure"); del.textContent = "Delete group";
  $("#geFrom").innerHTML = [...userGroups().filter((g) => !group || g.id !== group.id), ...builtinGroups()]
    .map((g) => `<option value="${esc(g.id)}">${esc(g.label)} (${g.names.length.toLocaleString()})</option>`).join("");
  ed.res(); ed.mem();
  ed.el.classList.remove("hidden");
  setTimeout(() => (group ? $("#geSearch") : $("#geName")).focus(), 30);
}
