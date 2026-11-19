// Warden's two-factor prompt. Home Assistant loads this on every page (an
// "extra module"), so it reaches people who are already logged in: it follows
// the user's Warden status and, when 2FA becomes required, opens a dialog that
// walks them through Home Assistant's own setup flow (auth/setup_mfa).
//
//   grace       — asks once per browser session; "Later" dismisses it.
//   restricted  — the dialog can't be dismissed until 2FA is set up.
//
// The security panel opens the same dialog with a "warden-mfa-setup" event.
// Plain JS, no build step. Every server string goes through esc().

(() => {
  if (window.__wardenPrompt) {
    return;
  }
  window.__wardenPrompt = true;

  const LATER_KEY = "warden-mfa-later";
  const SETUP_EVENT = "warden-mfa-setup";

  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");

  // sessionStorage can be missing or throw (private windows, webviews).
  const sessionGet = (key) => {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  };
  const sessionSet = (key, value) => {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      // Then "Later" lasts until the next status change; that's fine.
    }
  };

  const FIELD_LABELS = { code: "Code", pin: "PIN", notify_service: "Send codes to" };
  const ERRORS = {
    invalid_code:
      "That code didn't work. Check that your device's clock is correct and try again.",
  };

  const STYLE = `
    :host {
      --warden-loud: var(--ha-color-fill-primary-loud-resting, var(--primary-color));
      --warden-loud-hover: var(--ha-color-fill-primary-loud-hover, var(--warden-loud));
      --warden-on-loud: var(--ha-color-on-primary-loud, #fff);
      position: fixed;
      inset: 0;
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: rgba(0, 0, 0, 0.5);
      font-family: var(--ha-font-family-body, Roboto, sans-serif);
      color: var(--primary-text-color);
    }
    .dialog {
      box-sizing: border-box;
      width: 100%;
      max-width: 440px;
      max-height: 100%;
      overflow: auto;
      padding: 24px;
      border-radius: var(--ha-dialog-border-radius, 24px);
      background: var(--card-background-color, var(--primary-background-color, #fff));
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .icon { font-size: 40px; line-height: 1; margin-bottom: 12px; }
    h2 { font-size: 22px; font-weight: 500; margin: 0 0 12px; }
    p { margin: 0 0 12px; line-height: 1.5; font-size: 15px; }
    .muted { color: var(--secondary-text-color); font-size: 14px; }
    .error { color: var(--error-color); font-size: 14px; }
    .qr { display: flex; justify-content: center; margin: 8px 0 12px; }
    .qr img { width: 200px; height: 200px; padding: 8px; background: #fff; border-radius: 8px; }
    code {
      font-family: var(--ha-font-family-code, monospace);
      font-size: 13px;
      word-break: break-all;
      user-select: all;
      padding: 2px 4px;
      border-radius: 4px;
      background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
    }
    label { display: flex; flex-direction: column; gap: 4px; margin: 12px 0; font-size: 14px; }
    label.choice { flex-direction: row; align-items: center; gap: 8px; margin: 8px 0; }
    input:not([type]), input[type="text"], select {
      font: inherit;
      font-size: 16px;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
    }
    input[name="code"], input[name="pin"] { letter-spacing: 0.2em; font-size: 20px; text-align: center; }
    input[type="radio"] { accent-color: var(--warden-loud); }
    .actions { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 20px; flex-wrap: wrap; }
    .actions .spacer { flex: 1; }
    button {
      font: inherit;
      font-size: 14px;
      font-weight: 500;
      padding: 10px 18px;
      border-radius: 20px;
      border: none;
      background: transparent;
      color: var(--primary-color);
      cursor: pointer;
    }
    button.primary { background: var(--warden-loud); color: var(--warden-on-loud); }
    button.primary:hover { background: var(--warden-loud-hover); }
    button.text { color: var(--secondary-text-color); padding: 10px 8px; }
    button:disabled { opacity: 0.5; cursor: default; }
  `;

  class WardenMfaDialog extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.step = "intro";
      this._busy = false;
    }

    // controller: { hass(), me, onClose(), onDone() }
    start(controller, { direct }) {
      this._c = controller;
      this._error = "";
      if (direct) {
        this._begin();
      } else {
        this.step = "intro";
        this._render();
      }
    }

    get mandatory() {
      return this._c.me?.mfa === "restricted";
    }

    // Past the intro, the dialog is mid-setup and status changes mustn't
    // close it (enrolling itself changes the status before the flow ends).
    get inProgress() {
      return this.step !== "intro";
    }

    refresh() {
      if (this.step === "intro") {
        this._render();
      }
    }

    _modules() {
      const me = this._c.me || {};
      const enrolled = new Set(me.mfa_modules || []);
      return (me.available_mfa_modules || []).filter((m) => !enrolled.has(m.id));
    }

    _begin() {
      const modules = this._modules();
      if (modules.length === 1) {
        this._startFlow(modules[0].id);
      } else if (modules.length === 0) {
        this.step = "none";
        this._render();
      } else {
        this.step = "choose";
        this._choice = modules[0].id;
        this._render();
      }
    }

    async _call(msg) {
      this._busy = true;
      this._render();
      try {
        return await this._c.hass().callWS(msg);
      } finally {
        this._busy = false;
      }
    }

    async _startFlow(moduleId) {
      this._error = "";
      try {
        this._handle(await this._call({ type: "auth/setup_mfa", mfa_module_id: moduleId }));
      } catch (err) {
        this._fail(err);
      }
    }

    async _submit() {
      const input = {};
      for (const el of this.shadowRoot.querySelectorAll("[data-field]")) {
        input[el.dataset.field] = el.value.trim();
      }
      this._error = "";
      try {
        this._handle(
          await this._call({ type: "auth/setup_mfa", flow_id: this._flow.flow_id, user_input: input }),
        );
      } catch (err) {
        this._fail(err);
      }
    }

    _handle(result) {
      if (result.type === "form") {
        this._flow = result;
        this.step = "form";
      } else if (result.type === "create_entry") {
        this.step = "done";
      } else {
        this._error = result.reason ? `Setup stopped: ${result.reason}` : "Setup stopped.";
        this.step = "failed";
      }
      this._render();
    }

    _fail(err) {
      this._error = err?.message || String(err);
      this.step = "failed";
      this._render();
    }

    // ------------------------------------------------------------- render

    _render() {
      let body;
      switch (this.step) {
        case "choose":
          body = this._renderChoose();
          break;
        case "form":
          body = this._renderForm();
          break;
        case "done":
          body = `
            <div class="icon">✅</div>
            <h2>You're all set</h2>
            <p>Two-factor authentication is on. From now on, you'll enter a code
            from your app when you log in.</p>
            <div class="actions"><button class="primary" data-action="done">Continue</button></div>`;
          break;
        case "failed":
          body = `
            <div class="icon">⚠️</div>
            <h2>Something went wrong</h2>
            <p class="error">${esc(this._error)}</p>
            <div class="actions">
              ${this.mandatory ? "" : `<button data-action="close">Close</button>`}
              <button class="primary" data-action="begin">Try again</button>
            </div>`;
          break;
        case "none":
          body = `
            <div class="icon">⚠️</div>
            <h2>Can't set up two-factor authentication here</h2>
            <p>No two-factor method is available. Ask an administrator for help.</p>
            <div class="actions">${this.mandatory ? this._logoutButton() : `<button data-action="close">Close</button>`}</div>`;
          break;
        default:
          body = this._renderIntro();
      }
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="title">${body}</div>`;
      const title = this.shadowRoot.querySelector("h2");
      if (title) {
        title.id = "title";
      }
      this._bind();
    }

    _renderIntro() {
      const me = this._c.me || {};
      if (this.mandatory) {
        return `
          <div class="icon">🔒</div>
          <h2>Set up two-factor authentication</h2>
          <p>Your account now has to use two-factor authentication. Until you
          set it up, you can't use Home Assistant.</p>
          <p class="muted">It takes about a minute with an authenticator app on your phone.</p>
          <div class="actions">
            ${this._logoutButton()}<span class="spacer"></span>
            <button class="primary" data-action="begin">Set up now</button>
          </div>`;
      }
      return `
        <div class="icon">🛡️</div>
        <h2>Set up two-factor authentication</h2>
        <p>This home now requires two-factor authentication for your account.
        Set it up before <b>${esc(fmtDate(me.mfa_deadline))}</b> to keep using
        Home Assistant.</p>
        <p class="muted">It takes about a minute with an authenticator app on your phone.</p>
        <div class="actions">
          <button data-action="later">Later</button>
          <button class="primary" data-action="begin">Set up now</button>
        </div>`;
    }

    _renderChoose() {
      const options = this._modules()
        .map(
          (m) => `
          <label class="choice"><input type="radio" name="module" value="${esc(m.id)}" ${
            m.id === this._choice ? "checked" : ""
          }> ${esc(m.name)}</label>`,
        )
        .join("");
      return `
        <h2>Choose a method</h2>
        ${options}
        <div class="actions">
          ${this.mandatory ? "" : `<button data-action="close">Cancel</button>`}
          <button class="primary" data-action="choose" ${this._busy ? "disabled" : ""}>Next</button>
        </div>`;
    }

    _renderForm() {
      const flow = this._flow;
      const ph = flow.description_placeholders || {};
      const fields = flow.data_schema || [];
      let intro;
      if (ph.qr_code) {
        // The QR code is an SVG from Home Assistant; as an <img> it can't run
        // anything, and the white box keeps it scannable in dark themes.
        // Home Assistant strips the SVG namespace (its own page inlines the
        // markup), and without it the browser won't draw an image.
        let svg = ph.qr_code;
        if (!/^<svg[^>]*\sxmlns=/.test(svg)) {
          svg = svg.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
        }
        const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
        intro = `
          <p>Scan this QR code with an authenticator app, such as Google
          Authenticator, Microsoft Authenticator, 1Password or Authy.</p>
          <div class="qr"><img alt="QR code for your authenticator app" src="${esc(src)}"></div>
          ${ph.code ? `<p class="muted">Can't scan it? Enter this key in the app instead:<br><code>${esc(ph.code)}</code></p>` : ""}
          <p>Then enter the 6-digit code the app shows.</p>`;
      } else if (fields.some((f) => f.name === "notify_service")) {
        intro = `<p>Choose where to send your login codes.</p>`;
      } else if (ph.notify_service) {
        intro = `<p>Enter the code sent to <b>${esc(ph.notify_service)}</b>.</p>`;
      } else {
        intro = `<p>Enter the code to finish setting up.</p>`;
      }

      const errors = flow.errors || {};
      const errorText = (key) => (key ? ERRORS[key] || `Error: ${key}` : "");
      const inputs = fields.map((f) => this._renderField(f, errorText(errors[f.name]))).join("");
      return `
        <h2>Set up two-factor authentication</h2>
        ${intro}
        <form>${inputs}</form>
        ${errors.base ? `<p class="error">${esc(errorText(errors.base))}</p>` : ""}
        <div class="actions">
          ${this.mandatory ? "" : `<button data-action="close">Cancel</button>`}
          <button class="primary" data-action="submit" ${this._busy ? "disabled" : ""}>${
            this._busy ? "Checking…" : "Continue"
          }</button>
        </div>`;
    }

    _renderField(field, error) {
      const label = FIELD_LABELS[field.name] || field.name;
      const name = esc(field.name);
      let control;
      if (field.type === "select") {
        const options = (field.options || []).map((o) => (Array.isArray(o) ? o : [o, o]));
        control = `<select data-field="${name}">${options
          .map(([value, text]) => `<option value="${esc(value)}">${esc(text)}</option>`)
          .join("")}</select>`;
      } else {
        const code = field.name === "code" || field.name === "pin";
        control = `<input data-field="${name}" name="${name}" ${
          code ? `inputmode="numeric" autocomplete="one-time-code"` : `autocomplete="off"`
        }>`;
      }
      return `<label>${esc(label)}${control}${error ? `<span class="error">${esc(error)}</span>` : ""}</label>`;
    }

    _logoutButton() {
      return `<button class="text" data-action="logout">Log out</button>`;
    }

    _bind() {
      for (const el of this.shadowRoot.querySelectorAll("[data-action]")) {
        el.addEventListener("click", (ev) => {
          ev.preventDefault();
          this._action(el.dataset.action);
        });
      }
      const form = this.shadowRoot.querySelector("form");
      if (form) {
        form.addEventListener("submit", (ev) => {
          ev.preventDefault();
          this._action("submit");
        });
        form.querySelector("input")?.focus();
      }
    }

    _action(action) {
      if (this._busy) {
        return;
      }
      switch (action) {
        case "begin":
          this._begin();
          return;
        case "choose":
          this._choice =
            this.shadowRoot.querySelector('input[name="module"]:checked')?.value || this._choice;
          this._startFlow(this._choice);
          return;
        case "submit":
          this._submit();
          return;
        case "later":
          sessionSet(LATER_KEY, this._c.me?.mfa_deadline || "1");
          this._c.onClose();
          return;
        case "close":
          if (!this.mandatory) {
            this._c.onClose();
          }
          return;
        case "done":
          this._c.onDone();
          return;
        case "logout":
          this._c.logout();
          return;
      }
    }
  }

  if (!customElements.get("warden-mfa-dialog")) {
    customElements.define("warden-mfa-dialog", WardenMfaDialog);
  }

  // ------------------------------------------------------------- controller

  const controller = {
    root: null,
    me: null,
    dialog: null,
    wasRestricted: false,

    hass() {
      return this.root.hass;
    },

    async start() {
      this.root = await waitFor(() => document.querySelector("home-assistant"));
      await waitFor(() => this.root.hass?.connection && this.root.hass.user);
      window.addEventListener(SETUP_EVENT, () => this.open(true));
      try {
        await this.root.hass.connection.subscribeMessage((me) => this.update(me), {
          type: "warden/me/subscribe",
        });
      } catch {
        // Warden isn't loaded (or is older); there's nothing to prompt for.
      }
    },

    update(me) {
      const previous = this.me;
      this.me = me;
      if (this.dialog?.inProgress) {
        return;
      }
      if (me.mfa === "restricted") {
        this.wasRestricted = true;
        this.open(false);
        return;
      }
      if (this.wasRestricted) {
        // Access came back some other way (an admin changed the rules, or
        // 2FA was set up in another tab): reload to get dashboards back.
        this.finish();
        return;
      }
      if (me.mfa === "grace") {
        const dismissed = sessionGet(LATER_KEY) === (me.mfa_deadline || "1");
        if (!dismissed && previous?.mfa !== "grace") {
          this.open(false);
        } else {
          this.dialog?.refresh();
        }
        return;
      }
      this.close();
    },

    open(direct) {
      if (!this.dialog) {
        this.dialog = document.createElement("warden-mfa-dialog");
        document.body.appendChild(this.dialog);
      } else if (this.dialog.inProgress) {
        return;
      }
      this.dialog.start(
        {
          hass: () => this.hass(),
          get me() {
            return controller.me;
          },
          onClose: () => this.close(),
          onDone: () => this.finish(),
          logout: () =>
            this.root.dispatchEvent(new CustomEvent("hass-logout", { bubbles: true, composed: true })),
        },
        { direct },
      );
    },

    close() {
      this.dialog?.remove();
      this.dialog = null;
    },

    // Start fresh so the sidebar and dashboards match the new access. The
    // Account security page disappears once 2FA is set up, so leave it.
    finish() {
      this.close();
      if (location.pathname.startsWith("/warden-security")) {
        location.assign("/");
      } else {
        location.reload();
      }
    },
  };

  function waitFor(get, interval = 250) {
    return new Promise((resolve) => {
      const check = () => {
        const value = get();
        if (value) {
          resolve(value);
        } else {
          setTimeout(check, interval);
        }
      };
      check();
    });
  }

  controller.start();
})();
