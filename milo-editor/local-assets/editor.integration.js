(function () {
  "use strict";

  var editorPrefix = "/eos/editor/";
  var overlay;
  var trigger;
  var deployTrigger;
  var deployOverlay;
  var deployPollTimer;
  var deployBrowserPollTimer;
  var deployTaskRunning = false;
  var lastDeployStatus = { phase: "idle", running: false };
  var lastPath = "";
  var peekTimer;
  var dragged = false;
  var dragging = false;
  var dragOffset = { x: 0, y: 0 };
  var triggerStorageKey = "milo-outline-trigger-position";

  function projectId() {
    var path = location.pathname;
    if (!path.startsWith(editorPrefix)) return null;
    var part = path.slice(editorPrefix.length).split("/")[0];
    return part && !["teases", "create", "help", "login", "assets", "vendor"].includes(part)
      ? decodeURIComponent(part)
      : null;
  }

  async function loadExistingTeases() {
    var elements = deployElements();
    if (elements.targetSelect) elements.targetSelect.dataset.loaded = "0";
    if (!elements.targetSelect) return;
    if (elements.targetSelect.dataset.loaded === "1") return;
    var previous = (elements.target.value || localStorage.getItem(deployStorageKey(projectId())) || "").trim();
    elements.targetSelect.disabled = true;
    elements.targetSelect.innerHTML = '<option value="">Loading Milovana EOS teases…</option>';
    try {
      var response = await fetch("/api/deploy/milovana/teases", { cache: "no-store" });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not load existing teases");
      var teases = Array.isArray(payload.teases) ? payload.teases : [];
      elements.targetSelect.innerHTML = '<option value="">Select an existing EOS tease…</option>' + teases.map(function (tease) {
        var title = String(tease.title || ("Tease #" + tease.id)).replace(/[&<>"']/g, function (ch) {
          return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
        return '<option value="' + tease.id + '">#' + tease.id + ' · ' + title + '</option>';
      }).join("");
      elements.targetSelect.disabled = false;
      elements.targetSelect.dataset.loaded = "1";
      if (previous && teases.some(function (tease) { return tease.id === previous; })) {
        elements.targetSelect.value = previous;
      }
    } catch (_error) {
      elements.targetSelect.innerHTML = '<option value="">Could not load the list; enter an ID manually</option>';
      elements.targetSelect.disabled = false;
      elements.targetSelect.dataset.loaded = "0";
    }
  }

  function closeGraph() {
    if (overlay) overlay.hidden = true;
    schedulePeek();
  }

  function deployStorageKey(id) {
    return "milo-deploy-target-" + id;
  }

  function formatBytes(value) {
    var bytes = Number(value) || 0;
    if (bytes >= 1000 * 1000 * 1000) return (bytes / (1000 * 1000 * 1000)).toFixed(2) + " GB";
    if (bytes >= 1000 * 1000) return Math.round(bytes / (1000 * 1000)) + " MB";
    if (bytes >= 1000) return Math.round(bytes / 1000) + " KB";
    return bytes + " B";
  }

  function deployElements() {
    if (!deployOverlay) return {};
    return {
      target: deployOverlay.querySelector("#milo-deploy-target"),
      targetSelect: deployOverlay.querySelector("#milo-deploy-target-select"),
      modeExisting: deployOverlay.querySelector("#milo-deploy-mode-existing"),
      modeCreate: deployOverlay.querySelector("#milo-deploy-mode-create"),
      existingSection: deployOverlay.querySelector("#milo-deploy-existing"),
      createSection: deployOverlay.querySelector("#milo-deploy-create"),
      createTitle: deployOverlay.querySelector("#milo-deploy-title"),
      confirmTerms: deployOverlay.querySelector("#milo-deploy-confirm-terms"),
      confirmResponsibility: deployOverlay.querySelector("#milo-deploy-confirm-responsibility"),
      confirmAdults: deployOverlay.querySelector("#milo-deploy-confirm-adults"),
      summary: deployOverlay.querySelector("#milo-deploy-summary"),
      auth: deployOverlay.querySelector("#milo-deploy-auth"),
      browserOpen: deployOverlay.querySelector("#milo-deploy-browser-open"),
      progress: deployOverlay.querySelector("#milo-deploy-progress"),
      bar: deployOverlay.querySelector("#milo-deploy-bar"),
      status: deployOverlay.querySelector("#milo-deploy-status"),
      start: deployOverlay.querySelector("#milo-deploy-start"),
      retry: deployOverlay.querySelector("#milo-deploy-retry"),
      stop: deployOverlay.querySelector("#milo-deploy-stop"),
      remote: deployOverlay.querySelector("#milo-deploy-remote")
    };
  }

  function setDeployStatus(message, kind) {
    var elements = deployElements();
    if (!elements.status) return;
    elements.status.textContent = message || "";
    elements.status.dataset.kind = kind || "info";
  }

  function updateDeployProgress(status) {
    lastDeployStatus = status || { phase: "idle", running: false };
    deployTaskRunning = !!lastDeployStatus.running;
    var elements = deployElements();
    if (!elements.progress) return;
    var total = Number(status.total) || 0;
    var completed = Number(status.completed) || 0;
    var percent = total ? Math.round(completed * 100 / total) : 0;
    elements.progress.hidden = status.phase === "idle";
    elements.bar.style.width = Math.max(0, Math.min(100, percent)) + "%";
    if (elements.start && deployTaskRunning) elements.start.disabled = true;
    if (elements.retry) {
      elements.retry.hidden = !["failed", "stopped"].includes(status.phase);
      elements.retry.disabled = deployTaskRunning;
    }
    if (elements.stop) {
      elements.stop.hidden = !deployTaskRunning;
      elements.stop.disabled = status.phase === "stopping";
    }
    if (status.phase === "create") {
      elements.progress.hidden = false;
      elements.bar.style.width = "0%";
      setDeployStatus("Creating a new tease on Milovana…", "info");
    } else if (status.phase === "created") {
      setDeployStatus("Created Milovana tease #" + status.teaseId + "; processing media…", "info");
      if (elements.target) elements.target.value = status.teaseId || "";
      var currentProjectId = projectId();
      if (currentProjectId && status.teaseId) {
        localStorage.setItem(deployStorageKey(currentProjectId), String(status.teaseId));
      }
    } else if (status.phase === "media") {
      setDeployStatus(
        (status.resuming ? "Resuming media " : "Media ") + completed + " / " + total +
        (status.skipped ? " · skipped " + status.skipped : "") +
        " · uploaded " + (status.uploaded || 0) + " · reused " + (status.reused || 0) +
        (status.current ? " · " + status.current : ""),
        "info"
      );
    } else if (status.phase === "validate") {
      elements.bar.style.width = "0%";
      setDeployStatus(
        status.remoteChanged
          ? "Changes were detected on Milovana; rechecking media and filling any missing items…"
          : "Asking Milovana to pre-validate the EOS script…",
        "info"
      );
    } else if (status.phase === "save") {
      elements.bar.style.width = "0%";
      setDeployStatus("Validation passed. Saving the full EOS script before resuming media transfer…", "info");
    } else if (status.phase === "stopping") {
      setDeployStatus("Stopping Deploy; it will stop safely after the current network request finishes…", "info");
    } else if (status.phase === "stopped") {
      setDeployStatus("Deploy stopped. Completed media will be reused on the next Deploy.", "info");
      elements.start.disabled = false;
      if (elements.stop) elements.stop.hidden = true;
      clearInterval(deployPollTimer);
      deployPollTimer = null;
    } else if (status.phase === "done") {
      elements.bar.style.width = "100%";
      setDeployStatus(
        "Deploy complete. Skipped " + (status.skipped || 0) + ", uploaded " + (status.uploaded || 0) + ", reused " + (status.reused || 0) + "。",
        "success"
      );
      elements.start.disabled = false;
      if (status.editorUrl) {
        elements.remote.href = status.editorUrl;
        elements.remote.hidden = false;
      }
      clearInterval(deployPollTimer);
      deployPollTimer = null;
    } else if (status.phase === "failed") {
      setDeployStatus(
        (status.error || "Deploy failed.") + " Completed media are checkpointed; use Retry / Resume to continue from this point.",
        "error"
      );
      elements.start.disabled = false;
      clearInterval(deployPollTimer);
      deployPollTimer = null;
    }
  }

  async function pollDeployStatus() {
    var id = projectId();
    if (!id || !deployOverlay) return null;
    try {
      var response = await fetch("/api/projects/" + encodeURIComponent(id) + "/deploy/milovana/status", { cache: "no-store" });
      if (!response.ok) return null;
      var payload = await response.json();
      updateDeployProgress(payload);
      return payload;
    } catch (_error) {
      // The active POST will surface the useful error.
      return null;
    }
  }

  async function loadBrowserStatus(preserveTaskStatus) {
    if (!deployOverlay || deployOverlay.hidden) return false;
    var elements = deployElements();
    try {
      var response = await fetch("/api/deploy/milovana/browser/status", { cache: "no-store" });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not read Milovana browser status");
      if (payload.ready) {
        elements.auth.textContent = "Browser: signed in to Milovana (real Chrome session)";
        elements.auth.dataset.kind = "success";
        if (!deployTaskRunning) elements.start.disabled = false;
        elements.browserOpen.textContent = "Open browser";
        if (!preserveTaskStatus && !deployTaskRunning) {
          setDeployStatus("Ready. Media uploads and Restore will run in the signed-in Milovana browser.", "info");
        }
        clearInterval(deployBrowserPollTimer);
        deployBrowserPollTimer = null;
        loadExistingTeases();
        return true;
      }
      if (!deployTaskRunning) elements.start.disabled = true;
      elements.auth.textContent = payload.running ? "Browser: open, but sign-in/Cloudflare verification is not complete" : "Browser: not open";
      elements.auth.dataset.kind = payload.running ? "info" : "error";
      elements.browserOpen.textContent = payload.running ? "Switch to Milovana browser" : "Open Milovana browser";
      if (!preserveTaskStatus && !deployTaskRunning) {
        setDeployStatus(payload.message || "Open the dedicated browser and sign in to Milovana.", "info");
      }
      if (payload.running && !deployBrowserPollTimer) {
        deployBrowserPollTimer = setInterval(loadBrowserStatus, 1500);
      }
      return false;
    } catch (error) {
      if (!deployTaskRunning) elements.start.disabled = true;
      elements.auth.textContent = "Browser: status check failed";
      elements.auth.dataset.kind = "error";
      if (!preserveTaskStatus && !deployTaskRunning) setDeployStatus(error.message || String(error), "error");
      return false;
    }
  }

  async function openMilovanaBrowser() {
    var elements = deployElements();
    elements.browserOpen.disabled = true;
    setDeployStatus("Opening the dedicated Milovana Chrome window…", "info");
    try {
      var createNew = !!(elements.modeCreate && elements.modeCreate.checked);
      var target = createNew ? "" : (elements.target.value || (elements.targetSelect && elements.targetSelect.value) || "").trim();
      var browserRequest = /^\d+$/.test(target) ? { teaseId: target } : {};
      var response = await fetch("/api/deploy/milovana/browser/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(browserRequest)
      });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not open the Milovana browser");
      setDeployStatus("The browser is open. Sign in to Milovana there; complete any Cloudflare verification if shown.", "info");
      clearInterval(deployBrowserPollTimer);
      deployBrowserPollTimer = null;
      deployBrowserPollTimer = setInterval(loadBrowserStatus, 1500);
      await loadBrowserStatus(deployTaskRunning);
    } catch (error) {
      setDeployStatus(error.message || String(error), "error");
    } finally {
      elements.browserOpen.disabled = false;
    }
  }

  async function loadDeployPlan(preserveTaskStatus) {
    var id = projectId();
    if (!id) return;
    var elements = deployElements();
    if (!preserveTaskStatus && !deployTaskRunning) {
      elements.start.disabled = true;
      elements.remote.hidden = true;
      setDeployStatus("Checking local deployment resources…", "info");
    }
    try {
      var response = await fetch("/api/projects/" + encodeURIComponent(id) + "/deploy/milovana/plan", { cache: "no-store" });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not generate the deployment plan");
      elements.summary.textContent = payload.mediaCount + " media items (" + payload.imageCount + " images + " + payload.audioCount + " audio), " + formatBytes(payload.totalBytes);
      if (elements.createTitle && !elements.createTitle.value) elements.createTitle.value = payload.projectTitle || id;
      await loadBrowserStatus(!!preserveTaskStatus || deployTaskRunning);
    } catch (error) {
      elements.summary.textContent = "";
      setDeployStatus(error.message || String(error), "error");
    }
  }

  function syncDeployMode() {
    var elements = deployElements();
    var createNew = !!(elements.modeCreate && elements.modeCreate.checked);
    if (elements.existingSection) elements.existingSection.hidden = createNew;
    if (elements.createSection) elements.createSection.hidden = !createNew;
  }

  async function startDeploy(resumeFromStatus) {
    var id = projectId();
    if (!id) return;
    var elements = deployElements();
    var createNew = !!(elements.modeCreate && elements.modeCreate.checked);
    var target = (elements.target.value || (elements.targetSelect && elements.targetSelect.value) || "").trim();
    var resumeTarget = resumeFromStatus ? String((lastDeployStatus && lastDeployStatus.teaseId) || "").trim() : "";
    var requestBody;
    if (/^\d+$/.test(resumeTarget)) {
      target = resumeTarget;
      createNew = false;
      requestBody = { teaseId: target, createNew: false, resume: true };
      localStorage.setItem(deployStorageKey(id), target);
      if (elements.target) elements.target.value = target;
      if (elements.modeExisting) elements.modeExisting.checked = true;
      if (elements.modeCreate) elements.modeCreate.checked = false;
      syncDeployMode();
    } else if (createNew) {
      var title = (elements.createTitle.value || "").trim();
      if (!title) {
        setDeployStatus("A title is required to create a new Milovana tease.", "error");
        elements.createTitle.focus();
        return;
      }
      if (!elements.confirmTerms.checked || !elements.confirmResponsibility.checked || !elements.confirmAdults.checked) {
        setDeployStatus("Complete the three required confirmations before creating a new tease.", "error");
        return;
      }
      requestBody = {
        createNew: true,
        title: title,
        confirmations: {
          terms: true,
          responsibility: true,
          adultsOnly: true
        }
      };
    } else {
      if (!/^\d+$/.test(target)) {
        setDeployStatus("Enter a numeric Milovana tease ID.", "error");
        elements.target.focus();
        return;
      }
      localStorage.setItem(deployStorageKey(id), target);
      requestBody = { teaseId: target, createNew: false };
    }
    elements.start.disabled = true;
    if (elements.retry) {
      elements.retry.hidden = true;
      elements.retry.disabled = true;
    }
    deployTaskRunning = true;
    if (elements.stop) {
      elements.stop.hidden = false;
      elements.stop.disabled = false;
    }
    elements.remote.hidden = true;
    elements.progress.hidden = false;
    elements.bar.style.width = "0%";
    setDeployStatus(resumeFromStatus ? "Resuming media from checkpoint…" : "Connecting to Milovana…", "info");
    clearInterval(deployPollTimer);
    deployPollTimer = setInterval(pollDeployStatus, 700);
    try {
      var response = await fetch("/api/projects/" + encodeURIComponent(id) + "/deploy/milovana", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
      });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Deploy failed");
      if (payload.phase === "stopped" || payload.stopped) {
        updateDeployProgress({ ...payload, phase: "stopped", running: false });
      } else {
        updateDeployProgress({ phase: "done", running: false, ...payload });
      }
    } catch (error) {
      var latest = await pollDeployStatus();
      if (!latest || !latest.running) {
        clearInterval(deployPollTimer);
        deployPollTimer = null;
        deployTaskRunning = false;
        elements.start.disabled = false;
        if (!latest || latest.phase !== "failed") {
          setDeployStatus(error.message || String(error), "error");
        }
      }
    }
  }

  async function stopDeploy() {
    var id = projectId();
    if (!id || !deployTaskRunning) return;
    var elements = deployElements();
    if (elements.stop) elements.stop.disabled = true;
    setDeployStatus("Requesting Deploy stop…", "info");
    try {
      var response = await fetch("/api/projects/" + encodeURIComponent(id) + "/deploy/milovana/stop", { method: "POST" });
      var payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Could not stop Deploy");
      updateDeployProgress(payload);
      if (!deployPollTimer && payload.running) deployPollTimer = setInterval(pollDeployStatus, 700);
    } catch (error) {
      if (elements.stop) elements.stop.disabled = false;
      setDeployStatus(error.message || String(error), "error");
    }
  }

  function hideDeploy() {
    if (deployOverlay) deployOverlay.hidden = true;
    clearInterval(deployBrowserPollTimer);
    deployBrowserPollTimer = null;
  }

  function buildDeployOverlay() {
    deployOverlay = document.createElement("section");
    deployOverlay.id = "milo-deploy-overlay";
    deployOverlay.hidden = true;
    deployOverlay.innerHTML =
      '<div class="milo-deploy-card">' +
      '<header><div><strong>Deploy to Milovana</strong><span>Upload media + Restore EOS script</span></div><button type="button" id="milo-deploy-close" aria-label="Hide Deploy window" title="Hide; Deploy will continue in the background">×</button></header>' +
      '<main>' +
      '<div class="milo-deploy-modes">' +
      '<label><input type="radio" name="milo-deploy-mode" id="milo-deploy-mode-existing" checked> Use an existing tease</label>' +
      '<label><input type="radio" name="milo-deploy-mode" id="milo-deploy-mode-create"> Create a new tease on Milovana</label>' +
      '</div>' +
      '<div id="milo-deploy-existing" class="milo-deploy-section">' +
      '<label for="milo-deploy-target-select">Existing EOS tease</label>' +
      '<select id="milo-deploy-target-select"><option value="">Load list after sign-in…</option></select>' +
      '<label for="milo-deploy-target" class="milo-deploy-secondary-label">Or enter a tease ID manually</label>' +
      '<input id="milo-deploy-target" inputmode="numeric" autocomplete="off" placeholder="e.g. 82510">' +
      '</div>' +
      '<div id="milo-deploy-create" class="milo-deploy-section" hidden>' +
      '<label for="milo-deploy-title">New tease title</label>' +
      '<input id="milo-deploy-title" autocomplete="off" placeholder="Tease title">' +
      '<div class="milo-deploy-consents">' +
      '<label><input type="checkbox" id="milo-deploy-confirm-terms"> I have read and accept the <a href="https://milovana.com/pages/tos.php" target="_blank" rel="noopener">Milovana Terms of Service</a>.</label>' +
      '<label><input type="checkbox" id="milo-deploy-confirm-responsibility"> I understand that I am responsible for uploaded content and will follow applicable laws and rules.</label>' +
      '<label><input type="checkbox" id="milo-deploy-confirm-adults"> I confirm that all models and fictional characters are 18 or older.</label>' +
      '</div>' +
      '</div>' +
      '<div id="milo-deploy-summary" class="milo-deploy-summary"></div>' +
      '<div class="milo-deploy-browser"><div id="milo-deploy-auth" class="milo-deploy-auth"></div><button type="button" id="milo-deploy-browser-open">Open Milovana browser</button></div>' +
      '<div id="milo-deploy-progress" class="milo-deploy-progress" hidden><span id="milo-deploy-bar"></span></div>' +
      '<div id="milo-deploy-status" class="milo-deploy-status"></div>' +
      '</main>' +
      '<footer><a id="milo-deploy-remote" target="_blank" rel="noopener" hidden>Open Milovana Editor</a><button type="button" id="milo-deploy-retry" hidden>Retry / Resume</button><button type="button" id="milo-deploy-stop" class="milo-deploy-stop" hidden>Stop Deploy</button><button type="button" id="milo-deploy-start" disabled>Deploy</button></footer>' +
      '</div>';
    deployOverlay.querySelector("#milo-deploy-close").addEventListener("click", hideDeploy);
    deployOverlay.querySelector("#milo-deploy-start").addEventListener("click", function () { startDeploy(false); });
    deployOverlay.querySelector("#milo-deploy-retry").addEventListener("click", function () { startDeploy(true); });
    deployOverlay.querySelector("#milo-deploy-stop").addEventListener("click", stopDeploy);
    deployOverlay.querySelector("#milo-deploy-browser-open").addEventListener("click", openMilovanaBrowser);
    deployOverlay.querySelector("#milo-deploy-mode-existing").addEventListener("change", syncDeployMode);
    deployOverlay.querySelector("#milo-deploy-mode-create").addEventListener("change", syncDeployMode);
    deployOverlay.querySelector("#milo-deploy-target-select").addEventListener("change", function (event) {
      if (event.target.value) deployOverlay.querySelector("#milo-deploy-target").value = event.target.value;
    });
    // Do not close the Deploy dialog by clicking the backdrop. A text-selection
    // drag can begin inside the card and end over the backdrop; browsers may
    // synthesize the resulting click on the overlay itself, which made copying
    // status/error text accidentally close the dialog. Keep closing explicit
    // via the dedicated close button instead.
    document.body.appendChild(deployOverlay);
  }

  async function openDeploy() {
    var id = projectId();
    if (!id) return;
    if (!deployOverlay) buildDeployOverlay();
    var elements = deployElements();
    elements.target.value = localStorage.getItem(deployStorageKey(id)) || "";
    syncDeployMode();
    deployOverlay.hidden = false;
    var status = await pollDeployStatus();
    var running = !!(status && status.running);
    var preserveTaskStatus = !!(status && status.phase && status.phase !== "idle");
    if (running && !deployPollTimer) deployPollTimer = setInterval(pollDeployStatus, 700);
    await loadDeployPlan(preserveTaskStatus);
  }

  function buildDeployTrigger() {
    deployTrigger = document.createElement("button");
    deployTrigger.id = "milo-deploy-trigger";
    deployTrigger.type = "button";
    deployTrigger.title = "Open Deploy to Milovana";
    deployTrigger.setAttribute("aria-label", "Open Deploy to Milovana");
    deployTrigger.innerHTML = '<span aria-hidden="true">↑</span><span>Deploy</span>';
    deployTrigger.addEventListener("click", openDeploy);
    deployTrigger.addEventListener("pointerenter", revealTrigger);
    deployTrigger.addEventListener("pointerleave", function () { schedulePeek(700); });
    deployTrigger.addEventListener("focus", revealTrigger);
    deployTrigger.addEventListener("blur", function () { schedulePeek(700); });
    document.body.appendChild(deployTrigger);
    restoreTriggerPosition();
  }

  function openGraph() {
    var id = projectId();
    if (!id) return;
    if (!overlay) buildOverlay();
    var frame = overlay.querySelector("iframe");
    var expected = "/milo/tease-graph/" + encodeURIComponent(id) + "?project=" + encodeURIComponent(id);
    if (frame.getAttribute("src") !== expected) frame.setAttribute("src", expected);
    overlay.hidden = false;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function revealTrigger() {
    clearTimeout(peekTimer);
    if (trigger) trigger.classList.remove("is-peeking");
    if (deployTrigger) deployTrigger.classList.remove("is-peeking");
  }

  function schedulePeek(delay) {
    clearTimeout(peekTimer);
    if (!trigger || trigger.hidden || dragging) return;
    peekTimer = setTimeout(function () {
      if (!dragging && document.activeElement !== trigger && document.activeElement !== deployTrigger) {
        trigger.classList.add("is-peeking");
        if (deployTrigger) deployTrigger.classList.add("is-peeking");
      }
    }, delay || 1400);
  }

  function syncDeployTriggerPosition() {
    if (!trigger || !deployTrigger) return;
    var side = trigger.dataset.side === "left" ? "left" : "right";
    var top = parseFloat(trigger.style.top) || trigger.getBoundingClientRect().top || 8;
    deployTrigger.dataset.side = side;
    deployTrigger.style.top = (top + trigger.offsetHeight + 6) + "px";
    deployTrigger.style.left = side === "left" ? "0" : "auto";
    deployTrigger.style.right = side === "right" ? "0" : "auto";
  }

  function saveTriggerPosition() {
    if (!trigger) return;
    try {
      localStorage.setItem(triggerStorageKey, JSON.stringify({
        side: trigger.dataset.side || "right",
        top: parseFloat(trigger.style.top) || Math.round(window.innerHeight * 0.45)
      }));
    } catch (_error) {
      // Position persistence is optional.
    }
  }

  function applyTriggerPosition(position) {
    if (!trigger) return;
    var side = position && position.side === "left" ? "left" : "right";
    var top = clamp(
      Number(position && position.top) || Math.round(window.innerHeight * 0.45),
      8,
      Math.max(8, window.innerHeight - trigger.offsetHeight - (deployTrigger ? deployTrigger.offsetHeight + 6 : 0) - 8)
    );
    trigger.dataset.side = side;
    trigger.style.top = top + "px";
    trigger.style.left = side === "left" ? "0" : "auto";
    trigger.style.right = side === "right" ? "0" : "auto";
    syncDeployTriggerPosition();
  }

  function restoreTriggerPosition() {
    var saved;
    try {
      saved = JSON.parse(localStorage.getItem(triggerStorageKey) || "null");
    } catch (_error) {
      saved = null;
    }
    applyTriggerPosition(saved);
  }

  function handlePointerMove(event) {
    if (!dragging || !trigger) return;
    var left = clamp(event.clientX - dragOffset.x, 0, window.innerWidth - trigger.offsetWidth);
    var top = clamp(event.clientY - dragOffset.y, 0, window.innerHeight - trigger.offsetHeight - (deployTrigger ? deployTrigger.offsetHeight + 6 : 0));
    if (Math.abs(event.movementX) + Math.abs(event.movementY) > 1) dragged = true;
    trigger.dataset.side = "free";
    trigger.style.left = left + "px";
    trigger.style.right = "auto";
    trigger.style.top = top + "px";
    if (deployTrigger) {
      deployTrigger.style.left = left + "px";
      deployTrigger.style.right = "auto";
      deployTrigger.style.top = (top + trigger.offsetHeight + 6) + "px";
    }
  }

  function finishDrag(event) {
    if (!dragging || !trigger) return;
    dragging = false;
    trigger.classList.remove("is-dragging");
    trigger.releasePointerCapture?.(event.pointerId);
    var rect = trigger.getBoundingClientRect();
    applyTriggerPosition({
      side: rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right",
      top: rect.top
    });
    saveTriggerPosition();
    trigger.blur();
    schedulePeek(900);
  }

  function buildOverlay() {
    overlay = document.createElement("section");
    overlay.id = "milo-outline-overlay";
    overlay.hidden = true;
    overlay.innerHTML =
      '<header><strong>Milo · Tease Graph</strong><span>Interactive outline for the current tease</span>' +
      '<button type="button" aria-label="Close outline graph">Back to EOS Editor</button></header>' +
      '<iframe title="Tease Graph editor"></iframe>';
    overlay.querySelector("button").addEventListener("click", closeGraph);
    document.body.appendChild(overlay);
  }

  function buildTrigger() {
    trigger = document.createElement("button");
    trigger.id = "milo-outline-trigger";
    trigger.type = "button";
    trigger.title = "Drag to reposition; click to open the outline graph";
    trigger.setAttribute("aria-label", "Open the outline graph for the current tease");
    trigger.innerHTML = '<span aria-hidden="true">✦</span><span>Outline Graph</span>';
    trigger.addEventListener("click", function (event) {
      if (dragged) {
        event.preventDefault();
        dragged = false;
        return;
      }
      openGraph();
    });
    trigger.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      dragged = false;
      dragging = true;
      revealTrigger();
      var rect = trigger.getBoundingClientRect();
      dragOffset = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      trigger.classList.add("is-dragging");
      trigger.setPointerCapture?.(event.pointerId);
    });
    trigger.addEventListener("pointermove", handlePointerMove);
    trigger.addEventListener("pointerup", finishDrag);
    trigger.addEventListener("pointercancel", finishDrag);
    trigger.addEventListener("pointerenter", revealTrigger);
    trigger.addEventListener("pointerleave", function () { schedulePeek(700); });
    trigger.addEventListener("focus", revealTrigger);
    trigger.addEventListener("blur", function () { schedulePeek(700); });
    document.body.appendChild(trigger);
    restoreTriggerPosition();
  }

  function sync() {
    if (lastPath === location.pathname) return;
    lastPath = location.pathname;
    if (!trigger) buildTrigger();
    if (!deployTrigger) buildDeployTrigger();
    trigger.hidden = !projectId();
    deployTrigger.hidden = !projectId();
    if (!trigger.hidden) syncDeployTriggerPosition();
    if (!trigger.hidden) schedulePeek();
    if (overlay && !overlay.hidden && !projectId()) closeGraph();
  }

  var style = document.createElement("style");
  style.textContent =
    "#milo-outline-trigger,#milo-deploy-trigger{position:fixed;z-index:1500;display:flex;align-items:center;gap:6px;width:88px;min-height:42px;padding:0 12px;box-sizing:border-box;" +
    "border:1px solid #7c6ae6;background:#6d5bd0;color:#fff;font:600 13px system-ui;cursor:grab;touch-action:none;user-select:none;" +
    "box-shadow:0 8px 25px #0005;transition:transform .2s ease,background .2s ease,box-shadow .2s ease}" +
    "#milo-outline-trigger[hidden],#milo-deploy-trigger[hidden]{display:none}" +
    "#milo-outline-trigger[data-side=right],#milo-deploy-trigger[data-side=right]{border-right:0;border-radius:10px 0 0 10px}" +
    "#milo-outline-trigger[data-side=left],#milo-deploy-trigger[data-side=left]{border-left:0;border-radius:0 10px 10px 0}" +
    "#milo-outline-trigger span:last-child,#milo-deploy-trigger span:last-child{max-width:64px;overflow:hidden;white-space:nowrap;opacity:1;transition:max-width .2s ease,opacity .15s ease}" +
    "#milo-outline-trigger.is-peeking span:last-child,#milo-deploy-trigger.is-peeking span:last-child{max-width:0;opacity:0}" +
    "#milo-outline-trigger.is-peeking,#milo-deploy-trigger.is-peeking{width:auto;gap:0;padding-left:10px;padding-right:10px}" +
    "#milo-outline-trigger:hover,#milo-outline-trigger:focus-visible,#milo-deploy-trigger:hover,#milo-deploy-trigger:focus-visible{background:#7c6ae6;box-shadow:0 10px 30px #0008}" +
    "#milo-outline-trigger.is-dragging{cursor:grabbing;transition:none}" +
    "#milo-outline-overlay{position:fixed;inset:0;z-index:3000;display:grid;grid-template-rows:52px 1fr;background:#080b14}" +
    "#milo-outline-overlay[hidden]{display:none}" +
    "#milo-outline-overlay header{display:flex;align-items:center;gap:14px;padding:0 14px;color:#eef2ff;background:#111827;border-bottom:1px solid #29344d}" +
    "#milo-outline-overlay header span{color:#94a3b8;font:12px system-ui}" +
    "#milo-outline-overlay header button{margin-left:auto;min-height:36px;padding:0 14px;border:1px solid #46536d;border-radius:8px;background:#1c263a;color:#fff;cursor:pointer}" +
    "#milo-outline-overlay iframe{width:100%;height:100%;border:0;background:#080b14}" +
    "#milo-deploy-trigger{cursor:pointer}" +
    "#milo-deploy-overlay{position:fixed;inset:0;z-index:3500;display:flex;align-items:center;justify-content:center;padding:20px;background:#050914d9;font:14px system-ui;color:#e8edf7}" +
    "#milo-deploy-overlay[hidden]{display:none}.milo-deploy-card{width:min(620px,100%);border:1px solid #34435b;border-radius:14px;background:#111827;box-shadow:0 24px 80px #000a;overflow:hidden}" +
    ".milo-deploy-card header{display:flex;align-items:center;padding:16px 18px;border-bottom:1px solid #27344a}.milo-deploy-card header div{display:flex;flex-direction:column;gap:3px}.milo-deploy-card header strong{font-size:17px}.milo-deploy-card header span{font-size:12px;color:#94a3b8}.milo-deploy-card header button{margin-left:auto;border:0;background:transparent;color:#b8c2d5;font-size:26px;cursor:pointer}" +
    ".milo-deploy-card main{display:grid;gap:11px;padding:18px}.milo-deploy-card label{font-weight:600}.milo-deploy-card input[type=text],.milo-deploy-card input:not([type]),.milo-deploy-card select{height:42px;padding:0 12px;border:1px solid #42516b;border-radius:8px;background:#0b1220;color:#fff;font:15px system-ui;outline:none}.milo-deploy-card input:focus,.milo-deploy-card select:focus{border-color:#6d8cff}.milo-deploy-secondary-label{font-size:12px;color:#94a3b8}" +
    ".milo-deploy-section{display:grid;gap:8px}.milo-deploy-section[hidden]{display:none}.milo-deploy-modes{display:flex;gap:16px;flex-wrap:wrap}.milo-deploy-modes label,.milo-deploy-consents label{display:flex;align-items:flex-start;gap:8px;font-weight:500}.milo-deploy-modes input,.milo-deploy-consents input{width:auto;height:auto;margin-top:3px}.milo-deploy-consents{display:grid;gap:8px;padding:10px;border:1px solid #334155;border-radius:8px;background:#0b1220}.milo-deploy-consents a{color:#8db4ff}" +
    ".milo-deploy-summary,.milo-deploy-auth,.milo-deploy-status{line-height:1.5;color:#b7c3d7}.milo-deploy-auth[data-kind=success],.milo-deploy-status[data-kind=success]{color:#73d69c}.milo-deploy-auth[data-kind=error],.milo-deploy-status[data-kind=error]{color:#ff8f8f}" +
    ".milo-deploy-browser{display:flex;align-items:center;gap:10px}.milo-deploy-browser .milo-deploy-auth{flex:1}.milo-deploy-browser button{min-height:34px;padding:0 10px;border:1px solid #46536d;border-radius:7px;background:#1c263a;color:#fff;cursor:pointer}.milo-deploy-browser button:disabled{opacity:.5;cursor:not-allowed}" +
    ".milo-deploy-progress{height:9px;border-radius:999px;background:#263247;overflow:hidden}.milo-deploy-progress span{display:block;height:100%;width:0;background:#4eb477;transition:width .25s ease}" +
    ".milo-deploy-card footer{display:flex;align-items:center;gap:10px;padding:14px 18px;border-top:1px solid #27344a}.milo-deploy-card footer a{color:#8db4ff;text-decoration:none;margin-right:auto}.milo-deploy-card footer button{min-width:110px;height:40px;border:0;border-radius:8px;background:#267a4d;color:#fff;font-weight:700;cursor:pointer}.milo-deploy-card footer .milo-deploy-stop{background:#7f3540}.milo-deploy-card footer button[hidden]{display:none}.milo-deploy-card footer button:disabled{opacity:.45;cursor:not-allowed}";
  document.head.appendChild(style);

  sync();
  setInterval(sync, 300);
  window.addEventListener("popstate", sync);
  window.addEventListener("pointermove", handlePointerMove);
  window.addEventListener("pointerup", finishDrag);
  window.addEventListener("pointercancel", finishDrag);
  window.addEventListener("resize", function () {
    if (!trigger) return;
    applyTriggerPosition({
      side: trigger.dataset.side,
      top: parseFloat(trigger.style.top)
    });
  });
})();
