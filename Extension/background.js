chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "send_designs") {

    // Gauto serverio URL iš atminties arba naudojame numatytąjį localhost
    chrome.storage.local.get(["serverUrl"], (result) => {
      const serverUrl = result.serverUrl || "http://127.0.0.1:5000";

      fetch(`${serverUrl}/api/add_designs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ designs: msg.designs })
      })
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
        }
        return res.json();
      })
      .then(data => {
        if (data && data.success) {
          sendResponse({ ok: true });
        } else {
          sendResponse({ ok: false, error: `Server response error: ${data?.error || 'Unknown error'} (URL: ${serverUrl})` });
        }
      })
      .catch(err => {
        sendResponse({ ok: false, error: `${err.toString()} (URL: ${serverUrl}/api/add_designs)` });
      });
    });

    return true; // keep channel open for async sendResponse
  }
});
