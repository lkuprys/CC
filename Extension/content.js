function tryInsertButton() {
  const headers = document.querySelectorAll("h5");
  let targetHeader = null;

  headers.forEach(h => {
    const text = h.innerText || h.textContent;
    if (text.includes("GEN-") && text.includes("BID-")) {
      targetHeader = h;
    }
  });

  if (targetHeader && !targetHeader.querySelector(".my-custom-btn")) {
    const myButton = document.createElement("button");
        myButton.textContent = "Kurti konteinerį";
        myButton.className = "btn btn-primary my-custom-btn";
        myButton.style.marginLeft = "5px";

        // ✅ Your required functionality
        myButton.addEventListener("click", () => {
          const headerText = targetHeader.innerText || targetHeader.textContent || "";
          const isPodbase = headerText.toLowerCase().includes("podbase");
          let bidNumber = null;
          if (isPodbase) {
            const bidMatch = headerText.match(/BID-(\d+)/i);
            if (bidMatch) {
              bidNumber = bidMatch[1];
            }
          }

          const imgs = document.querySelectorAll("img");
          const found = [];
          const colorRegex = /(beige|nude|pink|purple|turquoise)/i;

          if (isPodbase && bidNumber) {
            imgs.forEach(img => {
              const src = img.src || "";
              if (src.includes("/remote_photos/")) {
                found.push({ name: `BID-${bidNumber}`, url: src });
              }
            });
          } else {
            imgs.forEach(img => {
              const src = img.src || "";
              const matches = src.match(/[A-Z]{2}_[0-9]{2}/g);

              if (matches) {
                matches.forEach(m => {
                  let finalName = m;
                  if (m.startsWith("ZO")) {
                    const colorMatch = src.match(colorRegex);
                    if (colorMatch) finalName = `${m}-${colorMatch[1].toLowerCase()}`;
                  }
                  found.push({ name: finalName, url: src });
                });
              }
            });
          }

          const designs = Array.from(found);

    chrome.runtime.sendMessage(
        { type: "send_designs", designs },
        (response) => {
          if (chrome.runtime.lastError) {
              alert("❌ Plėtinio ryšio klaida: " + chrome.runtime.lastError.message);
              console.error("Extension runtime error:", chrome.runtime.lastError);
              return;
          }
          if (response?.ok) {
              alert("✅ Designs sent successfully!");
          } else {
              alert("❌ Error sending designs: " + (response?.error || "Unknown server error"));
              console.error("Server error:", response?.error);
          }
        }
    );
    });


    targetHeader.appendChild(myButton);
    console.log("✅ Custom button added");
  }
}

tryInsertButton();

const observer = new MutationObserver(() => {
  tryInsertButton();
});

observer.observe(document.body, { childList: true, subtree: true });
