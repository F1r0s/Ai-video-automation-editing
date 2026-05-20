(function () {
  const storageKey = "ai-video-backend-url";
  const backendUrlInput = document.getElementById("backendUrl");
  const statusText = document.getElementById("statusText");
  const responseText = document.getElementById("responseText");
  const videoUrlText = document.getElementById("videoUrlText");

  const fields = [
    "game",
    "url",
    "max",
    "caption_color",
    "caption_pos",
    "landing_link_color",
    "link_font",
    "elevenlabs_key",
    "elevenlabs_voice_id",
    "overlays",
    "layout",
  ];

  function setStatus(message) {
    statusText.textContent = message;
  }

  function setResponse(message) {
    responseText.textContent = message;
  }

  function setVideoUrl(message) {
    videoUrlText.textContent = message;
  }

  function getBackendUrl() {
    return backendUrlInput.value.trim().replace(/\/+$/, "");
  }

  function saveSettings() {
    localStorage.setItem(storageKey, getBackendUrl());
    setStatus("Settings saved");
    setResponse("Backend URL stored locally in this browser.");
  }

  function loadSettings() {
    const stored = localStorage.getItem(storageKey);
    if (stored) {
      backendUrlInput.value = stored;
    }
    if (!backendUrlInput.value.trim()) {
      backendUrlInput.value = "https://your-oracle-host:5000";
    }
  }

  async function checkStatus() {
    const backendUrl = getBackendUrl();
    if (!backendUrl) {
      setStatus("Missing backend URL");
      setResponse("Set the Oracle backend URL first.");
      return;
    }

    setStatus("Checking status...");
    setResponse("Sending GET /api/status");
    try {
      const response = await fetch(`${backendUrl}/api/status`, { method: "GET" });
      const data = await response.json();
      setStatus(response.ok ? "Backend reachable" : `HTTP ${response.status}`);
      setResponse(JSON.stringify(data));
    } catch (error) {
      setStatus("Status check failed");
      setResponse(String(error));
    }
  }

  async function generate() {
    const backendUrl = getBackendUrl();
    const screenshot = document.getElementById("screenshot").files[0];

    if (!backendUrl) {
      setStatus("Missing backend URL");
      setResponse("Set the Oracle backend URL first.");
      return;
    }

    if (!screenshot) {
      setStatus("Missing screenshot");
      setResponse("Choose a screenshot file before sending a render job.");
      return;
    }

    const payload = new FormData();
    fields.forEach((id) => payload.append(id, document.getElementById(id).value));
    payload.append("screenshot", screenshot);

    setStatus("Sending render job...");
    setResponse("POST /api/generate");
    setVideoUrl("-");

    try {
      const response = await fetch(`${backendUrl}/api/generate`, {
        method: "POST",
        body: payload,
      });
      const data = await response.json();
      setStatus(response.ok ? "Render request sent" : `HTTP ${response.status}`);
      setResponse(JSON.stringify(data));
      if (data.video_url) {
        setVideoUrl(`${backendUrl}${data.video_url}`);
      }
    } catch (error) {
      setStatus("Render request failed");
      setResponse(String(error));
    }
  }

  document.getElementById("saveSettings").addEventListener("click", saveSettings);
  document.getElementById("checkStatus").addEventListener("click", checkStatus);
  document.getElementById("generate").addEventListener("click", generate);

  loadSettings();
})();