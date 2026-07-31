// ==UserScript==
// @name         Utopia Intel Capture
// @namespace    https://github.com/
// @version      0.1.0
// @description  Explicitly send the currently visible Utopia page to your intel service.
// @match        https://utopia-game.com/*
// @match        https://www.utopia-game.com/*
// @grant        none
// ==/UserScript==

(() => {
  "use strict";

  const SETTINGS_KEY = "utopia-intel-capture-settings";

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

  async function capture(button) {
    const settings = readSettings().endpoint ? readSettings() : configure();
    if (!settings) return;

    const content = document.querySelector("main") || document.querySelector("#content") || document.body;
    button.disabled = true;
    button.textContent = "Sending…";
    try {
      const response = await window.fetch(settings.endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${settings.key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: window.location.href,
          prov: settings.province,
          data_html: content.innerHTML,
          data_simple: content.innerText,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
      button.textContent = "Intel stored ✓";
    } catch (error) {
      window.alert(`Intel submission failed: ${error.message}`);
      button.textContent = "Send intel";
    } finally {
      button.disabled = false;
      window.setTimeout(() => {
        button.textContent = "Send intel";
      }, 3000);
    }
  }

  const button = document.createElement("button");
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
    else capture(button);
  });
  document.body.appendChild(button);
})();
