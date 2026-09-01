// Podbase to Kolosus Template Mapping Rules
const KOLOSUS_MAPPING = [
  // ==================== MACBOOK MAPPINGS ====================
  // 1. Macbook Neo 13 [A3404]
  { match: /Macbook\s+Neo\s+13.*A3404/i, template: 'Macbook | 13” Neo A3404' },
  { match: /A3404/i, template: 'Macbook | 13” Neo A3404' },

  // 2. MacBook Air 13 [A1932/A2179/A2337]
  { match: /MacBook\s+Air\s+13.*(?:A1932|A2179|A2337)/i, template: 'Macbook 13" Retina | A1932 / A2179 / A2337' },
  { match: /(?:A1932.*A2179|A2179.*A2337|A1932\/A2179\/A2337)/i, template: 'Macbook 13" Retina | A1932 / A2179 / A2337' },

  // 3. MacBook Air 11 [A1370/A1465]
  { match: /MacBook\s+Air\s+11.*(?:A1370|A1465)/i, template: 'Macbook Air 11" | A1370 / A1465' },
  { match: /A1370.*A1465|A1370\/A1465/i, template: 'Macbook Air 11" | A1370 / A1465' },

  // 4. MacBook Air 13 [A1466/A1369]
  { match: /MacBook\s+Air\s+13.*(?:A1466|A1369)/i, template: "Macbook Air 13'' | A1466 / A1369" },
  { match: /A1466.*A1369|A1466\/A1369/i, template: "Macbook Air 13'' | A1466 / A1369" },

  // 5. MacBook Air 15 [A2941/A3114/A3241/A3448]
  { match: /MacBook\s+Air\s+15.*(?:A2941|A3114|A3241|A3448)/i, template: 'Macbook Air 15 | A2941 / M4 / A3448' },
  { match: /Air\s+15.*(?:A2941|A3114|A3241|A3448)/i, template: 'Macbook Air 15 | A2941 / M4 / A3448' },

  // 6. MacBook Air 13 / 13.6 [A3449, A2681, A3113, A3240]
  { match: /MacBook\s+Air\s+13(?:\.6)?.*(?:A3449|A2681|A3113|A3240)/i, template: 'MacBook Air M2 | A2681 / M4' },
  { match: /Air\s+13\.6.*(?:A2681|A3113|A3240|M3\/M4)/i, template: 'MacBook Air M2 | A2681 / M4' },

  // 7. MacBook Pro 14 / 14.2 [A2442, A2779, A2918, A2992, A3112, A3185, A3401, A3426, A3427, A3434]
  { match: /MacBook\s+Pro\s+14(?:\.2)?.*(?:A2442|A2779|A2918|A2992|A3112|A3185|A3401|A3426|A3427|A3434)/i, template: 'MacBook Pro 14.2" | A2442 A3112 A3426 A3427' },
  { match: /Pro\s+14(?:\.2)?.*(?:A2442|A2779|A2918|A2992|A3112|A3185|A3401|A3426|A3427|A3434)/i, template: 'MacBook Pro 14.2" | A2442 A3112 A3426 A3427' },

  // 8. MacBook Pro 15 [A1398]
  { match: /MacBook\s+Pro\s+15.*A1398/i, template: 'Macbook Pro 15" | A1398' },
  { match: /Pro\s+15.*A1398/i, template: 'Macbook Pro 15" | A1398' },

  // 9. MacBook Pro 16 [A2141]
  { match: /MacBook\s+Pro\s+16.*A2141/i, template: 'Macbook Pro 16" | A2141' },
  { match: /Pro\s+16.*A2141/i, template: 'Macbook Pro 16" | A2141' },

  // 10. MacBook Pro 16 [A2485/A2780/A2991/A3403/A3186/A3428/A3429]
  { match: /MacBook\s+Pro\s+16.*(?:A2485|A2780|A2991|A3403|A3186|A3428|A3429)/i, template: "MacBook Pro 16'' | A2485 A3403 A3428 A3429" },
  { match: /Pro\s+16.*(?:A2485|A2780|A2991|A3403|A3186|A3428|A3429)/i, template: "MacBook Pro 16'' | A2485 A3403 A3428 A3429" },

  // 11. MacBook Pro 13 TouchBar [A2338] (M4)
  { match: /MacBook\s+Pro\s+13(?:\.3)?.*A2338/i, template: 'Macbook Pro TouchBar 13" | A1706 / A1708 / A1989 / A2159 / A2289 / A2338 / A2251/A2338-M4' },

  // 12. MacBook Pro 13 TouchBar [A2289/A2251] (M3)
  { match: /MacBook\s+Pro\s+13.*(?:A2289|A2251)/i, template: 'Macbook Pro TouchBar 13" | A1706 / A1708 / A1989 / A2159 / A2289 / A2338 / A2251/A2338-M3' },

  // 13. MacBook Pro 13 TouchBar [A1706/A1708] & [A1989/A2159] (M2)
  { match: /MacBook\s+Pro\s+13.*(?:A1706|A1708|A1989|A2159)/i, template: 'Macbook Pro TouchBar 13" | A1706 / A1708 / A1989 / A2159 / A2289 / A2338 / A2251/A2338-M2' },

  // 14. MacBook Pro 15 TouchBar [A1990/A1707]
  { match: /MacBook\s+Pro\s+15.*(?:A1990|A1707)/i, template: 'Macbook Pro TouchBar 15" | A1990 / A1707' },
  { match: /Pro\s+15.*(?:A1990|A1707)/i, template: 'Macbook Pro TouchBar 15" | A1990 / A1707' },

  // ==================== IPAD MAPPINGS ====================
  // 10.9" 2022
  { match: /iPad\s+11\s+A16\s+\(11th\s+Gen\)/i, template: 'iPad | 10.9" 2022' },
  { match: /iPad\s+10\.9\s+\(10th\s+Gen\)/i, template: 'iPad | 10.9" 2022' },
  
  // 7 10.2 | 8 10.2
  { match: /iPad\s+10\.2\s+\(9th\/8th\/7th\s+Gen\)/i, template: 'iPad | 7 10.2 | iPad 8 10.2' },
  
  // Air 13" 2024
  { match: /iPad\s+Air\s+13\s+\(8th\s+Gen\)/i, template: 'iPad | Air 13" 2024' },
  { match: /iPad\s+Air\s+13\s+\(7th\/6th\s+Gen\)/i, template: 'iPad | Air 13" 2024' },
  
  // Air 4 10.9" 2020
  { match: /iPad\s+Air\s+11\s+\(7th\/6th\s+Gen\)/i, template: 'iPad | Air 4 10.9" 2020' },
  { match: /iPad\s+Air\s+11\s+\(8th\s+Gen\)/i, template: 'iPad | Air 4 10.9" 2020' },
  { match: /iPad\s+Air\s+11\s+\(5th\s+Gen\)/i, template: 'iPad | Air 4 10.9" 2020' },
  { match: /iPad\s+Air\s+10\.9\s+\(5th\/4th\s+Gen\)/i, template: 'iPad | Air 4 10.9" 2020' },
  
  // Pro 11
  { match: /iPad\s+Pro\s+11\s+\(4th\/3rd\/2nd\/1st\s+Gen\)/i, template: 'iPad | Pro 11' },
  
  // Pro 11" 2024
  { match: /iPad\s+Pro\s+11\s+\(8th\s+Gen\)/i, template: 'iPad | Pro 11" 2024' },
  { match: /iPad\s+Pro\s+11\s+\(6th\s+Gen\)/i, template: 'iPad | Pro 11" 2024' },
  
  // Pro 12.9
  { match: /iPad\s+Pro\s+12\.9\s+\(6th\/5th\/4th\/3rd\s+Gen\)/i, template: 'iPad | Pro 12.9' },
  { match: /iPad\s+Pro\s+12\.9/i, template: 'iPad | Pro 12.9' },
  { match: /ipad-pro-129|ipad_pro_129/i, template: 'iPad | Pro 12.9' },
  
  // Pro 13" 2024
  { match: /iPad\s+Pro\s+13\s+\(8th\s+Gen\)/i, template: 'iPad | Pro 13" 2024' },
  { match: /iPad\s+Pro\s+13\s+\(7th\s+Gen\)/i, template: 'iPad | Pro 13" 2024' },

  // ==================== SLEEVES ====================
  { match: /Laptop\s+Sleeve\s+16/i, template: 'Sleeve 16"' },
  { match: /Laptop\s+Sleeve\s+14/i, template: 'Sleeve 14"' },
  { match: /Laptop\s+Sleeve\s+13/i, template: 'Sleeve 13"' }
];

function getKolosusTemplate(rawName) {
  if (!rawName) return null;
  for (const rule of KOLOSUS_MAPPING) {
    if (rule.match.test(rawName)) {
      return rule.template;
    }
  }
  return null;
}

// Inject CSS styles for badges, buttons and floating controls
function injectStyles() {
  if (document.getElementById('kolosus-ext-styles')) return;
  const style = document.createElement('style');
  style.id = 'kolosus-ext-styles';
  style.textContent = `
    .kolosus-badge {
      display: inline-flex;
      align-items: center;
      background: linear-gradient(135deg, #10b981, #059669);
      color: #ffffff !important;
      font-weight: 700 !important;
      font-size: 11px !important;
      padding: 2px 7px !important;
      border-radius: 4px !important;
      margin-right: 6px !important;
      box-shadow: 0 1px 2px rgba(0,0,0,0.15);
      letter-spacing: 0.2px;
      vertical-align: middle;
    }
    .kolosus-original-sub {
      display: block;
      font-size: 10px !important;
      color: #64748b !important;
      font-weight: normal !important;
      margin-top: 2px;
    }
    .kolosus-toggle-btn {
      background-color: #10b981;
      color: white;
      border: none;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 4px;
      cursor: pointer;
      margin-left: 8px;
      transition: all 0.2s;
    }
    .kolosus-toggle-btn:hover {
      background-color: #059669;
    }
    .kolosus-grouped-container {
      margin-top: 6px;
      font-family: inherit;
    }
    .kolosus-group-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      margin-bottom: 6px;
      padding: 8px 10px;
      transition: background 0.15s;
    }
    .kolosus-group-card:hover {
      background: #f1f5f9;
      border-color: #cbd5e1;
    }
    .kolosus-group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      font-size: 12px;
    }
    .kolosus-pids-badge {
      background: #10b981;
      color: white;
      font-weight: bold;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
    }
    .kolosus-group-items {
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px dashed #cbd5e1;
      font-size: 11px;
      color: #475569;
    }
  `;
  document.head.appendChild(style);
}

// Enhance product tables across all stations (UV, MacBook, etc.)
function enhanceProductsTable() {
  injectStyles();

  const tables = document.querySelectorAll("table");
  if (!tables || tables.length === 0) return;

  tables.forEach(table => {
    const rows = table.querySelectorAll("tbody tr, tr");
    rows.forEach(row => {
      const cells = row.querySelectorAll("td");
      if (cells.length >= 1) {
        cells.forEach(cell => {
          if (cell.querySelector(".kolosus-badge") || cell.querySelector("button")) return;

          const text = cell.innerText.trim();
          const template = getKolosusTemplate(text);
          if (template) {
            const originalText = cell.innerText;
            cell.innerHTML = `
              <span class="kolosus-badge">${template}</span>
              <span class="kolosus-original-sub">${originalText}</span>
            `;
          }
        });
      }
    });

    // Grouping Toggle Button Injection for any station card
    const cardParent = table.closest(".card, [class*='card'], .p-card, .table-responsive") || table.parentElement;
    if (cardParent && !cardParent.querySelector(".kolosus-toggle-btn")) {
      const headerTitle = cardParent.querySelector("h5, h4, h6, .card-title, [class*='title'], [class*='header']");
      if (headerTitle) {
        const toggleBtn = document.createElement("button");
        toggleBtn.className = "kolosus-toggle-btn";
        toggleBtn.innerHTML = "🔄 Grupuoti pagal Šabloną";
        toggleBtn.addEventListener("click", (e) => {
          e.preventDefault();
          toggleGroupedView(cardParent, table, toggleBtn);
        });
        headerTitle.appendChild(toggleBtn);
      }
    }
  });
}

function toggleGroupedView(cardParent, targetTable, toggleBtn) {
  let groupedView = cardParent.querySelector("#kolosus-grouped-view");
  const isHidden = (targetTable.style.display === "none");

  if (!isHidden) {
    targetTable.style.display = "none";
    if (!groupedView) {
      groupedView = document.createElement("div");
      groupedView.id = "kolosus-grouped-view";
      groupedView.className = "kolosus-grouped-container";
      targetTable.parentNode.insertBefore(groupedView, targetTable.nextSibling);
    }
    groupedView.style.display = "block";
    renderGroupedView(groupedView, targetTable);
    if (toggleBtn) toggleBtn.innerHTML = "📋 Rodyti lentelę";
  } else {
    targetTable.style.display = "";
    if (groupedView) groupedView.style.display = "none";
    if (toggleBtn) toggleBtn.innerHTML = "🔄 Grupuoti pagal Šabloną";
  }
}

function renderGroupedView(container, targetTable) {
  const rows = targetTable.querySelectorAll("tbody tr, tr");
  const groupedData = {};

  rows.forEach(row => {
    const cells = row.querySelectorAll("td");
    if (cells.length >= 2) {
      let id = "";
      let pids = 1;
      let originalName = "";

      if (cells.length >= 3) {
        id = cells[0].innerText.trim();
        pids = parseInt(cells[1].innerText.trim(), 10) || 1;
        originalName = cells[2].innerText.trim();
      } else {
        originalName = cells[0].innerText.trim();
        pids = parseInt(cells[1].innerText.trim(), 10) || 1;
      }
      
      const template = getKolosusTemplate(originalName) || "Kiti / Neatpažinti";

      if (!groupedData[template]) {
        groupedData[template] = {
          template: template,
          totalPids: 0,
          items: []
        };
      }

      groupedData[template].totalPids += pids;
      groupedData[template].items.push({ id, pids, originalName });
    }
  });

  container.innerHTML = "";
  const groupKeys = Object.keys(groupedData);

  if (groupKeys.length === 0) {
    container.innerHTML = "<p style='font-size: 11px; color: #64748b;'>Nėra duomenų.</p>";
    return;
  }

  groupKeys.forEach(key => {
    const group = groupedData[key];
    const card = document.createElement("div");
    card.className = "kolosus-group-card";

    let itemsHtml = "";
    group.items.forEach(it => {
      itemsHtml += `<div style="display: flex; justify-content: space-between; padding: 2px 0;">
        <span>• ${it.originalName} ${it.id ? '(ID: ' + it.id + ')' : ''}</span>
        <span style="font-weight: 600;">${it.pids} vnt.</span>
      </div>`;
    });

    card.innerHTML = `
      <div class="kolosus-group-header">
        <span style="font-weight: bold; color: #0f172a;">${group.template}</span>
        <span class="kolosus-pids-badge">${group.totalPids} vnt.</span>
      </div>
      <div class="kolosus-group-items">
        ${itemsHtml}
      </div>
    `;

    container.appendChild(card);
  });
}

// ----------------- PRECISE PID & DESIGN EXTRACTION -----------------
function extractPIDDirect(container) {
  if (!container) return null;

  // 1. Check dedicated .print-detail-id class (Exact match from DevTools)
  const pidElem = container.querySelector(".print-detail-id, [class*='print-detail-id'], [class*='detail-id']");
  if (pidElem) {
    const text = (pidElem.innerText || pidElem.textContent || "").trim();
    const m = text.match(/PID[-:\s#]*(\d+)/i) || text.match(/^(\d+)$/);
    if (m) return m[1];
  }

  // 2. Check dataset attributes
  if (container.dataset) {
    if (container.dataset.pid) return container.dataset.pid;
    if (container.dataset.printId) return container.dataset.printId;
    if (container.dataset.itemId && /^\d{3,8}$/.test(container.dataset.itemId)) return container.dataset.itemId;
  }

  // 3. Search strictly for 'PID 8528' or 'PID-8528' or 'PID: 8528' in text
  const txt = container.innerText || container.textContent || "";
  const strictPidMatch = txt.match(/PID[-:\s#]*(\d{3,8})/i);
  if (strictPidMatch) return strictPidMatch[1];

  return null;
}

function getValidDesignImages() {
  const modal = document.querySelector(".modal, .dialog, [role='dialog'], .p-dialog, [class*='modal'], [class*='dialog'], .frame-plan-body");
  const searchRoot = modal || document.body;

  const validDesigns = [];
  const seenPIDs = new Set();
  const fullText = searchRoot.innerText || document.body.innerText || "";
  let bidNumber = null;
  const bidMatch = fullText.match(/BID-(\d+)/i) || document.location.href.match(/bid[-_](\d+)/i);
  if (bidMatch) {
    bidNumber = bidMatch[1];
  }

  // 1. Leaf Item Cards: select ONLY inner item containers (.print-detail-item)
  const cardElements = Array.from(searchRoot.querySelectorAll(".print-detail-item"));
  const targetCards = cardElements.length > 0 ? cardElements : Array.from(searchRoot.querySelectorAll(".print-detail-card"));
  
  if (targetCards.length > 0) {
    targetCards.forEach((card) => {
      const pidFound = extractPIDDirect(card);
      const img = card.querySelector("img");
      const src = img ? (img.src || "") : "";

      const key = pidFound ? `pid_${pidFound}` : (src ? `src_${src}` : `idx_${validDesigns.length}`);
      if (seenPIDs.has(key)) {
        return; // Avoid processing parent or duplicated elements
      }
      seenPIDs.add(key);

      if (pidFound || src) {
        const designName = pidFound ? `PID-${pidFound}` : (bidNumber ? `BID-${bidNumber}_${validDesigns.length + 1}` : `Dizainas_${validDesigns.length + 1}`);
        validDesigns.push({
          name: designName,
          url: src,
          pid: pidFound || null
        });
      }
    });
  }

  // 2. Fallback: Image-by-image extraction if no cards found
  if (validDesigns.length === 0) {
    const imgs = Array.from(searchRoot.querySelectorAll("img"));
    imgs.forEach((img) => {
      const src = img.src || "";
      const alt = (img.alt || "").toLowerCase();
      const cls = (img.className || "").toLowerCase();

      if (src.includes("flag") || src.includes("flags/") || src.includes("logo") || 
          src.includes("avatar") || src.includes("icon") || src.includes("favicon") ||
          alt.includes("flag") || alt.includes("logo") || cls.includes("flag") ||
          src.endsWith(".svg") || (img.width < 50 && img.width > 0 && img.height < 50 && img.height > 0)) {
        return;
      }

      const cardParent = img.closest(".print-detail-item, .print-detail-card, div, [class*='card'], .col, .item, tr, td") || img.parentElement;
      let pidFound = extractPIDDirect(cardParent);

      if (!pidFound && src) {
        const srcPidMatch = src.match(/PID[-:\s#_]*(\d{3,8})/i);
        if (srcPidMatch) pidFound = srcPidMatch[1];
      }

      const key = pidFound ? `pid_${pidFound}` : (src ? `src_${src}` : `idx_${validDesigns.length}`);
      if (seenPIDs.has(key)) return;
      seenPIDs.add(key);

      if (pidFound || src.includes("/photos/") || src.includes("/remote_photos/") || modal) {
        const designName = pidFound ? `PID-${pidFound}` : (bidNumber ? `BID-${bidNumber}_${validDesigns.length + 1}` : `Dizainas_${validDesigns.length + 1}`);
        validDesigns.push({
          name: designName,
          url: src,
          pid: pidFound || null
        });
      }
    });
  }

  return { designs: validDesigns, bidNumber };
}

function collectAndSendDesigns() {
  const modal = document.querySelector(".modal, .dialog, [role='dialog'], .p-dialog, [class*='modal'], [class*='dialog'], .frame-plan-body");
  const contextText = modal ? modal.innerText : document.body.innerText;

  const { designs, bidNumber } = getValidDesignImages();

  if (designs.length === 0) {
    alert("⚠️ Nerasta jokių spaudos dizainų! Pirmiausia atidarykite BID užsakymo langą (paspauskite 'Laukiama' arba BID numerį).");
    return;
  }

  let detectedModel = null;
  for (const rule of KOLOSUS_MAPPING) {
    if (rule.match.test(contextText)) {
      detectedModel = rule.template;
      break;
    }
  }

  console.log("🚀 Siunčiami spaudos dizainai į UV Studio:", { count: designs.length, designs, model: detectedModel, bidNumber });

  chrome.runtime.sendMessage(
    {
      type: "send_designs",
      designs: designs,
      model: detectedModel,
      jobName: bidNumber ? `BID-${bidNumber}` : null,
      bidNumber: bidNumber
    },
    (response) => {
      if (chrome.runtime.lastError) {
        alert("❌ Plėtinio ryšio klaida: " + chrome.runtime.lastError.message + "\nĮsitikinkite, kad paleista programa!");
        console.error("Extension runtime error:", chrome.runtime.lastError);
        return;
      }
      if (response?.ok) {
        alert(`✅ Užsakymas ${bidNumber ? 'BID-' + bidNumber : ''} sėkmingai nusiųstas į UV Studio!\nModelis: ${detectedModel || 'Nenustatytas'}\nTikrų dizainų kiekis: ${designs.length}`);
      } else {
        alert("❌ Klaida siunčiant į programą: " + (response?.error || "Nežinoma klaida"));
      }
    }
  );
}

// ----------------- CLEAN TARGETED BUTTON INJECTION (FOR ALL STATIONS INCL. MACBOOK) -----------------
function injectContainerButtons() {
  injectStyles();

  // 1. In Modal Footer: right next to "Spausdinti BID" button
  const allButtons = Array.from(document.querySelectorAll("button"));
  const printBidBtn = allButtons.find(b => b.innerText && b.innerText.includes("Spausdinti BID"));
  
  if (printBidBtn && printBidBtn.parentElement) {
    if (!printBidBtn.parentElement.querySelector(".kolosus-footer-btn")) {
      const btn = document.createElement("button");
      btn.className = "kolosus-footer-btn";
      btn.innerHTML = "🚀 Kurti konteinerį";
      btn.style.cssText = "background: linear-gradient(135deg, #10b981, #059669); color: white; border: none; padding: 7px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-right: 8px; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.15);";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        collectAndSendDesigns();
      });
      printBidBtn.parentElement.insertBefore(btn, printBidBtn);
    }
  }

  // 2. In Purple Modal Header: right next to "Spausdinti Sample" button
  const printSampleBtn = allButtons.find(b => b.innerText && b.innerText.includes("Spausdinti Sample"));
  if (printSampleBtn && printSampleBtn.parentElement) {
    if (!printSampleBtn.parentElement.querySelector(".kolosus-header-btn")) {
      const btn = document.createElement("button");
      btn.className = "kolosus-header-btn";
      btn.innerHTML = "🚀 Kurti konteinerį";
      btn.style.cssText = "background: #10b981; color: white; border: none; padding: 5px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-right: 8px; font-size: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.15);";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        collectAndSendDesigns();
      });
      printSampleBtn.parentElement.insertBefore(btn, printSampleBtn);
    }
  }
}

// Initial execution
enhanceProductsTable();
injectContainerButtons();

// DOM Observer for dynamic SPA modal openings and page changes across stations
const observer = new MutationObserver(() => {
  enhanceProductsTable();
  injectContainerButtons();
});

observer.observe(document.body, { childList: true, subtree: true });
