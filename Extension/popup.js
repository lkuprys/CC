document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("server-url");
  const saveBtn = document.getElementById("save-btn");
  const statusMsg = document.getElementById("status-msg");

  // Load saved URL or default
  chrome.storage.local.get(["serverUrl"], (result) => {
    urlInput.value = result.serverUrl || "http://127.0.0.1:5000";
  });

  saveBtn.addEventListener("click", () => {
    let rawUrl = urlInput.value.trim();
    if (!rawUrl) {
      rawUrl = "http://127.0.0.1:5000";
    }

    // Ensure it starts with http:// or https://
    if (!/^https?:\/\//i.test(rawUrl)) {
      rawUrl = "http://" + rawUrl;
    }

    // Remove trailing slash
    rawUrl = rawUrl.replace(/\/+$/, "");

    chrome.storage.local.set({ serverUrl: rawUrl }, () => {
      statusMsg.textContent = "Išsaugota sėkmingai!";
      statusMsg.className = "status success";
      urlInput.value = rawUrl;

      setTimeout(() => {
        statusMsg.textContent = "";
        statusMsg.className = "status";
      }, 1500);
    });
  });
});
