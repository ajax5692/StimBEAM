/**
 * PStim Laboratory Dashboard & Mouse-Centric Profile Workstation Client
 */

let ANIMALS_DATA = [];
let currentAnimalId = null;
let activeProfileTab = "overview";
let overviewChartPoints = [];
let overviewTooltipAttached = false;

function getAnimalsData() {
  if (ANIMALS_DATA && ANIMALS_DATA.length > 0) {
    return ANIMALS_DATA;
  }
  const dataEl = document.getElementById("pstim-animals-data");
  if (dataEl && dataEl.textContent) {
    try {
      ANIMALS_DATA = JSON.parse(dataEl.textContent);
    } catch (e) {
      console.error("Error parsing ANIMALS_DATA payload:", e);
      ANIMALS_DATA = [];
    }
  }
  return ANIMALS_DATA;
}

function initTracker() {
  const animals = getAnimalsData();

  // Populate mouse dropdown selector
  const sel = document.getElementById("mouse-select-input");
  if (sel) {
    sel.innerHTML = "";
    if (animals && animals.length > 0) {
      animals.forEach((a) => {
        const opt = document.createElement("option");
        opt.value = a.animal_id;
        opt.textContent = `${a.animal_id} (${a.genotype || "Mouse"}, Cage ${a.cage_id})`;
        sel.appendChild(opt);
      });
      currentAnimalId = animals[0].animal_id;
    } else {
      sel.innerHTML = '<option value="">No animals registered</option>';
    }
  }

  // Check URL query parameters or hash to activate requested view
  const params = new URLSearchParams(window.location.search);
  const viewParam = params.get("view") || window.location.hash.replace("#", "");
  const animalParam = params.get("animal");

  if (animalParam && animals.some((a) => a.animal_id === animalParam)) {
    openMouseProfile(animalParam);
  } else if (viewParam === "profile") {
    switchTrackerView("profile");
  } else {
    switchTrackerView("dashboard");
  }
}

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  const viewParam = params.get("view") || window.location.hash.replace("#", "");
  if (viewParam === "profile" || viewParam === "dashboard") {
    switchTrackerView(viewParam);
  }
});

window.addEventListener("hashchange", () => {
  const hash = window.location.hash.replace("#", "");
  if (hash === "profile" || hash === "dashboard") {
    switchTrackerView(hash);
  }
});

function switchTrackerView(viewName) {
  const dashView = document.getElementById("tracker-dashboard-view");
  const profView = document.getElementById("tracker-profile-view");
  const btnDash = document.getElementById("btn-view-dashboard");
  const btnProf = document.getElementById("btn-view-profile");

  if (viewName === "dashboard") {
    if (dashView) dashView.classList.remove("hidden");
    if (profView) profView.classList.add("hidden");
    if (btnDash) btnDash.classList.add("active");
    if (btnProf) btnProf.classList.remove("active");
  } else {
    if (dashView) dashView.classList.add("hidden");
    if (profView) profView.classList.remove("hidden");
    if (btnDash) btnDash.classList.remove("active");
    if (btnProf) btnProf.classList.add("active");
    if (currentAnimalId) {
      renderSelectedMouseProfile(currentAnimalId);
    }
  }
}

function openMouseProfile(animalId) {
  switchTrackerView("profile");
  const sel = document.getElementById("mouse-select-input");
  if (sel) {
    sel.value = animalId;
  }
  renderSelectedMouseProfile(animalId);
}

function onMouseSelectChange(animalId) {
  renderSelectedMouseProfile(animalId);
}

function renderSelectedMouseProfile(animalId) {
  currentAnimalId = animalId;
  const animals = getAnimalsData();
  const a = animals.find((x) => x.animal_id === animalId);
  if (!a) return;

  // Demographics Banner
  const dispId = document.getElementById("disp-animal-id");
  if (dispId) dispId.textContent = a.animal_id;

  const dispMeta = document.getElementById("disp-animal-meta");
  if (dispMeta) {
    dispMeta.textContent = `${a.genotype} • ${a.sex} • Age: ${a.age_in_days} days • Cage: ${a.cage_id} • Project: ${a.project_id} • Owner: ${a.owner}`;
  }

  const stagePill = document.getElementById("disp-pipeline-stage");
  if (stagePill) {
    stagePill.textContent = a.pipeline_stage;
    stagePill.className = `pstim-stage-pill stage-${a.pipeline_stage.toLowerCase().replace(/\\s+/g, "-")}`;
  }

  // Admin direct edit link
  const linkAdmin = document.getElementById("link-admin-edit");
  if (linkAdmin) {
    linkAdmin.href = `/admin/animals_metadata/animal/${a.id}/change/`;
  }

  // Quick Metrics
  const baseEl = document.getElementById("metric-baseline");
  if (baseEl)
    baseEl.textContent = a.baseline_weight ? `${a.baseline_weight} g` : "—";

  const lateEl = document.getElementById("metric-latest-wt");
  if (lateEl)
    lateEl.textContent = a.latest_weight ? `${a.latest_weight} g` : "—";

  const pctEl = document.getElementById("metric-pct");
  if (pctEl) {
    if (a.latest_pct != null) {
      const cls =
        a.latest_pct >= 85 ? "good" : a.latest_pct >= 80 ? "warn" : "bad";
      pctEl.innerHTML = `<span class="pstim-pill ${cls}">${a.latest_pct}%</span>`;
    } else {
      pctEl.innerHTML = '<span class="pstim-muted">—</span>';
    }
  }

  const waterEl = document.getElementById("metric-water");
  if (waterEl) {
    waterEl.innerHTML = (a.restriction_day_str || "—").replace(" (", "<br>(");
  }

  // Render active sub-tab
  renderSubTabContent(a);
}

function switchProfileTab(tabName) {
  activeProfileTab = tabName;
  document.querySelectorAll(".pstim-subnav-btn").forEach((btn) => {
    btn.classList.toggle(
      "active",
      btn.textContent.toLowerCase().includes(tabName),
    );
  });

  document
    .querySelectorAll(".pstim-subtab-panel")
    .forEach((p) => p.classList.add("hidden"));
  const target = document.getElementById(`subtab-${tabName}`);
  if (target) {
    target.classList.remove("hidden");
  }

  const animals = getAnimalsData();
  const a = animals.find((x) => x.animal_id === currentAnimalId);
  if (a) {
    renderSubTabContent(a);
  }
}

function renderSubTabContent(a) {
  // 1. Overview Canvas Chart
  if (activeProfileTab === "overview") {
    drawWeightCanvas("canvas-overview-weight", a);
  }

  // 2. Vision Checks
  if (activeProfileTab === "vision") {
    const tbody = document.getElementById("tbody-vision");
    if (tbody) {
      if (a.vision && a.vision.length > 0) {
        tbody.innerHTML = a.vision
          .map((v) => {
            const isPass =
              v.result.toLowerCase().includes("pass") || v.result === "P";
            const pill = `<span class="pstim-pill ${isPass ? "good" : "bad"}">${v.result}</span>`;

            const pathHtml = v.data_path
              ? `
            <div style="display: grid; grid-template-columns: max-content 1fr; column-gap: 6px; align-items: center;">
              <button type="button" class="pstim-copy-button" data-copy-text="${v.data_path}" title="Copy vision data path" aria-label="Copy vision data path">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="8" y="8" width="12" height="12" rx="2"></rect>
                  <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
                </svg>
              </button>
              <code class="pstim-code" style="overflow-wrap: anywhere;">${v.data_path}</code>
            </div>
          `
              : '<span class="pstim-muted">—</span>';

            return `<tr>
            <td><strong>${v.type}</strong></td>
            <td>${pill}</td>
            <td>${pathHtml}</td>
          </tr>`;
          })
          .join("");
      } else {
        tbody.innerHTML =
          '<tr><td colspan="3" class="pstim-empty-cell">No vision checks recorded.</td></tr>';
      }
    }
  }

  // 3. Virus Injections
  if (activeProfileTab === "virus") {
    const box = document.getElementById("container-virus-records");
    if (box) {
      if (a.viruses && a.viruses.length > 0) {
        box.innerHTML = a.viruses
          .map((v) => {
            const expressionHtml = v.expression
              ? `
            <div class="pstim-expression-note" style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
              <strong>Expression:</strong>
              <button type="button" class="pstim-copy-button" data-copy-text="${v.expression}" title="Copy MESC file path" aria-label="Copy MESC file path">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="8" y="8" width="12" height="12" rx="2"></rect>
                  <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
                </svg>
              </button>
              <code class="pstim-code" style="overflow-wrap: anywhere;">${v.expression}</code>
            </div>
          `
              : "";

            return `
            <div class="pstim-record-card">
              <div class="pstim-record-header">
                <div>
                  <strong>Injection Date: ${v.date}</strong> <span class="pstim-muted">(${v.person})</span>
                </div>
              </div>
              <div class="pstim-record-body">
                <div>
                  <strong>Surgery Date:</strong> ${v.surgery_date} (${v.surgery_person})
                </div>
                <div style="margin-top: 8px;">
                  <strong>Constructs & Volumes:</strong>
                </div>
                <ul class="pstim-record-list">
                  ${v.injections.map((i) => `<li>${i}</li>`).join("") || "<li>No viral constructs specified</li>"}
                </ul>
                ${expressionHtml}
                ${v.notes ? `<div class="pstim-notes-note" style="margin-top: 6px;"><strong>Notes:</strong> ${v.notes}</div>` : ""}
              </div>
            </div>
          `;
          })
          .join("");
      } else {
        box.innerHTML =
          '<div class="pstim-empty-state">No viral injection records found for this animal.</div>';
      }
    }
  }

  // 4. Weights Table
  if (activeProfileTab === "weights") {
    const tbody = document.getElementById("tbody-weights");
    if (tbody) {
      if (a.weights && a.weights.length > 0) {
        tbody.innerHTML = a.weights
          .map((w) => {
            const cls = w.pct
              ? w.pct >= 85
                ? "good"
                : w.pct >= 80
                  ? "warn"
                  : "bad"
              : "";
            const pill = w.pct
              ? `<span class="pstim-pill ${cls}">${w.pct}%</span>`
              : "—";
            return `<tr>
            <td><strong>${w.date}</strong></td>
            <td>${w.weight_g} g</td>
            <td>${pill}</td>
            <td class="pstim-muted">${w.notes || "—"}</td>
          </tr>`;
          })
          .join("");
      } else {
        tbody.innerHTML =
          '<tr><td colspan="4" class="pstim-empty-cell">No body weight records logged.</td></tr>';
      }
    }
  }

  // 5. Training Sessions
  if (activeProfileTab === "training") {
    const box = document.getElementById("container-training-records");
    if (box) {
      if (a.training_sessions && a.training_sessions.length > 0) {
        box.innerHTML = a.training_sessions
          .map((ts) => {
            const bpodPathHtml = ts.bpod_file
              ? `
            <div style="display: inline-flex; align-items: center; gap: 8px; margin-left: 6px;">
              <button type="button" class="pstim-copy-button" data-copy-text="${ts.bpod_file}" title="Copy BPod file path" aria-label="Copy BPod file path">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="8" y="8" width="12" height="12" rx="2"></rect>
                  <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
                </svg>
              </button>
              <code class="pstim-code" style="overflow-wrap: anywhere;">${ts.bpod_file}</code>
            </div>
          `
              : '<span class="pstim-muted" style="margin-left: 6px;">—</span>';

            const isCompleted =
              (ts.status || "").toLowerCase().includes("complete") ||
              ts.status === "SUCCESS";
            const isFailed =
              (ts.status || "").toLowerCase().includes("fail") ||
              (ts.status || "").toLowerCase().includes("error");
            const statusClass = isCompleted
              ? "good"
              : isFailed
                ? "bad"
                : "warn";
            const statusPill = `<span class="pstim-pill ${statusClass}">${ts.status || "—"}</span>`;

            return `
            <div class="pstim-record-card">
              <div class="pstim-record-header">
                <strong>Training Date: ${ts.date}</strong>
              </div>
              <div class="pstim-record-body">
                <div>
                  <strong>Unit Range:</strong> ${ts.units || "All units"}
                </div>
                <div style="display: flex; align-items: center; flex-wrap: wrap; margin-top: 8px;">
                  <strong>BPod File:</strong>
                  ${bpodPathHtml}
                </div>
                <div style="margin-top: 8px;">
                  <strong>Training Data Analysis Status:</strong> ${statusPill}
                </div>
                ${ts.notes ? `<div class="pstim-notes-note" style="margin-top: 8px;"><strong>Notes:</strong> ${ts.notes}</div>` : ""}
              </div>
            </div>
          `;
          })
          .join("");
      } else {
        box.innerHTML =
          '<div class="pstim-empty-state">No behavior training sessions logged for this animal.</div>';
      }
    }
  }

  // 6. Imaging & Analysis
  if (activeProfileTab === "imaging") {
    const box = document.getElementById("container-imaging-records");
    if (box) {
      if (a.imaging && a.imaging.length > 0) {
        box.innerHTML = a.imaging
          .map((im) => {
            const mescPathHtml = im.mesc_file
              ? `
            <div style="display: inline-flex; align-items: center; gap: 8px; margin-left: 6px;">
              <button type="button" class="pstim-copy-button" data-copy-text="${im.mesc_file}" title="Copy MESC file path" aria-label="Copy MESC file path">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="8" y="8" width="12" height="12" rx="2"></rect>
                  <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
                </svg>
              </button>
              <code class="pstim-code" style="overflow-wrap: anywhere;">${im.mesc_file}</code>
            </div>
          `
              : '<span class="pstim-muted" style="margin-left: 6px;">—</span>';

            return `
            <div class="pstim-record-card">
              <div class="pstim-record-header">
                <strong>Acquisition: ${im.date} — Region: ${im.region}</strong>
              </div>
              <div class="pstim-record-body">
                <div>
                  <strong>Units:</strong> ${im.units || "All"}</span>
                </div>
                <div style="display: flex; align-items: center; flex-wrap: wrap; margin-top: 8px;">
                  <strong>MESC File:</strong>
                  ${mescPathHtml}
                </div>
                <div style="margin-top: 8px;">
                  <strong>Analysis Status:</strong> 
                  <span class="pstim-pill ${im.analysis_performed === "Yes" ? "good" : "warn"}">Performed: ${im.analysis_performed}</span>
                  <span class="pstim-pill ${im.need_for_analysis === "Yes" ? "accent" : "muted"}">Required: ${im.need_for_analysis}</span>
                </div>
                ${
                  im.runs && im.runs.length > 0
                    ? `
                  <div style="margin-top: 10px;">
                    <strong>Suite2p Analysis Runs:</strong>
                    <ul class="pstim-record-list">
                      ${im.runs.map((r) => `<li>Run #${r.id} — Status: <strong>${r.status}</strong> (${r.frame_rate} Hz, Completed: ${r.completed_at})</li>`).join("")}
                    </ul>
                  </div>
                `
                    : ""
                }
              </div>
            </div>
          `;
          })
          .join("");
      } else {
        box.innerHTML =
          '<div class="pstim-empty-state">No 2-photon imaging sessions logged for this animal.</div>';
      }
    }
  }

  // 7. Timeline
  if (activeProfileTab === "timeline") {
    const box = document.getElementById("container-animal-timeline");
    if (box) {
      if (a.timeline && a.timeline.length > 0) {
        box.innerHTML = a.timeline
          .map(
            (e) => `
          <div class="pstim-timeline-item">
            <div class="pstim-timeline-dot ${e.type}"></div>
            <div class="pstim-timeline-content">
              <div class="pstim-timeline-header">
                <strong>${e.title}</strong>
                <span class="pstim-timeline-time">${e.date}</span>
              </div>
              <div class="pstim-timeline-msg">${e.desc}</div>
            </div>
          </div>
        `,
          )
          .join("");
      } else {
        box.innerHTML =
          '<div class="pstim-empty-state">No historical events recorded for this mouse.</div>';
      }
    }
  }
}

// Pure HTML5 Canvas Weight Chart (Body Weight Progression)
function drawWeightCanvas(canvasId, a) {
  const canvas = document.getElementById(canvasId);
  const container = document.getElementById("overview-weight-canvas-container");
  const emptyMsg = document.getElementById("overview-weight-empty");
  const tooltip = document.getElementById("overview-weight-tooltip");
  const badgesContainer = document.getElementById("overview-weight-badges");

  if (!canvas || !container) return;

  const ctx = canvas.getContext("2d");
  overviewChartPoints = [];

  // Parse and prepare weight data
  const rawWeights = a.weights || [];
  const data = [];
  rawWeights.forEach((w) => {
    const val = parseFloat(w.weight_g);
    if (w.date && !isNaN(val) && val > 0) {
      data.push({
        date: w.date,
        weight: val,
        pct: w.pct != null ? parseFloat(w.pct) : null,
      });
    }
  });

  data.sort((x, y) => (x.date > y.date ? 1 : x.date < y.date ? -1 : 0));

  const rect = container.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = rect.width || 400;
  const height = 240;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";

  ctx.save();
  ctx.scale(dpr, dpr);

  if (data.length === 0) {
    ctx.clearRect(0, 0, width, height);
    if (emptyMsg) emptyMsg.style.display = "flex";
    if (badgesContainer) badgesContainer.innerHTML = "";
    if (tooltip) tooltip.style.display = "none";
    ctx.restore();
    return;
  }

  if (emptyMsg) emptyMsg.style.display = "none";

  const startWeight = a.baseline_weight || data[0].weight;
  const limit80 = startWeight * 0.8;

  // Update badges
  if (badgesContainer) {
    const latestEntry = data[data.length - 1];
    const latestPct =
      startWeight > 0 ? (latestEntry.weight / startWeight) * 100 : 100;
    const isBelowLimit = latestEntry.weight < limit80;

    badgesContainer.innerHTML = `
      <span class="mbw-badge start" title="Baseline start weight">
        Start: <strong>${startWeight.toFixed(1)}g</strong> (100%)
      </span>
      <span class="mbw-badge latest ${isBelowLimit ? "warning" : ""}" title="Most recent recorded weight">
        Latest: <strong>${latestEntry.weight.toFixed(1)}g</strong> (${latestPct.toFixed(1)}%)
      </span>
      <span class="mbw-badge limit" title="80% threshold line (safety cutoff)">
        80% Limit: <strong>${limit80.toFixed(1)}g</strong>
      </span>
    `;
  }

  const margin = {
    top: 25,
    right: 90,
    bottom: 38,
    left: 60,
  };

  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  let minW = Math.min(...data.map((d) => d.weight), limit80);
  let maxW = Math.max(...data.map((d) => d.weight), startWeight);

  const span = maxW - minW || 5;
  minW = Math.floor(Math.max(0, minW - span * 0.15));
  maxW = Math.ceil(maxW + span * 0.15);

  function getY(val) {
    return margin.top + plotH - ((val - minW) / (maxW - minW)) * plotH;
  }

  function getX(idx) {
    if (data.length === 1) return margin.left + plotW / 2;
    return margin.left + (idx / (data.length - 1)) * plotW;
  }

  ctx.clearRect(0, 0, width, height);

  // Grid lines & Y-axis ticks
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.fillStyle = "rgba(200, 210, 220, 0.65)";
  ctx.font = "10.5px Inter, system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  const tickSteps = 4;
  for (let i = 0; i <= tickSteps; i++) {
    const val = minW + ((maxW - minW) / tickSteps) * i;
    const y = getY(val);

    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(margin.left + plotW, y);
    ctx.stroke();

    ctx.fillText(`${val.toFixed(1)}g`, margin.left - 8, y);
  }

  // Y Axis Rotated Label
  ctx.save();
  ctx.translate(14, margin.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(200, 210, 220, 0.5)";
  ctx.font = "10px Inter, system-ui, sans-serif";
  ctx.fillText("Body Weight (g)", 0, 0);
  ctx.restore();

  // 80% Safety Limit Line (Red dashed)
  const y80 = getY(limit80);
  if (y80 >= margin.top - 5 && y80 <= margin.top + plotH + 5) {
    ctx.save();
    ctx.beginPath();
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 2;
    ctx.moveTo(margin.left, y80);
    ctx.lineTo(margin.left + plotW, y80);
    ctx.stroke();

    ctx.setLineDash([]);
    ctx.fillStyle = "#ef4444";
    ctx.font = "bold 10px Inter, system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(`80% (${limit80.toFixed(1)}g)`, margin.left + plotW + 6, y80);
    ctx.restore();
  }

  // Plot Line & Gradient Fill
  if (data.length > 0) {
    ctx.save();
    const gradient = ctx.createLinearGradient(
      0,
      margin.top,
      0,
      margin.top + plotH,
    );
    gradient.addColorStop(0, "rgba(59, 130, 246, 0.28)");
    gradient.addColorStop(1, "rgba(59, 130, 246, 0.0)");

    ctx.beginPath();
    data.forEach((d, idx) => {
      const x = getX(idx);
      const y = getY(d.weight);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(getX(data.length - 1), margin.top + plotH);
    ctx.lineTo(getX(0), margin.top + plotH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.restore();

    // Stroke line
    ctx.save();
    ctx.beginPath();
    data.forEach((d, idx) => {
      const x = getX(idx);
      const y = getY(d.weight);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.restore();

    // Points & X Labels
    data.forEach((d, idx) => {
      const x = getX(idx);
      const y = getY(d.weight);
      const pct = startWeight > 0 ? (d.weight / startWeight) * 100 : 100;
      const isWarning = d.weight < limit80;

      overviewChartPoints.push({
        x,
        y,
        date: d.date,
        weight: d.weight,
        pct: pct,
        isWarning: isWarning,
      });

      // Draw dot
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = isWarning ? "#ef4444" : "#0284c7";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
      ctx.restore();

      // X-axis date label
      ctx.save();
      ctx.fillStyle = "rgba(200, 210, 220, 0.75)";
      ctx.font = "10px Inter, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";

      const shortDate = d.date.length > 5 ? d.date.slice(5) : d.date;
      ctx.fillText(shortDate, x, margin.top + plotH + 8);
      ctx.restore();
    });
  }

  ctx.restore();

  // Attach hover listener once
  if (!overviewTooltipAttached) {
    overviewTooltipAttached = true;
    canvas.addEventListener("mousemove", function (e) {
      const cRect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - cRect.left;
      const mouseY = e.clientY - cRect.top;

      let nearest = null;
      let minDist = 24;

      overviewChartPoints.forEach((pt) => {
        const dist = Math.hypot(pt.x - mouseX, pt.y - mouseY);
        if (dist < minDist) {
          minDist = dist;
          nearest = pt;
        }
      });

      if (nearest && tooltip) {
        tooltip.style.display = "block";
        tooltip.style.left = nearest.x + "px";
        tooltip.style.top = nearest.y + "px";

        const statusColor = nearest.isWarning ? "#ef4444" : "#4ade80";
        tooltip.innerHTML = `
          <div style="font-weight:700; margin-bottom:2px; color:#f8fafc;">${nearest.date}</div>
          <div>Weight: <strong>${nearest.weight.toFixed(1)} g</strong></div>
          <div>% Start: <strong style="color:${statusColor}">${nearest.pct.toFixed(1)}%</strong></div>
        `;
      } else if (tooltip) {
        tooltip.style.display = "none";
      }
    });

    canvas.addEventListener("mouseleave", function () {
      if (tooltip) tooltip.style.display = "none";
    });

    if (window.ResizeObserver && container) {
      const ro = new ResizeObserver(() => {
        const animals = getAnimalsData();
        const activeA = animals.find((x) => x.animal_id === currentAnimalId);
        if (activeA && activeProfileTab === "overview") {
          drawWeightCanvas("canvas-overview-weight", activeA);
        }
      });
      ro.observe(container);
    }
  }
}

// Attach globally for inline HTML event handlers
window.initTracker = initTracker;
window.switchTrackerView = switchTrackerView;
window.openMouseProfile = openMouseProfile;
window.onMouseSelectChange = onMouseSelectChange;
window.switchProfileTab = switchProfileTab;

document.addEventListener("DOMContentLoaded", initTracker);
