// ==UserScript==
// @name         Utopia Intel Capture
// @namespace    https://github.com/
// @version      0.2.0
// @description  Mirror sanitized Utopia intel transfers to your intel service.
// @match        https://utopia-game.com/*
// @match        https://www.utopia-game.com/*
// @grant        none
// ==/UserScript==

(() => {
  "use strict";

  const SETTINGS_KEY = "utopia-intel-capture-settings";
  const OFFICIAL_INTEL_HOST = "intel.utopia-game.com";
  const OFFICIAL_INTEL_PATH = "/parse/parse.php";
  let button;

  function readSettings() {
    try {
      return JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function configure() {
    const current = readSettings();
    const endpoint = window.prompt(
      "Intel API URL",
      current.endpoint || "https://your-api-host.example/api/v1/intel-submissions",
    );
    if (!endpoint) return null;
    const key = window.prompt("Kingdom ingestion key", current.key || "");
    if (!key) return null;
    const province = window.prompt("Your province name", current.province || "");
    if (!province) return null;
    const settings = { endpoint, key, province };
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    return settings;
  }

  async function sendPayload(payload) {
    const saved = readSettings();
    const settings = saved.endpoint && saved.key ? saved : null;
    if (!settings) {
      if (button) button.title = "Click to configure automatic intel mirroring";
      return false;
    }

    button.disabled = true;
    button.textContent = "Sending…";
    try {
      const response = await window.fetch(settings.endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${settings.key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
      if (!result.success) throw new Error(result.error || "Intel service rejected the submission");
      button.textContent = "Intel stored ✓";
      return true;
    } catch (error) {
      window.alert(`Intel submission failed: ${error.message}`);
      button.textContent = "Send intel";
      return false;
    } finally {
      button.disabled = false;
      window.setTimeout(() => {
        button.textContent = "Send intel";
      }, 3000);
    }
  }

  function captureVisiblePage() {
    const content = document.querySelector("main") || document.querySelector("#content") || document.body;
    const saved = readSettings();
    const settings = saved.endpoint && saved.key && saved.province ? saved : configure();
    if (!settings) return Promise.resolve(false);
    return sendPayload({
      url: window.location.href,
      prov: settings.province,
      data_html: content.innerHTML,
      data_simple: content.innerText,
    });
  }

  function decodeLegacyEscapes(value) {
    return String(value || "").replace(/%u([0-9a-f]{4})/gi, (_match, code) =>
      String.fromCharCode(Number.parseInt(code, 16)),
    );
  }

  function sanitizedOfficialPayload(data) {
    const fields =
      typeof data === "string" ? new URLSearchParams(data) : new URLSearchParams(data || {});
    const value = (name) => decodeLegacyEscapes(fields.get(name));
    return {
      url: value("url") || window.location.href,
      prov: value("prov"),
      data_html: value("raw_html"),
      data_simple: value("data"),
    };
  }

  function isOfficialIntelRequest(url) {
    try {
      const destination = new URL(url, window.location.href);
      return destination.hostname === OFFICIAL_INTEL_HOST && destination.pathname === OFFICIAL_INTEL_PATH;
    } catch {
      return false;
    }
  }

  function enableAutomaticMirror() {
    if (!window.jQuery) {
      window.console.warn("Utopia Intel Capture: jQuery was not available; automatic mirroring is disabled.");
      return;
    }
    window.jQuery(document).on("ajaxSend.utopiaIntelCapture", (_event, _xhr, options) => {
      if (!isOfficialIntelRequest(options.url)) return;
      const payload = sanitizedOfficialPayload(options.data);
      if (!payload.prov || (!payload.data_html && !payload.data_simple)) {
        window.console.warn("Utopia Intel Capture: skipped an empty official intel transfer.");
        return;
      }
      // Only the report, source URL, and submitting province are copied. In
      // particular, the official token, password cookie, resources, and attack
      // metadata never leave the official request.
      void sendPayload(payload);
    });
  }

  button = document.createElement("button");
  button.type = "button";
  button.textContent = "Send intel";
  button.title = "Shift-click to change the API connection";
  Object.assign(button.style, {
    position: "fixed",
    right: "16px",
    bottom: "16px",
    zIndex: "2147483647",
    padding: "10px 16px",
    border: "0",
    borderRadius: "6px",
    background: "#2f80ed",
    color: "white",
    fontWeight: "700",
    cursor: "pointer",
    boxShadow: "0 2px 8px rgba(0, 0, 0, 0.3)",
  });
  button.addEventListener("click", (event) => {
    if (event.shiftKey) configure();
    else captureVisiblePage();
  });
  document.body.appendChild(button);
  enableAutomaticMirror();
})();
