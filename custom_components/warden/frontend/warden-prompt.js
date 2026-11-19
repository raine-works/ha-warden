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
    invalid_code: "That code didn't work. Make sure your device's clock is correct, then try the newest code.",
  };

  // Material Design Icons paths, as used across Home Assistant.
  const ICONS = {
    shield:
      "M12,1L3,5V11C3,16.55 6.84,21.74 12,23C17.16,21.74 21,16.55 21,11V5L12,1M12,7C13.4,7 14.8,8.1 14.8,9.5V11C15.4,11 16,11.6 16,12.3V15.8C16,16.4 15.4,17 14.7,17H9.2C8.6,17 8,16.4 8,15.7V12.2C8,11.6 8.6,11 9.2,11V9.5C9.2,8.1 10.6,7 12,7M12,8.2C11.2,8.2 10.5,8.7 10.5,9.5V11H13.5V9.5C13.5,8.7 12.8,8.2 12,8.2Z",
    check:
      "M12 2C6.5 2 2 6.5 2 12S6.5 22 12 22 22 17.5 22 12 17.5 2 12 2M10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z",
    alert:
      "M13,13H11V7H13M13,17H11V15H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z",
    copy: "M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z",
  };
  const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;

  const STYLE = `
    :host {
      --warden-loud: var(--ha-color-fill-primary-loud-resting, var(--primary-color));
      --warden-loud-hover: var(--ha-color-fill-primary-loud-hover, var(--warden-loud));
      --warden-on-loud: var(--ha-color-on-primary-loud, #fff);
      --warden-accent: var(--ha-color-primary-50, #009ac7);
      --warden-tint: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
      position: fixed;
      inset: 0;
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: rgba(0, 0, 0, 0.55);
      backdrop-filter: blur(2px);
      font-family: var(--ha-font-family-body, Roboto, sans-serif);
      color: var(--primary-text-color);
      -webkit-font-smoothing: antialiased;
    }
    :host([mandatory]) { background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(6px); }
    .dialog {
      box-sizing: border-box;
      width: 100%;
      max-width: 460px;
      max-height: 100%;
      overflow: auto;
      padding: 28px;
      border-radius: var(--ha-dialog-border-radius, 28px);
      background: var(--card-background-color, var(--primary-background-color, #fff));
      border: 1px solid var(--divider-color, transparent);
      box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
    }
    .dialog.wide { max-width: 640px; }

    .head { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 20px; }
    .badge {
      flex: none;
      display: grid;
      place-items: center;
      width: 48px;
      height: 48px;
      border-radius: 50%;
      color: var(--warden-accent);
      background: color-mix(in srgb, var(--warden-accent) 16%, transparent);
    }
    .badge svg { width: 26px; height: 26px; fill: currentColor; }
    .badge.warn { color: var(--warning-color, #f59e0b); background: color-mix(in srgb, var(--warning-color, #f59e0b) 16%, transparent); }
    .badge.bad { color: var(--error-color, #ef4444); background: color-mix(in srgb, var(--error-color, #ef4444) 16%, transparent); }
    .badge.good { color: var(--success-color, #22c55e); background: color-mix(in srgb, var(--success-color, #22c55e) 16%, transparent); }
    h2 { font-size: 22px; line-height: 1.25; font-weight: 500; margin: 2px 0 6px; }
    .sub { margin: 0; color: var(--secondary-text-color); font-size: 14px; line-height: 1.5; }
    p { margin: 0 0 12px; line-height: 1.55; font-size: 15px; }
    b { font-weight: 500; }

    .facts { list-style: none; padding: 0; margin: 0 0 4px; display: grid; gap: 8px; }
    .facts li {
      display: flex; gap: 12px; align-items: center;
      padding: 12px 14px; border-radius: 12px; background: var(--warden-tint); font-size: 14px;
    }
    .facts .n {
      flex: none; display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
      font-size: 13px; font-weight: 500; color: var(--warden-on-loud); background: var(--warden-loud);
    }

    .setup { display: grid; grid-template-columns: 200px 1fr; gap: 28px; align-items: start; }
    .qr {
      box-sizing: border-box; width: 200px; height: 200px; padding: 10px;
      background: #fff; border-radius: 16px;
    }
    .qr img { display: block; width: 100%; height: 100%; image-rendering: pixelated; }
    .steps { list-style: none; padding: 0; margin: 0; display: grid; gap: 20px; }
    .steps > li { display: grid; grid-template-columns: 28px 1fr; gap: 12px; }
    .steps .n {
      display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%;
      font-size: 14px; font-weight: 500; color: var(--warden-on-loud); background: var(--warden-loud);
    }
    .steps .title { font-size: 15px; font-weight: 500; margin: 3px 0 4px; }
    .steps .text { font-size: 14px; color: var(--secondary-text-color); line-height: 1.5; margin: 0 0 10px; }
    .key {
      display: flex; align-items: center; gap: 4px;
      padding: 4px 4px 4px 12px; border-radius: 10px; background: var(--warden-tint);
    }
    .key code {
      flex: 1; min-width: 0;
      font-family: var(--ha-font-family-code, ui-monospace, monospace);
      font-size: 13px; letter-spacing: 0.04em; word-break: break-word; user-select: all;
    }
    .open-app { margin: 0 0 10px; }
    .open-app a {
      display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
      font-size: 14px; font-weight: 500; padding: 10px 16px; border-radius: 20px;
      color: var(--warden-on-loud); background: var(--warden-loud);
    }

    .otp {
      box-sizing: border-box; width: 100%; max-width: 240px;
      font-family: var(--ha-font-family-code, ui-monospace, monospace);
      font-size: 28px; letter-spacing: 0.35em; text-indent: 0.35em; text-align: center;
      padding: 10px 12px; border-radius: 12px;
      border: 2px solid var(--divider-color);
      background: var(--card-background-color); color: var(--primary-text-color);
      outline: none;
    }
    .otp:focus { border-color: var(--warden-loud); }
    .otp.invalid { border-color: var(--error-color); }
    .otp::placeholder { color: color-mix(in srgb, var(--primary-text-color) 25%, transparent); }
    label.field { display: flex; flex-direction: column; gap: 6px; margin: 0 0 14px; font-size: 14px; }
    label.choice {
      display: flex; align-items: center; gap: 12px; margin: 0 0 8px; padding: 14px;
      border-radius: 12px; background: var(--warden-tint); font-size: 15px; cursor: pointer;
    }
    input[type="radio"] { accent-color: var(--warden-loud); width: 18px; height: 18px; margin: 0; }
    select, input.text {
      font: inherit; font-size: 16px; padding: 10px 12px; border-radius: 10px;
      border: 1px solid var(--divider-color); background: var(--card-background-color);
      color: var(--primary-text-color);
    }
    .error { color: var(--error-color); font-size: 14px; line-height: 1.5; margin: 8px 0 0; }

    .actions {
      display: flex; gap: 8px; align-items: center; justify-content: flex-end;
      margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--divider-color);
    }
    .actions .spacer { flex: 1; }
    button {
      display: inline-flex; align-items: center; gap: 6px;
      font: inherit; font-size: 14px; font-weight: 500;
      padding: 10px 20px; border-radius: 20px; border: none;
      background: transparent; color: var(--primary-text-color); cursor: pointer;
    }
    button:hover { background: var(--warden-tint); }
    button.primary { background: var(--warden-loud); color: var(--warden-on-loud); }
    button.primary:hover { background: var(--warden-loud-hover); }
    button.quiet { color: var(--secondary-text-color); padding: 10px 12px; }
    button.icon { padding: 8px; border-radius: 8px; color: var(--secondary-text-color); }
    button.icon svg { width: 18px; height: 18px; fill: currentColor; }
    button:disabled { opacity: 0.5; cursor: default; }
    .copied { font-size: 12px; color: var(--success-color, #22c55e); padding-right: 6px; }

    /* Phones: a bottom sheet, with the QR code on top. */
    @media (max-width: 640px) {
      :host { align-items: flex-end; padding: 0; }
      .dialog, .dialog.wide {
        max-width: none; padding: 24px 20px calc(16px + env(safe-area-inset-bottom));
        border-radius: 28px 28px 0 0; border-width: 1px 0 0;
      }
      .setup { grid-template-columns: 1fr; gap: 20px; }
      .qr { margin: 0 auto; width: 184px; height: 184px; }
      .otp { max-width: none; }
    }
  `;

  class WardenMfaDialog extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.step = "intro";
      this._busy = false;
    }

    // controller: { hass(), me, onClose(), onDone(), logout() }
    start(controller, { direct }) {
      this._c = controller;
      this._error = "";
      this.toggleAttribute("mandatory", this.mandatory);
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
        this.toggleAttribute("mandatory", this.mandatory);
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
        input[el.dataset.field] = el.value.replace(/\s+/g, "");
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
      // Keep what's been typed while it's being checked. A rejected code comes
      // back as a fresh form, empty and ready for the next code.
      const typed = {};
      for (const el of this.shadowRoot.querySelectorAll("[data-field]")) {
        typed[el.dataset.field] = el.value;
      }
      let body;
      let wide = false;
      switch (this.step) {
        case "choose":
          body = this._renderChoose();
          break;
        case "form":
          body = this._renderForm();
          wide = Boolean(this._flow.description_placeholders?.qr_code);
          break;
        case "done":
          body = `
            ${this._head("check", "good", "Two-factor authentication is on", "Your account is now protected.")}
            <p>Next time you log in, Home Assistant will ask for a code from your
            authenticator app after your password.</p>
            <div class="actions"><button class="primary" data-action="done">Continue</button></div>`;
          break;
        case "failed":
          body = `
            ${this._head("alert", "bad", "Something went wrong")}
            <p class="error">${esc(this._error)}</p>
            <div class="actions">
              ${this.mandatory ? this._logoutButton() : `<button data-action="close">Close</button>`}
              <span class="spacer"></span>
              <button class="primary" data-action="begin">Try again</button>
            </div>`;
          break;
        case "none":
          body = `
            ${this._head("alert", "bad", "Two-factor authentication isn't available")}
            <p>No two-factor method is set up in this Home Assistant. Ask an administrator for help.</p>
            <div class="actions">${this.mandatory ? this._logoutButton() : `<button data-action="close">Close</button>`}</div>`;
          break;
        default:
          body = this._renderIntro();
      }
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <div class="dialog ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="title">${body}</div>`;
      for (const [field, value] of Object.entries(typed)) {
        const el = this.shadowRoot.querySelector(`[data-field="${CSS.escape(field)}"]`);
        if (el && this._busy) {
          el.value = value;
        }
      }
      this._bind();
    }

    _head(iconName, tone, title, sub) {
      return `
        <div class="head">
          <div class="badge ${tone}">${icon(iconName)}</div>
          <div><h2 id="title">${esc(title)}</h2>${sub ? `<p class="sub">${sub}</p>` : ""}</div>
        </div>`;
    }

    _renderIntro() {
      const me = this._c.me || {};
      const facts = `
        <ul class="facts">
          <li><span class="n">1</span>Install an authenticator app on your phone, if you don't have one</li>
          <li><span class="n">2</span>Scan a QR code and enter the code it shows. It takes about a minute.</li>
        </ul>`;
      if (this.mandatory) {
        return `
          ${this._head(
            "shield",
            "bad",
            "Two-factor authentication required",
            "Your account has to use two-factor authentication. Until it's set up, you can't use Home Assistant.",
          )}
          ${facts}
          <div class="actions">
            ${this._logoutButton()}<span class="spacer"></span>
            <button class="primary" data-action="begin">Set up now</button>
          </div>`;
      }
      return `
        ${this._head(
          "shield",
          "warn",
          "Protect your account",
          `This home now requires two-factor authentication. Set it up by
          <b>${esc(fmtDate(me.mfa_deadline))}</b> to keep using Home Assistant.`,
        )}
        ${facts}
        <div class="actions">
          <button data-action="later">Remind me later</button>
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
        ${this._head("shield", "", "Choose a method", "How do you want to get your login codes?")}
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
      const errors = flow.errors || {};
      const errorText = (key) => (key ? ERRORS[key] || `Error: ${key}` : "");
      const actions = `
        <div class="actions">
          ${this.mandatory ? this._logoutButton() : `<button data-action="close">Cancel</button>`}
          <span class="spacer"></span>
          <button class="primary" data-action="submit" ${this._busy ? "disabled" : ""}>${
            this._busy ? "Checking…" : "Verify"
          }</button>
        </div>`;

      if (ph.qr_code) {
        return `
          ${this._head(
            "shield",
            "",
            "Set up two-factor authentication",
            "Use an authenticator app such as Google Authenticator, Microsoft Authenticator, 1Password or Authy.",
          )}
          <div class="setup">
            <div class="qr"><img alt="QR code for your authenticator app" src="${esc(qrSrc(ph.qr_code))}"></div>
            <ol class="steps">
              <li><span class="n">1</span><div>
                <div class="title">Add Home Assistant to your app</div>
                <p class="text">Scan the QR code with the app${
                  ph.code ? ", or enter this key in it" : ""
                }.</p>
                ${this._openInApp(ph.url)}
                ${
                  ph.code
                    ? `<div class="key"><code>${esc(ph.code.replace(/(.{4})(?=.)/g, "$1 "))}</code>
                       ${this._copied ? `<span class="copied">Copied</span>` : ""}
                       <button class="icon" data-action="copy" title="Copy key" aria-label="Copy key">${icon("copy")}</button></div>`
                    : ""
                }
              </div></li>
              <li><span class="n">2</span><div>
                <div class="title">Enter the 6-digit code</div>
                <p class="text">The app shows a new code every 30 seconds.</p>
                <form>${fields.map((f) => this._renderField(f, errors[f.name], true)).join("")}</form>
                ${errors.base ? `<p class="error">${esc(errorText(errors.base))}</p>` : ""}
                ${Object.entries(errors)
                  .filter(([k]) => k !== "base")
                  .map(([, v]) => `<p class="error">${esc(errorText(v))}</p>`)
                  .join("")}
              </div></li>
            </ol>
          </div>
          ${actions}`;
      }

      let sub = "Enter the code to finish setting up.";
      if (fields.some((f) => f.name === "notify_service")) {
        sub = "Choose where to send your login codes.";
      } else if (ph.notify_service) {
        sub = `Enter the code sent to <b>${esc(ph.notify_service)}</b>.`;
      }
      return `
        ${this._head("shield", "", "Set up two-factor authentication", sub)}
        <form>${fields.map((f) => this._renderField(f, errors[f.name], false)).join("")}</form>
        ${errors.base ? `<p class="error">${esc(errorText(errors.base))}</p>` : ""}
        ${actions}`;
    }

    // On a phone the QR code can't be scanned from its own screen, so offer
    // the otpauth:// link, which authenticator apps register for.
    _openInApp(url) {
      if (!url || !url.startsWith("otpauth://") || !matchMedia("(pointer: coarse)").matches) {
        return "";
      }
      return `<div class="open-app"><a href="${esc(url)}">Open in authenticator app</a></div>`;
    }

    _renderField(field, error, totp) {
      const label = FIELD_LABELS[field.name] || field.name;
      const name = esc(field.name);
      const invalid = error || this._flow?.errors?.base ? "invalid" : "";
      if (field.type === "select") {
        const options = (field.options || []).map((o) => (Array.isArray(o) ? o : [o, o]));
        return `<label class="field">${esc(label)}<select data-field="${name}">${options
          .map(([value, text]) => `<option value="${esc(value)}">${esc(text)}</option>`)
          .join("")}</select></label>`;
      }
      if (field.name === "code" || field.name === "pin") {
        // TOTP codes are always six digits; check as soon as all six are in.
        return `<input class="otp ${invalid}" data-field="${name}" ${totp ? `data-auto="6" maxlength="6" placeholder="000000"` : ""}
          inputmode="numeric" autocomplete="one-time-code" aria-label="${esc(label)}" ${this._busy ? "disabled" : ""}>`;
      }
      return `<label class="field">${esc(label)}<input class="text" data-field="${name}" autocomplete="off"></label>`;
    }

    _logoutButton() {
      return `<button class="quiet" data-action="logout">Log out</button>`;
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
        const first = form.querySelector("input, select");
        first?.focus();
        first?.select?.();
      }
      for (const el of this.shadowRoot.querySelectorAll("[data-auto]")) {
        el.addEventListener("input", () => {
          el.value = el.value.replace(/\D/g, "").slice(0, 6);
          el.classList.remove("invalid");
          if (el.value.length === Number(el.dataset.auto)) {
            this._action("submit");
          }
        });
      }
    }

    async _copy() {
      try {
        await navigator.clipboard.writeText(this._flow.description_placeholders.code);
        this._copied = true;
        this._render();
        setTimeout(() => {
          this._copied = false;
          if (this.step === "form") {
            this._render();
          }
        }, 2000);
      } catch {
        // No clipboard access (insecure origin); the key is still selectable.
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
        case "copy":
          this._copy();
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

  // The QR code is an SVG from Home Assistant. As an <img> it can't run
  // anything. Home Assistant strips the SVG namespace (its own page inlines
  // the markup), and without it the browser won't draw an image.
  function qrSrc(svg) {
    if (!/^<svg[^>]*\sxmlns=/.test(svg)) {
      svg = svg.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
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
