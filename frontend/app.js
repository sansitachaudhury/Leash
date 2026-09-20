const API = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/events`;

const genBtn = document.getElementById("genBtn");
const runBtn = document.getElementById("runBtn");
const scenarioList = document.getElementById("scenarioList");
const liveLog = document.getElementById("liveLog");
const scoreHeadline = document.getElementById("scoreHeadline");
const scoreDetails = document.getElementById("scoreDetails");
const scoreMetaRow = document.getElementById("scoreMetaRow");
const scenarioTable = document.getElementById("scenarioTable");
const wsStatus = document.getElementById("wsStatus");
const severityBar = document.getElementById("severityBar");
const statsRow = document.getElementById("statsRow");
const exportRow = document.getElementById("exportRow");
const runHistory = document.getElementById("runHistory");
const hardeningToggle = document.getElementById("hardeningToggle");
const interventionModal = document.getElementById("interventionModal");

let breakdownChart, regressionChart;
let currentRunId = null;
const CF = { family: "'Inter', sans-serif", size: 11, weight: '600' };

// ===== NAV ACTIVE STATE =====
const navLinks = document.querySelectorAll('.nav-link');
const sections = document.querySelectorAll('section[id]');

function updateNav() {
  const scrollY = window.scrollY + 200;
  sections.forEach(sec => {
    const top = sec.offsetTop;
    const height = sec.offsetHeight;
    const id = sec.getAttribute('id');
    if (scrollY >= top && scrollY < top + height) {
      navLinks.forEach(l => l.classList.remove('active'));
      const active = document.querySelector(`.nav-link[href="#${id}"]`);
      if (active) active.classList.add('active');
    }
  });
}
window.addEventListener('scroll', updateNav, { passive: true });

// ===== WebSocket =====
let socket;
let pendingIntervention = null;

function connectWS() {
  wsStatus.className = "conn-badge";
  wsStatus.querySelector(".conn-text").textContent = "Connecting...";

  socket = new WebSocket(WS_URL);
  socket.onopen = () => {
    wsStatus.className = "conn-badge online";
    wsStatus.querySelector(".conn-text").textContent = "Live";
  };
  socket.onmessage = (msg) => {
    try { handleWSEvent(JSON.parse(msg.data)); } catch (e) { console.error("WS:", e); }
  };
  socket.onclose = () => {
    wsStatus.className = "conn-badge offline";
    wsStatus.querySelector(".conn-text").textContent = "Offline";
    resetRunBtn();
    setTimeout(connectWS, 3000);
  };
  socket.onerror = () => socket.close();
}

function handleWSEvent(evt) {
  switch (evt.type) {
    case "suite_start":
      logLine(`Running ${evt.total} scenarios...`, "l-system");
      break;
    case "scenario_start":
      logLine(`[${evt.category.replace(/_/g, ' ')}] ${evt.task}`);
      break;
    case "step": {
      const risk = evt.risk.risk_score;
      const rc = risk > 0.7 ? "var(--danger)" : risk > 0.4 ? "var(--warning)" : "var(--accent)";
      const tags = (evt.injected ? " [INJECT]" : "") + (evt.blocked_by_human ? " [BLOCKED]" : "") + (evt.approved_by_human ? " [APPROVED]" : "");
      logLine(`  step ${evt.step}: <span style="color:var(--text)">${evt.tool}</span> risk=${risk.toFixed(2)}<span style="color:${rc}">\u2588</span>${tags}`, evt.injected ? "l-injected" : "");
      break;
    }
    case "interception_triggered":
      showInterventionModal(evt);
      logLine(`  INTERCEPT: ${evt.tool} risk=${evt.risk.risk_score.toFixed(2)} - awaiting decision`, "l-intercept");
      break;
    case "scenario_classified": {
      const c = evt.classification;
      if (c.passed) {
        logLine(`  \u2192 PASS`, "l-pass");
      } else {
        logLine(`  \u2192 FAIL: ${c.failures.map(f => f.category.replace(/_/g, ' ')).join(", ")}`, "l-fail");
      }
      break;
    }
    case "suite_done":
      currentRunId = evt.run_id;
      renderScorecard(evt.scorecard);
      updateSeverityBar(evt.scorecard.severity_breakdown);
      loadRegression();
      loadRunHistory();
      loadStats();
      resetRunBtn();
      exportRow.style.display = "flex";
      logLine(`Done in ${evt.elapsed_seconds}s \u2014 Score: ${evt.scorecard.reliability_score}%`, "l-pass");
      break;
  }
}

function resetRunBtn() {
  runBtn.disabled = false;
  runBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Suite';
}

function showInterventionModal(evt) {
  pendingIntervention = evt;
  document.getElementById("interventionDesc").textContent = `High-risk call: ${evt.tool}`;
  document.getElementById("interventionDetails").innerHTML =
    `<div><b>Tool:</b> ${evt.tool}</div>` +
    `<div><b>Args:</b> ${JSON.stringify(evt.args, null, 2)}</div>` +
    `<div><b>Risk:</b> ${evt.risk.risk_score.toFixed(3)}</div>` +
    `<div><b>Sensitivity:</b> ${evt.risk.tool_sensitivity}</div>` +
    `<div><b>Drift:</b> ${evt.risk.semantic_drift}</div>`;
  interventionModal.style.display = "flex";
}

document.getElementById("interventionApprove").addEventListener("click", () => {
  if (pendingIntervention) fetch(`${API}/api/intervene`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ scenario_id: pendingIntervention.scenario_id, action: "approve" }) });
  interventionModal.style.display = "none";
  pendingIntervention = null;
});

document.getElementById("interventionDeny").addEventListener("click", () => {
  if (pendingIntervention) fetch(`${API}/api/intervene`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ scenario_id: pendingIntervention.scenario_id, action: "deny" }) });
  interventionModal.style.display = "none";
  pendingIntervention = null;
});

// ===== Generate =====
genBtn.addEventListener("click", async () => {
  genBtn.disabled = true;
  genBtn.innerHTML = '<span class="loading"></span> Generating...';
  scenarioList.innerHTML = '<div class="empty-state loading"><span>Generating scenarios...</span></div>';
  try {
    const res = await fetch(`${API}/api/generate-scenarios`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ num_scenarios: Number(document.getElementById("numScenarios").value) }) });
    const data = await res.json();
    renderScenarios(data.scenarios);
  } catch (err) {
    scenarioList.innerHTML = '<div class="empty-state" style="color:var(--danger)"><span>Failed to generate.</span></div>';
  } finally {
    genBtn.disabled = false;
    genBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg> Generate';
  }
});

function renderScenarios(scenarios) {
  if (!scenarios?.length) { scenarioList.innerHTML = '<div class="empty-state"><span>No scenarios.</span></div>'; return; }
  scenarioList.innerHTML = scenarios.map(s =>
    `<div class="scenario-item">
      <span class="sc-title">${s.title}</span>
      <span class="badge ${s.category}">${s.category.replace(/_/g, ' ')}</span>
      <button class="del-btn" onclick="deleteScenario('${s.id}')" title="Remove">&times;</button>
    </div>`
  ).join("");
}

window.deleteScenario = async (id) => {
  await fetch(`${API}/api/scenarios/${id}`, { method: "DELETE" });
  const res = await fetch(`${API}/api/scenarios`);
  renderScenarios((await res.json()).scenarios);
};

document.getElementById("addCustomBtn").addEventListener("click", async () => {
  const title = document.getElementById("customTitle").value.trim();
  const task = document.getElementById("customTask").value.trim();
  if (!title || !task) return;
  await fetch(`${API}/api/custom-scenario`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ title, task, category: document.getElementById("customCategory").value }) });
  const res = await fetch(`${API}/api/scenarios`);
  renderScenarios((await res.json()).scenarios);
  document.getElementById("customTitle").value = "";
  document.getElementById("customTask").value = "";
});

// ===== Run =====
runBtn.addEventListener("click", async () => {
  liveLog.innerHTML = '<div class="log-line l-system">Initializing sandbox...</div>';
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="loading"></span> Running...';
  try {
    const res = await fetch(`${API}/api/run-suite`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ run_label: document.getElementById("runLabel").value || "run" }) });
    const data = await res.json();
    if (data.error) { logLine(`Error: ${data.error}`, "l-fail"); resetRunBtn(); }
  } catch (err) { logLine(`Network error: ${err.message}`, "l-fail"); resetRunBtn(); }
});

function logLine(text, cls = "") {
  const empty = liveLog.querySelector(".empty-state");
  if (empty) liveLog.innerHTML = "";
  const div = document.createElement("div");
  div.className = "log-line " + cls;
  div.innerHTML = text;
  liveLog.appendChild(div);
  liveLog.scrollTop = liveLog.scrollHeight;
}

// ===== Hardening =====
hardeningToggle.addEventListener("change", async () => {
  const on = hardeningToggle.checked;
  await fetch(`${API}/api/settings`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({ hardening_mode: on }) });
  logLine(on ? "Hardening ENABLED \u2014 high-risk actions intercepted" : "Hardening disabled", "l-system");
});

// ===== Scorecard =====
function renderScorecard(sc) {
  scoreHeadline.innerHTML = `${sc.reliability_score}<span style="font-size:2rem;opacity:0.5">%</span>`;
  scoreDetails.textContent = `${sc.passed} / ${sc.total_scenarios} scenarios passed`;
  scoreMetaRow.textContent = `Fail rate: ${sc.fail_rate}% | Avg steps: ${sc.avg_steps_per_scenario}`;

  const cats = Object.keys(sc.failure_breakdown);
  const vals = cats.map(c => sc.failure_breakdown[c]);
  if (breakdownChart) breakdownChart.destroy();
  breakdownChart = new Chart(document.getElementById("breakdownChart"), {
    type: "bar",
    data: { labels: cats.map(c => c.replace(/_/g, ' ')), datasets: [{ data: vals, backgroundColor: "rgba(255,77,106,0.6)", borderColor: "var(--danger)", borderWidth: 1, borderRadius: 6 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: "FAILURES BY TYPE", color: "#636671", font: { ...CF, size: 11, weight: '700' } }, legend: { display: false } }, scales: { x: { ticks: { color: "#636671", font: CF, maxRotation: 45 }, grid: { color: "rgba(255,255,255,0.03)" } }, y: { ticks: { color: "#636671", font: CF, stepSize: 1 }, grid: { color: "rgba(255,255,255,0.03)" }, beginAtZero: true } } }
  });

  scenarioTable.innerHTML = `<table><thead><tr><th>Scenario</th><th>Category</th><th>Result</th><th>Failures</th><th>Risk</th></tr></thead><tbody>${sc.scenarios.map(s => {
    const mr = s.max_risk || 0;
    const rc = mr > 0.7 ? "var(--danger)" : mr > 0.4 ? "var(--warning)" : "var(--accent)";
    return `<tr><td title="${s.task}">${s.task.slice(0,45)}${s.task.length>45?"\u2026":""}</td><td><span class="badge ${s.category}">${s.category.replace(/_/g,' ')}</span></td><td><span class="${s.passed?"tag-pass":"tag-fail"}">${s.passed?"PASS":"FAIL"}</span></td><td>${s.failures.length?s.failures.map(f=>`<span title="${f.evidence}">${f.category.replace(/_/g,' ')}</span>`).join(", "):"\u2014"}</td><td><span style="font-family:var(--mono);font-size:0.75rem;color:${rc}">${mr.toFixed(2)}</span><span class="risk-mini"><span class="risk-mini-fill" style="width:${mr*100}%;background:${rc}"></span></span></td></tr>`;
  }).join("")}</tbody></table>`;
}

function updateSeverityBar(sev) {
  if (!sev) return;
  const t = (sev.critical||0)+(sev.high||0)+(sev.medium||0)+(sev.low||0);
  if (t === 0) { severityBar.style.display = "none"; return; }
  severityBar.style.display = "block";
  document.getElementById("sevCritical").style.width = `${(sev.critical||0)/t*100}%`;
  document.getElementById("sevHigh").style.width = `${(sev.high||0)/t*100}%`;
  document.getElementById("sevMedium").style.width = `${(sev.medium||0)/t*100}%`;
  document.getElementById("sevLow").style.width = `${(sev.low||0)/t*100}%`;
}

// ===== Charts =====
async function loadRegression() {
  try {
    const data = await (await fetch(`${API}/api/runs`)).json();
    if (!data.runs?.length) { renderPlaceholderRegression(); return; }
    const labels = data.runs.map(r => `${r.run_label} (${new Date(r.timestamp*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})})`);
    const scores = data.runs.map(r => r.reliability_score);
    if (regressionChart) regressionChart.destroy();
    regressionChart = new Chart(document.getElementById("regressionChart"), {
      type: "line",
      data: { labels, datasets: [{ data: scores, borderColor: "#00d68f", backgroundColor: "rgba(0,214,143,0.05)", fill: true, tension: 0.35, borderWidth: 2, pointBackgroundColor: "#00d68f", pointRadius: 4, pointHoverRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: "REGRESSION TRACKER", color: "#636671", font: { ...CF, size: 11, weight: '700' } }, legend: { display: false } }, scales: { y: { min: 0, max: 100, ticks: { color: "#636671", font: CF }, grid: { color: "rgba(255,255,255,0.03)" } }, x: { ticks: { color: "#636671", font: CF, maxRotation: 45 }, grid: { color: "rgba(255,255,255,0.03)" } } } }
    });
  } catch (e) { console.error(e); }
}

function renderPlaceholderRegression() {
  if (regressionChart) regressionChart.destroy();
  regressionChart = new Chart(document.getElementById("regressionChart"), {
    type: "line",
    data: { labels: ["No Runs"], datasets: [{ data: [0], borderColor: "rgba(255,255,255,0.1)", borderDash: [5,5] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: "REGRESSION TRACKER", color: "#636671", font: { ...CF, size: 11, weight: '700' } }, legend: { display: false } }, scales: { y: { min: 0, max: 100, ticks: { color: "#636671", font: CF }, grid: { color: "rgba(255,255,255,0.03)" } }, x: { ticks: { color: "#636671", font: CF }, grid: { color: "rgba(255,255,255,0.03)" } } } }
  });
}

// ===== History =====
async function loadRunHistory() {
  try {
    const data = await (await fetch(`${API}/api/runs`)).json();
    if (!data.runs?.length) { runHistory.innerHTML = '<div class="empty-state"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.3"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg><span>No runs yet.</span></div>'; return; }
    runHistory.innerHTML = data.runs.reverse().slice(0,15).map(r => {
      const s = r.reliability_score;
      const sc = s >= 80 ? "sc-good" : s >= 50 ? "sc-warn" : "sc-bad";
      return `<div class="run-item"><div class="run-info"><div class="run-label-text">${r.run_label}</div><div class="run-meta">${new Date(r.timestamp*1000).toLocaleString()} | ${r.passed}/${r.total_scenarios} passed</div></div><div class="run-score ${sc}">${s}%</div></div>`;
    }).join("");
  } catch (e) { console.error(e); }
}

// ===== Stats =====
async function loadStats() {
  try {
    const d = await (await fetch(`${API}/api/stats`)).json();
    if (d.total_runs > 0) {
      statsRow.style.display = "grid";
      document.getElementById("statAvg").textContent = `${d.avg_score}%`;
      document.getElementById("statBest").textContent = `${d.best_score}%`;
      document.getElementById("statWorst").textContent = `${d.worst_score}%`;
      document.getElementById("statRuns").textContent = d.total_runs;
    }
  } catch (e) { console.error(e); }
}

// ===== Export =====
document.getElementById("exportJsonBtn")?.addEventListener("click", () => { if (currentRunId) window.open(`${API}/api/runs/${currentRunId}/export?format=json`, "_blank"); });
document.getElementById("exportCsvBtn")?.addEventListener("click", () => { if (currentRunId) window.open(`${API}/api/runs/${currentRunId}/export?format=csv`, "_blank"); });

// ===== Init =====
connectWS();
window.addEventListener("load", () => {
  loadRegression();
  loadRunHistory();
  loadStats();
  fetch(`${API}/api/scenarios`).then(r => r.json()).then(d => { if (d.scenarios?.length) renderScenarios(d.scenarios); }).catch(() => {});
  fetch(`${API}/api/settings`).then(r => r.json()).then(d => { if (d.settings?.hardening_mode) hardeningToggle.checked = true; }).catch(() => {});
});
