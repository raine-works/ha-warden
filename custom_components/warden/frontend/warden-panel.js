// Warden sidebar panels. One element serves both:
//   mode "admin"    — manage groups, members, permissions and 2FA settings
//   mode "security" — tells a user they must set up two-factor authentication
//                      (the setup dialog itself is in warden-prompt.js)
// Plain web component, no build step. Every user-supplied string goes through
// esc() before it reaches innerHTML.

const SCOPES = [
  ["entity_ids", "Entity"],
  ["device_ids", "Device"],
  ["area_ids", "Area"],
  ["domains", "Domain"],
  ["label_ids", "Label"],
];
const LEVELS = [
  ["read", "Read"],
  ["control", "Control"],
  ["deny", "Deny"],
];
const MFA_LABELS = {
  exempt: "Not required",
  compliant: "Enrolled",
  grace: "Grace period",
  restricted: "Restricted",
  unenforceable: "Can't enforce",
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");

// A searchable combobox for picking an entity, device, area, domain or label.
// Typing filters the options: every word must appear in the name, id or
// context (area, device), so "kitchen lamp" finds light.kitchen_lamp_2.
// Options: [{ value, label, secondary, search }]. Fires "value-changed".
const PICKER_LIMIT = 100;
const PICKER_PLACEHOLDERS = {
  entity_ids: "Search entities…",
  device_ids: "Search devices…",
  area_ids: "Search areas…",
  domains: "Search domains…",
  label_ids: "Search labels…",
};
const PICKER_CUSTOM = {
  entity_ids: /^[a-z0-9_]+\.[a-z0-9_]+$/,
  domains: /^[a-z0-9_]+$/,
};

const PICKER_STYLE = `
  :host { display: block; position: relative; min-width: 0; }
  .box {
    display: flex; align-items: center; gap: 4px;
    border: 1px solid var(--divider-color); border-radius: 6px;
    background: var(--card-background-color); padding: 0 4px 0 8px;
  }
  .box:focus-within { border-color: var(--warden-loud); box-shadow: 0 0 0 1px var(--warden-loud); }
  input {
    flex: 1; min-width: 0; font: inherit; font-size: 14px; padding: 7px 0;
    border: none; outline: none; background: transparent; color: var(--primary-text-color);
  }
  input::placeholder { color: var(--secondary-text-color); }
  button {
    display: grid; place-items: center; width: 26px; height: 26px; padding: 0;
    border: none; border-radius: 50%; background: transparent; cursor: pointer;
    color: var(--secondary-text-color);
  }
  button:hover { background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }
  button svg { width: 18px; height: 18px; fill: currentColor; }
  .list {
    position: fixed; z-index: 10; box-sizing: border-box;
    max-height: 320px; overflow-y: auto; overscroll-behavior: contain;
    padding: 4px; margin: 0; list-style: none;
    background: var(--card-background-color); color: var(--primary-text-color);
    border: 1px solid var(--divider-color); border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  }
  li { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 6px; cursor: pointer; }
  li.active { background: color-mix(in srgb, var(--warden-loud) 18%, transparent); }
  li .text { min-width: 0; flex: 1; }
  li .label { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li .secondary { font-size: 12px; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li .check { width: 16px; flex: none; color: var(--warden-loud); }
  li .check svg { width: 16px; height: 16px; fill: currentColor; }
  mark { background: none; color: inherit; font-weight: 600; }
  .note { padding: 8px 10px; font-size: 12px; color: var(--secondary-text-color); cursor: default; }
`;

const PICKER_ICONS = {
  down: "M7,10L12,15L17,10H7Z",
  clear: "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  check: "M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z",
};
const pickerIcon = (name) => `<svg viewBox="0 0 24 24"><path d="${PICKER_ICONS[name]}"/></svg>`;

class WardenPicker extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._options = [];
    this._value = "";
    this._placeholder = "Search…";
    // Typed values not in the list that may be used as is (a RegExp), if any.
    this.customPattern = null;
    this._open = false;
    this._query = "";
    this._active = 0;
    this._reposition = () => this._place();
  }

  get options() {
    return this._options;
  }

  set options(options) {
    this._options = options;
    this._showValue();
  }

  get value() {
    return this._value;
  }

  set value(value) {
    this._value = value || "";
    this._showValue();
  }

  set placeholder(text) {
    this._placeholder = text;
    if (this._input) {
      this._input.placeholder = text;
    }
  }

  connectedCallback() {
    if (this._input) {
      return;
    }
    this.shadowRoot.innerHTML = `
      <style>${PICKER_STYLE}</style>
      <div class="box">
        <input role="combobox" aria-autocomplete="list" aria-expanded="false" autocomplete="off" spellcheck="false">
        <button class="clear" tabindex="-1" title="Clear" aria-label="Clear">${pickerIcon("clear")}</button>
        <button class="toggle" tabindex="-1" title="Show options" aria-label="Show options">${pickerIcon("down")}</button>
      </div>
      <ul class="list" role="listbox" hidden></ul>`;
    this._input = this.shadowRoot.querySelector("input");
    this._list = this.shadowRoot.querySelector(".list");
    this._input.placeholder = this._placeholder;
    this._showValue();

    this._input.addEventListener("focus", () => {
      this._input.select();
      this._openList("");
    });
    this._input.addEventListener("input", () => this._openList(this._input.value));
    this._input.addEventListener("keydown", (ev) => this._key(ev));
    this._input.addEventListener("blur", () => this._closeList(true));
    this.shadowRoot.querySelector(".toggle").addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      if (this._open) {
        this._closeList(true);
      } else {
        this._input.focus();
      }
    });
    this.shadowRoot.querySelector(".clear").addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      this._pick("");
    });
    // mousedown, not click: picking must happen before the input blurs.
    this._list.addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      const li = ev.target.closest("li[data-index]");
      if (li) {
        this._pickMatch(Number(li.dataset.index));
      }
    });
    this._list.addEventListener("mousemove", (ev) => {
      const li = ev.target.closest("li[data-index]");
      if (li && Number(li.dataset.index) !== this._active) {
        this._active = Number(li.dataset.index);
        this._paintActive();
      }
    });
  }

  disconnectedCallback() {
    window.removeEventListener("scroll", this._reposition, true);
    window.removeEventListener("resize", this._reposition);
  }

  _showValue() {
    if (!this._input) {
      return;
    }
    const match = this.options.find((o) => o.value === this.value);
    this._input.value = match ? match.label : this.value;
    this.shadowRoot.querySelector(".clear").hidden = !this.value;
  }

  _openList(query) {
    this._query = query.trim().toLowerCase();
    this._active = 0;
    this._open = true;
    this._input.setAttribute("aria-expanded", "true");
    this._renderList();
    // Opened without a search: start at the current choice.
    const current = this._query ? -1 : this._matches.findIndex((o) => o.value === this.value);
    if (current > 0) {
      this._active = current;
      this._paintActive();
    }
    this._list.hidden = false;
    this._place();
    window.addEventListener("scroll", this._reposition, true);
    window.addEventListener("resize", this._reposition);
  }

  _closeList(restore) {
    this._open = false;
    this._list.hidden = true;
    this._input.setAttribute("aria-expanded", "false");
    window.removeEventListener("scroll", this._reposition, true);
    window.removeEventListener("resize", this._reposition);
    if (restore) {
      this._showValue();
    }
  }

  // The list is position: fixed so cards and scrolling parents can't clip it.
  _place() {
    if (!this._open) {
      return;
    }
    const box = this.shadowRoot.querySelector(".box").getBoundingClientRect();
    const below = window.innerHeight - box.bottom - 8;
    const above = box.top - 8;
    const height = Math.min(320, Math.max(below, above));
    this._list.style.left = `${box.left}px`;
    this._list.style.width = `${Math.max(box.width, 280)}px`;
    this._list.style.maxHeight = `${height}px`;
    if (below >= Math.min(320, this._list.scrollHeight) || below >= above) {
      this._list.style.top = `${box.bottom + 4}px`;
      this._list.style.bottom = "";
    } else {
      this._list.style.top = "";
      this._list.style.bottom = `${window.innerHeight - box.top + 4}px`;
    }
  }

  _filter() {
    const words = this._query.split(/\s+/).filter(Boolean);
    if (!words.length) {
      return this.options;
    }
    const scored = [];
    for (const option of this.options) {
      const label = option.label.toLowerCase();
      const hay = `${label} ${option.value.toLowerCase()} ${option.search || ""}`;
      if (!words.every((w) => hay.includes(w))) {
        continue;
      }
      // Names that start with the query first, then names containing it.
      const score = label.startsWith(this._query) ? 0 : label.includes(this._query) ? 1 : 2;
      scored.push([score, option]);
    }
    scored.sort((a, b) => a[0] - b[0]);
    return scored.map(([, option]) => option);
  }

  _renderList() {
    const matches = this._filter();
    this._matches = matches.slice(0, PICKER_LIMIT);
    const typed = this._input.value.trim();
    this._custom =
      this.customPattern?.test(typed) && !this.options.some((o) => o.value === typed) ? typed : null;
    const words = this._query.split(/\s+/).filter(Boolean);
    const highlight = (text) => {
      let html = esc(text);
      for (const w of words) {
        html = html.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"), "<mark>$1</mark>");
      }
      return html;
    };
    const rows = this._matches.map(
      (o, i) => `
        <li role="option" data-index="${i}" aria-selected="${o.value === this.value}">
          <span class="check">${o.value === this.value ? pickerIcon("check") : ""}</span>
          <span class="text">
            <div class="label">${highlight(o.label)}</div>
            ${o.secondary ? `<div class="secondary">${highlight(o.secondary)}</div>` : ""}
          </span>
        </li>`,
    );
    if (this._custom) {
      rows.push(`
        <li role="option" data-index="${this._matches.length}">
          <span class="check"></span>
          <span class="text"><div class="label">Use “${esc(this._custom)}”</div>
          <div class="secondary">Not in the list right now</div></span>
        </li>`);
    }
    let note = "";
    if (!rows.length) {
      note = `<li class="note">No matches</li>`;
    } else if (matches.length > PICKER_LIMIT) {
      note = `<li class="note">Showing ${PICKER_LIMIT} of ${matches.length}. Keep typing to narrow it down.</li>`;
    }
    this._list.innerHTML = rows.join("") + note;
    this._paintActive();
  }

  _count() {
    return this._matches.length + (this._custom ? 1 : 0);
  }

  _paintActive() {
    for (const li of this._list.querySelectorAll("li[data-index]")) {
      const active = Number(li.dataset.index) === this._active;
      li.classList.toggle("active", active);
      if (active) {
        li.scrollIntoView({ block: "nearest" });
      }
    }
  }

  _key(ev) {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (!this._open) {
        this._openList("");
        return;
      }
      const n = this._count();
      if (n) {
        this._active = (this._active + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
        this._paintActive();
      }
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (this._open && this._count()) {
        this._pickMatch(this._active);
      }
    } else if (ev.key === "Escape" && this._open) {
      ev.preventDefault();
      ev.stopPropagation();
      this._closeList(true);
    }
  }

  _pickMatch(index) {
    const value = index < this._matches.length ? this._matches[index].value : this._custom;
    this._pick(value ?? "");
  }

  _pick(value) {
    this._closeList(false);
    this.value = value;
    this._showValue();
    this._input.blur();
    this.dispatchEvent(new CustomEvent("value-changed", { detail: { value } }));
  }
}

if (!customElements.get("warden-picker")) {
  customElements.define("warden-picker", WardenPicker);
}

// Colors use Home Assistant's design tokens (the ones its own buttons use),
// which themes keep readable. --primary-color and --text-primary-color are
// only fallbacks: themes don't promise contrast between those two.
const STYLE = `
  :host {
    --warden-loud: var(--ha-color-fill-primary-loud-resting, var(--primary-color));
    --warden-loud-hover: var(--ha-color-fill-primary-loud-hover, var(--warden-loud));
    --warden-on-loud: var(--ha-color-on-primary-loud, #fff);
    --warden-quiet: var(--ha-color-fill-primary-normal-resting, var(--secondary-background-color));
    --warden-on-quiet: var(--ha-color-on-primary-normal, var(--primary-text-color));
    display: block;
    min-height: 100%;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    height: var(--header-height, 56px);
    padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, white);
    font-size: 20px;
  }
  main { max-width: 1000px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
  .tabs button { border-radius: 18px; }
  .tabs button.active { background: var(--warden-quiet); color: var(--warden-on-quiet); border-color: transparent; font-weight: 500; }
  .card {
    background: var(--card-background-color);
    border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--divider-color);
    padding: 16px;
    margin-bottom: 16px;
  }
  h2 { font-size: 18px; margin: 0 0 12px; font-weight: 500; }
  h3 { font-size: 15px; margin: 20px 0 8px; font-weight: 500; }
  p.hint { color: var(--secondary-text-color); margin: 4px 0 12px; font-size: 14px; }
  button {
    font: inherit;
    font-size: 14px;
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid var(--divider-color);
    background: var(--card-background-color);
    color: var(--primary-text-color);
    cursor: pointer;
  }
  button.primary { background: var(--warden-loud); color: var(--warden-on-loud); border-color: transparent; }
  button.primary:hover { background: var(--warden-loud-hover); }
  input[type="checkbox"] { accent-color: var(--warden-loud); }
  button.danger { color: var(--error-color); }
  button.icon { padding: 4px 8px; }
  input[type="text"], input[type="number"], input:not([type]), select, textarea {
    font: inherit;
    font-size: 14px;
    padding: 6px 8px;
    border-radius: 6px;
    border: 1px solid var(--divider-color);
    background: var(--card-background-color);
    color: var(--primary-text-color);
    box-sizing: border-box;
    max-width: 100%;
  }
  label.row { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
  .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
  .field > span { font-size: 13px; color: var(--secondary-text-color); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 2px 12px; }
  .group-row {
    display: flex; align-items: center; gap: 12px; padding: 12px 0;
    border-top: 1px solid var(--divider-color);
  }
  .group-row:first-of-type { border-top: none; }
  .group-row .grow { flex: 1; min-width: 0; }
  .group-row .name { font-weight: 500; }
  .muted { color: var(--secondary-text-color); font-size: 13px; }
  .chip {
    display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 10px;
    background: color-mix(in srgb, var(--primary-text-color) 10%, transparent);
    margin: 2px 4px 2px 0;
  }
  .chip.warn { background: var(--warning-color); color: white; }
  .chip.bad { background: var(--error-color); color: white; }
  .chip.good { background: var(--success-color); color: white; }
  .rule { display: grid; grid-template-columns: 110px 1fr 110px auto; gap: 8px; margin-bottom: 8px; align-items: center; }
  .table { width: 100%; border-collapse: collapse; font-size: 14px; }
  .table th, .table td { text-align: left; padding: 8px 6px; border-top: 1px solid var(--divider-color); vertical-align: top; }
  .table th { border-top: none; color: var(--secondary-text-color); font-weight: 500; }
  .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
  .error { color: var(--error-color); margin: 8px 0; }
  .center { text-align: center; padding: 32px 16px; }
  .center .big { font-size: 56px; line-height: 1; }
  @media (max-width: 600px) {
    .rule { grid-template-columns: 1fr 1fr; }
    .table .hide-narrow { display: none; }
  }
`;

class WardenPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "groups";
    this._info = null;
    this._me = null;
    this._draft = null;
    this._error = "";
    this._loaded = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._menu) {
      this._menu.hass = hass;
    }
    this._maybeLoad();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) {
      this._menu.narrow = narrow;
    }
  }

  set panel(panel) {
    this._mode = panel?.config?.mode || "admin";
    this._maybeLoad();
  }

  // The frontend sets hass and panel in no fixed order; the mode decides
  // what to load (non-admins may only call warden/me).
  _maybeLoad() {
    if (this._hass && this._mode && !this._loading) {
      this._loading = true;
      this._load();
    }
  }

  async _load() {
    try {
      if (this._mode === "security") {
        this._me = await this._hass.callWS({ type: "warden/me" });
      } else {
        this._info = await this._hass.callWS({ type: "warden/info" });
      }
      this._error = "";
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._loaded = true;
    this._render();
  }

  // ------------------------------------------------------------------ render

  _render() {
    const title = this._mode === "security" ? "Account security" : "Warden";
    let body;
    if (!this._loaded) {
      body = `<p class="muted">Loading…</p>`;
    } else if (this._mode === "security") {
      body = this._renderSecurity();
    } else if (this._draft) {
      body = this._renderEditor();
    } else {
      body = this._renderTabs() + this._renderTab();
    }
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar"><span id="menu"></span><span>${esc(title)}</span></div>
      <main>
        ${this._error ? `<div class="error">${esc(this._error)}</div>` : ""}
        ${body}
      </main>`;

    // The frontend's own sidebar toggle, so the panel works on phones too.
    this._menu = document.createElement("ha-menu-button");
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    this.shadowRoot.getElementById("menu").replaceWith(this._menu);
    this._bind();
  }

  _renderSecurity() {
    const me = this._me || {};
    const setup = `
      <button class="primary" data-action="setup">Set it up now</button>
      <p class="muted" style="margin-top:16px">You can also manage two-factor
      authentication on your <a href="/profile/security" data-action="goto-security">profile</a>.</p>`;
    if (me.mfa === "restricted") {
      return `
        <div class="card center">
          <div class="big">🔒</div>
          <h2>Two-factor authentication required</h2>
          <p class="hint">Your access is limited until you set up two-factor
          authentication for your account.</p>
          ${setup}
        </div>`;
    }
    if (me.mfa === "grace") {
      return `
        <div class="card center">
          <div class="big">🛡️</div>
          <h2>Please set up two-factor authentication</h2>
          <p class="hint">Your account will be required to use two-factor
          authentication. Set it up before <b>${esc(fmtDate(me.mfa_deadline))}</b>
          to keep full access.</p>
          ${setup}
        </div>`;
    }
    return `
      <div class="card center">
        <div class="big">✅</div>
        <h2>You're all set</h2>
        <p class="hint">Your account meets this home's security requirements.</p>
      </div>`;
  }

  _renderTabs() {
    const tab = (id, label) =>
      `<button data-action="tab" data-tab="${id}" class="${this._tab === id ? "active" : ""}">${label}</button>`;
    return `<div class="tabs">${tab("groups", "Groups")}${tab("users", "Users")}${tab(
      "settings",
      "Two-factor",
    )}</div>`;
  }

  _renderTab() {
    if (!this._info) {
      return "";
    }
    if (this._tab === "users") {
      return this._renderUsers();
    }
    if (this._tab === "settings") {
      return this._renderSettings();
    }
    return this._renderGroups();
  }

  _userName(id) {
    return this._info.users.find((u) => u.id === id)?.name || id;
  }

  _renderGroups() {
    const groups = this._info.groups;
    const rows = groups
      .map((g) => {
        const chips = [
          g.admin ? `<span class="chip">Administrator</span>` : "",
          g.require_mfa ? `<span class="chip">2FA required</span>` : "",
          `<span class="chip">${g.members.length} member${g.members.length === 1 ? "" : "s"}</span>`,
        ].join("");
        return `
          <div class="group-row">
            <div class="grow">
              <div class="name">${esc(g.name)}</div>
              ${g.description ? `<div class="muted">${esc(g.description)}</div>` : ""}
              <div>${chips}</div>
            </div>
            <button data-action="edit" data-id="${esc(g.id)}">Edit</button>
          </div>`;
      })
      .join("");
    return `
      <div class="card">
        <h2>Groups</h2>
        <p class="hint">Users in a group lose their standard Home Assistant
        role and get exactly what their groups allow. A user in several groups
        gets everything any of them allows, minus anything any of them denies.
        The owner is never restricted, and Home Assistant administrators keep
        full access: only a group's 2FA requirement applies to them. To
        restrict someone, turn off Administrator under Settings → People.</p>
        ${rows || `<p class="muted">No groups yet.</p>`}
        <div class="actions"><button class="primary" data-action="new">Add group</button></div>
      </div>`;
  }

  _renderUsers() {
    const groupsOf = (id) =>
      this._info.groups.filter((g) => g.members.includes(id)).map((g) => g.name);
    const rows = this._info.users
      .map((u) => {
        const groups = groupsOf(u.id);
        const role = u.is_owner
          ? "Owner"
          : u.native_admin
            ? "Administrator"
            : u.is_admin
              ? "Administrator (Warden group)"
              : u.managed
                ? "Managed"
                : "User";
        // Whether 2FA is set up and whether it's required are separate: someone
        // can be enrolled without being required to, and the other way round.
        const enrolled = u.mfa_modules.length > 0;
        const required = ["compliant", "grace", "restricted", "unenforceable"].includes(u.mfa);
        let chip;
        if (enrolled) {
          chip = `<span class="chip good">Enrolled</span>`;
        } else if (required) {
          const cls = { grace: "warn", restricted: "bad", unenforceable: "bad" }[u.mfa] || "";
          chip = `<span class="chip ${cls}">${esc(MFA_LABELS[u.mfa])}</span>`;
        } else {
          chip = `<span class="chip">Not set up</span>`;
        }
        let note = required ? "Required" : "Not required";
        if (u.is_owner) {
          note = "Owner, never required";
        } else if (u.mfa === "grace") {
          note = `Required by ${fmtDate(u.mfa_deadline)}`;
        }
        const mfa = `${chip}<div class="muted">${esc(note)}</div>`;
        return `
          <tr>
            <td>${esc(u.name)}${u.is_active ? "" : ` <span class="muted">(inactive)</span>`}</td>
            <td class="hide-narrow">${esc(role)}</td>
            <td>${groups.map((n) => `<span class="chip">${esc(n)}</span>`).join("") || `<span class="muted">—</span>`}</td>
            <td>${mfa}</td>
          </tr>`;
      })
      .join("");
    return `
      <div class="card">
        <h2>Users</h2>
        <p class="hint">Add people to groups from the group editor. Create or
        remove accounts under Settings → People.</p>
        <table class="table">
          <thead><tr><th>Name</th><th class="hide-narrow">Role</th><th>Groups</th><th>Two-factor</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  _renderSettings() {
    const s = this._info.settings;
    const modules = this._info.mfa_modules;
    return `
      <div class="card">
        <h2>Two-factor authentication</h2>
        <p class="hint">Require 2FA for everyone here, or per group in the group
        editor. Users who haven't set it up keep full access during the grace
        period, then can only reach their profile until they do. The owner is
        exempt.</p>
        ${
          modules.length
            ? `<p class="muted">Available methods: ${modules.map((m) => esc(m.name)).join(", ")}</p>`
            : `<p class="error">No two-factor module is loaded, so 2FA can't be enforced. Add one under <code>auth_mfa_modules</code> in configuration.yaml.</p>`
        }
        <label class="row"><input type="checkbox" id="require_mfa_all" ${s.require_mfa_all ? "checked" : ""}> Require two-factor authentication for all users</label>
        <div class="field" style="max-width:220px">
          <span>Grace period (days)</span>
          <input type="number" id="mfa_grace_days" min="0" max="365" value="${esc(s.mfa_grace_days)}">
        </div>
        <div class="actions"><button class="primary" data-action="save-settings">Save</button></div>
      </div>`;
  }

  // ------------------------------------------------------------------ editor

  _renderEditor() {
    const d = this._draft;
    const info = this._info;
    const users = info.users.filter((u) => !u.is_owner);
    const members = users
      .map(
        (u) =>
          `<label class="row"><input type="checkbox" data-member="${esc(u.id)}" ${
            d.members.includes(u.id) ? "checked" : ""
          }> ${esc(u.name)}${
            u.native_admin ? ` <span class="muted" title="Home Assistant administrators keep full access; only this group's 2FA requirement applies.">(administrator)</span>` : ""
          }</label>`,
      )
      .join("");
    const access = (kind, items) => {
      const list = d[kind];
      const boxes = items
        .map(
          (it) =>
            `<label class="row"><input type="checkbox" data-${kind}="${esc(it.url_path)}" ${
              list.items.includes(it.url_path) ? "checked" : ""
            } ${list.all ? "disabled" : ""}> ${esc(it.title)}</label>`,
        )
        .join("");
      return `
        <label class="row"><input type="checkbox" data-all="${kind}" ${list.all ? "checked" : ""}> All ${kind}</label>
        <div class="grid">${boxes || `<span class="muted">None available.</span>`}</div>`;
    };
    const levelSelect = (value, attr, allowNone) =>
      `<select ${attr}>${allowNone ? `<option value="" ${value ? "" : "selected"}>No access</option>` : ""}${LEVELS.map(
        ([v, l]) => `<option value="${v}" ${value === v ? "selected" : ""}>${l}</option>`,
      ).join("")}</select>`;
    const rules = d.rules
      .map(
        (r, i) => `
        <div class="rule">
          <select data-rule="${i}" data-field="scope">${SCOPES.map(
            ([v, l]) => `<option value="${v}" ${r.scope === v ? "selected" : ""}>${l}</option>`,
          ).join("")}</select>
          <warden-picker data-rule="${i}" data-field="key"></warden-picker>
          ${levelSelect(r.level, `data-rule="${i}" data-field="level"`, false)}
          <button class="icon danger" data-action="remove-rule" data-index="${i}" title="Remove">✕</button>
        </div>
        <div class="muted" style="margin:-4px 0 8px">${esc(this._describeKey(r.scope, r.key))}</div>`,
      )
      .join("");

    return `
      <div class="card">
        <h2>${d.id ? "Edit group" : "New group"}</h2>
        <div class="field"><span>Name</span><input id="name" value="${esc(d.name)}"></div>
        <div class="field"><span>Description</span><input id="description" value="${esc(d.description)}"></div>
        <label class="row"><input type="checkbox" id="admin" ${d.admin ? "checked" : ""}> Members are Home Assistant administrators</label>
        <label class="row"><input type="checkbox" id="require_mfa" ${d.require_mfa ? "checked" : ""}> Require two-factor authentication</label>

        <h3>Members</h3>
        <div class="grid">${members || `<span class="muted">No users to add.</span>`}</div>

        <div ${d.admin ? `style="opacity:.5;pointer-events:none"` : ""}>
          <h3>Entities</h3>
          <p class="hint">Rules match an entity directly, everything on a device,
          everything on devices in an area, a whole domain, or everything with a
          label (on the entity, its device or its area). Control includes read.
          Deny overrides any allow, from any group.</p>
          <div class="field" style="max-width:260px">
            <span>Every entity</span>${levelSelect(d.all, `id="all"`, true)}
          </div>
          ${rules}
          <button data-action="add-rule">Add rule</button>

          <h3>Dashboards</h3>
          ${access("dashboards", info.dashboards)}

          <h3>Panels</h3>
          <p class="hint">Sidebar pages such as Map, Energy or Logbook. Profile
          is always available.</p>
          ${access("panels", info.panels)}
        </div>
        ${d.admin ? `<p class="hint">Administrators have full access; entity, dashboard and panel rules don't apply.</p>` : ""}

        <div class="actions">
          ${d.id ? `<button class="danger" data-action="delete">Delete group</button>` : ""}
          <span style="flex:1"></span>
          <button data-action="cancel">Cancel</button>
          <button class="primary" data-action="save">Save</button>
        </div>
      </div>`;
  }

  // Picker options for a rule scope. Built once per editor: there can be
  // thousands of entities.
  _options(scope) {
    this._optionCache ||= {};
    if (!this._optionCache[scope]) {
      this._optionCache[scope] = this._buildOptions(scope);
    }
    return this._optionCache[scope];
  }

  _buildOptions(scope) {
    const hass = this._hass;
    const areas = hass.areas || {};
    const devices = hass.devices || {};
    const areaName = (id) => (id && areas[id]?.name) || "";
    const deviceName = (dev) => (dev && (dev.name_by_user || dev.name)) || "";
    const byLabel = (a, b) => a.label.localeCompare(b.label);

    if (scope === "entity_ids") {
      return Object.keys(hass.states)
        .map((id) => {
          const entry = hass.entities?.[id];
          const device = entry?.device_id ? devices[entry.device_id] : undefined;
          const area = areaName(entry?.area_id || device?.area_id);
          const context = [id, area, deviceName(device)].filter(Boolean);
          return {
            value: id,
            label: hass.states[id].attributes.friendly_name || id,
            secondary: [...new Set(context)].join(" · "),
            search: context.join(" ").toLowerCase(),
          };
        })
        .sort(byLabel);
    }
    if (scope === "device_ids") {
      return Object.values(devices)
        .map((dev) => {
          const context = [areaName(dev.area_id), dev.manufacturer, dev.model].filter(Boolean);
          return {
            value: dev.id,
            label: deviceName(dev) || dev.id,
            secondary: context.join(" · "),
            search: context.join(" ").toLowerCase(),
          };
        })
        .sort(byLabel);
    }
    if (scope === "area_ids") {
      const floors = hass.floors || {};
      return Object.values(areas)
        .map((area) => {
          const floor = (area.floor_id && floors[area.floor_id]?.name) || "";
          return {
            value: area.area_id,
            label: area.name,
            secondary: floor,
            search: floor.toLowerCase(),
          };
        })
        .sort(byLabel);
    }
    if (scope === "label_ids") {
      return (this._info.labels || []).map((label) => ({
        value: label.label_id,
        label: label.name,
        secondary: "",
      }));
    }
    const counts = {};
    for (const id of Object.keys(hass.states)) {
      const domain = id.split(".")[0];
      counts[domain] = (counts[domain] || 0) + 1;
    }
    return Object.keys(counts)
      .sort()
      .map((domain) => ({
        value: domain,
        label: domain,
        secondary: `${counts[domain]} ${counts[domain] === 1 ? "entity" : "entities"}`,
      }));
  }

  _describeKey(scope, key) {
    if (!key) {
      return "";
    }
    const match = this._options(scope).find((o) => o.value === key);
    if (!match) {
      return scope === "entity_ids" ? `${key} (not currently available)` : `${key} (not found)`;
    }
    return scope === "domains" ? "" : match.secondary || "";
  }

  _openEditor(group) {
    const g = group || {
      name: "",
      description: "",
      admin: false,
      require_mfa: false,
      members: [],
      entities: {},
      dashboards: { all: false, items: [] },
      panels: { all: false, items: [] },
    };
    const rules = [];
    for (const [scope] of SCOPES) {
      for (const [key, level] of Object.entries(g.entities[scope] || {})) {
        rules.push({ scope, key, level });
      }
    }
    this._draft = {
      id: g.id,
      name: g.name,
      description: g.description,
      admin: g.admin,
      require_mfa: g.require_mfa,
      members: [...g.members],
      all: g.entities.all || "",
      rules,
      dashboards: { all: g.dashboards.all, items: [...g.dashboards.items] },
      panels: { all: g.panels.all, items: [...g.panels.items] },
    };
    this._optionCache = null;
    this._error = "";
    this._render();
  }

  _draftPayload() {
    const d = this._draft;
    const entities = { all: d.all || null };
    for (const [scope] of SCOPES) {
      entities[scope] = {};
    }
    for (const r of d.rules) {
      if (r.key.trim()) {
        entities[r.scope][r.key.trim()] = r.level;
      }
    }
    return {
      name: d.name.trim(),
      description: d.description.trim(),
      admin: d.admin,
      require_mfa: d.require_mfa,
      members: d.members,
      entities,
      dashboards: d.dashboards,
      panels: d.panels,
    };
  }

  // ------------------------------------------------------------------ events

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-action]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.preventDefault();
        this._action(el.dataset.action, el.dataset);
      }),
    );
    if (!this._draft) {
      return;
    }
    const d = this._draft;
    const on = (sel, fn) => root.querySelectorAll(sel).forEach((el) => el.addEventListener("change", () => fn(el)));
    const onInput = (id, fn) => {
      const el = root.getElementById(id);
      el?.addEventListener("input", () => fn(el));
    };
    onInput("name", (el) => (d.name = el.value));
    onInput("description", (el) => (d.description = el.value));
    on("#admin", (el) => {
      d.admin = el.checked;
      this._render();
    });
    on("#require_mfa", (el) => (d.require_mfa = el.checked));
    on("#all", (el) => (d.all = el.value));
    on("[data-member]", (el) => {
      const id = el.dataset.member;
      d.members = el.checked ? [...d.members, id] : d.members.filter((m) => m !== id);
    });
    for (const kind of ["dashboards", "panels"]) {
      on(`[data-${kind}]`, (el) => {
        const key = el.dataset[kind];
        const items = d[kind].items.filter((i) => i !== key);
        d[kind].items = el.checked ? [...items, key] : items;
      });
    }
    on("[data-all]", (el) => {
      d[el.dataset.all].all = el.checked;
      this._render();
    });
    for (const picker of root.querySelectorAll("warden-picker[data-rule]")) {
      const rule = d.rules[Number(picker.dataset.rule)];
      picker.options = this._options(rule.scope);
      picker.value = rule.key;
      picker.placeholder = PICKER_PLACEHOLDERS[rule.scope];
      // An entity may not exist yet, and a domain can be typed in full.
      picker.customPattern = PICKER_CUSTOM[rule.scope] || null;
      picker.addEventListener("value-changed", (ev) => {
        rule.key = ev.detail.value;
        this._render();
      });
    }
    on("select[data-rule], input[data-rule]", (el) => {
      const rule = d.rules[Number(el.dataset.rule)];
      rule[el.dataset.field] = el.value;
      if (el.dataset.field === "scope") {
        rule.key = "";
      }
      this._render();
    });
  }

  async _action(action, data) {
    try {
      switch (action) {
        case "tab":
          this._tab = data.tab;
          this._render();
          return;
        case "setup":
          // warden-prompt.js, loaded on every page, runs the setup dialog. It
          // only loads with a fresh page, so fall back to the profile page.
          if (window.__wardenPrompt) {
            window.dispatchEvent(new CustomEvent("warden-mfa-setup"));
            return;
          }
        // falls through
        case "goto-security":
          history.pushState(null, "", "/profile/security");
          window.dispatchEvent(new CustomEvent("location-changed"));
          return;
        case "new":
          this._openEditor(null);
          return;
        case "edit":
          this._openEditor(this._info.groups.find((g) => g.id === data.id));
          return;
        case "cancel":
          this._draft = null;
          this._error = "";
          this._render();
          return;
        case "add-rule":
          this._draft.rules.push({ scope: "domains", key: "", level: "read" });
          this._render();
          return;
        case "remove-rule":
          this._draft.rules.splice(Number(data.index), 1);
          this._render();
          return;
        case "save": {
          const payload = this._draftPayload();
          if (!payload.name) {
            throw new Error("Give the group a name.");
          }
          if (this._draft.id) {
            await this._hass.callWS({ type: "warden/group/update", group_id: this._draft.id, ...payload });
          } else {
            await this._hass.callWS({ type: "warden/group/create", ...payload });
          }
          this._draft = null;
          await this._load();
          return;
        }
        case "delete":
          if (!confirm(`Delete the group "${this._draft.name}"? Its members lose what it grants.`)) {
            return;
          }
          await this._hass.callWS({ type: "warden/group/delete", group_id: this._draft.id });
          this._draft = null;
          await this._load();
          return;
        case "save-settings":
          await this._hass.callWS({
            type: "warden/settings/update",
            require_mfa_all: this.shadowRoot.getElementById("require_mfa_all").checked,
            mfa_grace_days: Number(this.shadowRoot.getElementById("mfa_grace_days").value || 0),
          });
          await this._load();
          return;
      }
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
    }
  }
}

customElements.define("warden-panel", WardenPanel);
