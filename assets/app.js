/* Event Signup Page Template — tiny, dependency-free page glue.
   1) Adds the .js class so the copy button is only shown when JS runs.
   2) "Copy RSVP text" copies a pre-built RSVP form with a fallback for
      older browsers, then shows friendly status text.
   No tracking, no network calls, nothing leaves the page. */

(function () {
  "use strict";

  document.body.classList.add("js");

  function readEventData() {
    var node = document.getElementById("event-data");
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (err) {
      return null;
    }
  }

  function setStatus(node, message) {
    if (node) node.textContent = message;
  }

  function copyViaLegacy(text) {
    var scratch = document.createElement("textarea");
    scratch.value = text;
    scratch.setAttribute("readonly", "readonly");
    scratch.style.position = "fixed";
    scratch.style.left = "-9999px";
    document.body.appendChild(scratch);
    scratch.select();
    try {
      return document.execCommand("copy");
    } catch (err) {
      return false;
    } finally {
      document.body.removeChild(scratch);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var data = readEventData();
    var button = document.getElementById("copy-rsvp");
    var status = document.getElementById("copy-status");
    if (!button || !data || !data.rsvp_text) return;

    button.textContent = "Copy RSVP text";
    button.addEventListener("click", function () {
      var text = data.rsvp_text;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            setStatus(status, "Copied! Paste it into an email, text, or note.");
            button.textContent = "Copied \u2713";
          },
          function () {
            var ok = copyViaLegacy(text);
            setStatus(status, ok ? "Copied! Paste it wherever it is handy." : "Copy did not work \u2014 press Ctrl+C after selecting, or just use the email button.");
            button.textContent = ok ? "Copied \u2713" : "Copy RSVP text";
          }
        );
      } else {
        var ok = copyViaLegacy(text);
        setStatus(status, ok ? "Copied! Paste it wherever it is handy." : "Copy did not work \u2014 just use the email button above.");
        button.textContent = ok ? "Copied \u2713" : "Copy RSVP text";
      }
    });
  });
})();
