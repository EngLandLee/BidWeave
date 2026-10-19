/* SPDX-FileCopyrightText: 2026 BidWeave contributors
 * SPDX-License-Identifier: Apache-2.0
 * Read-only bridge for the public BidWeave appearance preference.
 * Authentication cookies and tokens are intentionally never inspected.
 */
(function applyBidWeaveTheme() {
  "use strict";

  var valid = { light: true, dark: true, system: true };
  var preference = null;
  var cookie = document.cookie.split(";").map(function (part) {
    return part.trim();
  }).find(function (part) {
    return part.indexOf("bidweave-theme=") === 0;
  });

  if (cookie) {
    var value = decodeURIComponent(cookie.slice("bidweave-theme=".length));
    if (valid[value]) preference = value;
  }

  if (!preference) {
    try {
      var stored = window.localStorage.getItem("bidweave.theme");
      if (stored && valid[stored]) preference = stored;
    } catch (_error) {
      // Storage can be disabled; the system preference remains sufficient.
    }
  }

  preference = preference || "system";
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var apply = function () {
    var theme = preference === "system" ? (media.matches ? "dark" : "light") : preference;
    document.documentElement.setAttribute("data-bw-theme", theme);
  };

  apply();
  if (preference === "system") {
    if (media.addEventListener) media.addEventListener("change", apply);
    else if (media.addListener) media.addListener(apply);
  }
})();
