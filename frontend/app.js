// Leash dashboard client. Talks to the FastAPI backend over REST (to kick off
// a session) and WebSocket (to stream events as the agent runs).

const BACKEND = "http://localhost:8000";
const WS_BACKEND = "ws://localhost:8000";

const els = {
  connDot: document.getElementById("connDot"),
  connLabel: document.getElementById("connLabel"),
  taskInput: document.getElementById("taskInput"),
  scenarioSelect: document.getElementById("scenarioSelect"),
  replayScenarioSelect: document.getElementById("replayScenarioSelect"),
  btnReplay: document.getElementById("btnReplay"),
  btnLive: document.getElementById("btnLive"),
  eventLog: document.getElementById("eventLog"),
  incidentList: document.getElementById("incidentList"),
};

let ws = null;
let sessionId = null;
let stepCounter = 0;
let riskChart = null;
let chartLabels = [];
let chartScores = [];
let chartColors = [];

// ---------------------------------------------------------------- chart ----
function initChart() {
  const ctx = document.getElementById("riskChart").getContext("2d");
  riskChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Risk score",
          data: [],
          borderColor: "#8fc9a0",
          backgroundColor: "rgba(143,201,160,0.08)",
          tension: 0.25,
          fill: true,
          pointRadius: 6,
          pointBackgroundColor: [],
          pointBorderColor: "#0c1210",
          pointBorderWidth: 1.5,
        },
        {
          label: "Block threshold",
          data: [],
          borderColor: "rgba(217,105,91,0.5)",
          borderDash: [6, 6],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#9aa89e" },
        },
        x: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#9aa89e" },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Risk: ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
    },
  });
}

function pushChartPoint(label, riskScore, verdict) {
  const color =
    verdict === "block" ? "#d9695b" : verdict === "review" ? "#e0b96b" : "#8fc9a0";
  chartLabels.push(label);
  chartScores.push(riskScore);
  chartColors.push(color);

  riskChart.data.labels = chartLabels;
  riskChart.data.datasets[0].data = chartScores;
  riskChart.data.datasets[0].pointBackgroundColor = chartColors;
  riskChart.data.datasets[1].data = chartLabels.map(() => 70);
  riskChart.update();
}

function resetChart() {
  chartLabels = [];
  chartScores = [];
  chartColors = [];
  if (riskChart) {
    riskChart.data.labels = [];
    riskChart.data.datasets[0].data = [];
    riskChart.data.datasets[1].data = [];
    riskChart.update();
  }
}

// ------------------------------------------------------------- log/UI ----
function clearLog() {
  els.eventLog.innerHTML = "";
}

function addLog(html, cls) {
  if (els.eventLog.querySelector(".log-empty")) els.eventLog.innerHTML = "";
  const div = document.createElement("div");
  div.className = `log-entry ${cls}`;
  div.innerHTML = html;
  els.eventLog.appendChild(div);
  els.eventLog.scrollTop = els.eventLog.scrollHeight;
}

function clearIncidents() {
  els.incidentList.innerHTML = '<p class="log-empty">No incidents yet.</p>';
}

function addIncident(report) {
  if (els.incidentList.querySelector(".log-empty")) els.incidentList.innerHTML = "";

  const cardCls = report.verdict === "block" ? "" : "review";
  const contribRows = report.top_contributions
    .slice(0, 5)
    .map((c) => {
      const pct = Math.min(100, Math.abs(c.contribution) * 8 + 6);
      const dir = c.contribution >= 0 ? "pos" : "neg";
      return `
        <div class="contrib-row">
          <span class="contrib-label">${c.description}</span>
          <span class="contrib-bar-track"><span class="contrib-bar ${dir}" style="width:${pct}%"></span></span>
          <span class="contrib-val">${c.value.toFixed(1)}</span>
        </div>`;
    })
    .join("");

  const div = document.createElement("div");
  div.className = `incident-card ${cardCls}`;
  div.innerHTML = `
    <div class="incident-head">
      <span class="incident-title">${report.verdict.toUpperCase()} — ${report.tool_name}(${Object.keys(
    report.arguments
  ).join(", ")})</span>
      <span class="incident-score">${report.risk_score.toFixed(0)}/100</span>
    </div>
    <div class="incident-explain">${report.explanation}<br><em>${report.recommended_action}</em></div>
    ${contribRows}
  `;
  els.incidentList.appendChild(div);
}

function setConnected(isConnected) {
  els.connDot.className = `dot ${isConnected ? "dot-on" : "dot-off"}`;
  els.connLabel.textContent = isConnected ? `connected (${sessionId})` : "disconnected";
}

function setButtonsBusy(busy) {
  els.btnReplay.disabled = busy;
  els.btnLive.disabled = busy;
}

// ------------------------------------------------------------- session ----
async function newSessionId() {
  const res = await fetch(`${BACKEND}/api/session/new`, { method: "POST" });
  const data = await res.json();
  return data.session_id;
}

function openSocket(id) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`${WS_BACKEND}/ws/${id}`);
    socket.onopen = () => resolve(socket);
    socket.onerror = (e) => reject(e);
    socket.onmessage = handleEvent;
    socket.onclose = () => setConnected(false);
  });
}

async function startSession(kind) {
  setButtonsBusy(true);
  clearLog();
  clearIncidents();
  resetChart();
  stepCounter = 0;

  try {
    sessionId = await newSessionId();
    ws = await openSocket(sessionId);
    setConnected(true);

    if (kind === "replay") {
      const scenario = els.replayScenarioSelect.value;
      await fetch(`${BACKEND}/api/session/replay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, scenario }),
      });
    } else {
      const task = els.taskInput.value.trim();
      const scenario = els.scenarioSelect.value || null;
      await fetch(`${BACKEND}/api/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, task, scenario }),
      });
    }
  } catch (err) {
    addLog(
      `<span class="tag">ERROR</span> Could not reach the Leash backend at ${BACKEND}. Is it running? (${err})`,
      "error"
    );
    setButtonsBusy(false);
  }
}

// ------------------------------------------------------------- events ----
function handleEvent(msgEvent) {
  const event = JSON.parse(msgEvent.data);
  const d = event.data;

  switch (event.type) {
    case "session_start":
      addLog(
        `<span class="tag">SESSION</span> <span class="meta">${d.mode === "replay" ? "Replay" : "Live"} run started — task: "${escapeHtml(
          d.task
        )}"${d.scenario ? ` <em>(scenario: ${d.scenario})</em>` : ""}</span>`,
        "system"
      );
      break;

    case "agent_message":
      addLog(`<span class="tag">AGENT</span> ${escapeHtml(d.content)}`, "msg");
      break;

    case "action_proposed":
      addLog(
        `<span class="tag">PROPOSED</span> <span class="tool">${d.tool_name}</span>(${formatArgs(d.arguments)})`,
        "proposed"
      );
      break;

    case "action_scored": {
      const s = d.score;
      stepCounter += 1;
      pushChartPoint(`step ${d.step}`, s.risk_score, s.verdict);
      break;
    }

    case "action_allowed": {
      const s = d.score;
      const cls = s.verdict === "review" ? "review" : "allow";
      addLog(
        `<span class="tag">${s.verdict.toUpperCase()}</span> <span class="tool">${d.tool_name}</span> executed <span class="risk">${s.risk_score.toFixed(
          0
        )}/100</span>`,
        cls
      );
      break;
    }

    case "action_blocked": {
      const s = d.score;
      addLog(
        `<span class="tag">BLOCKED</span> <span class="tool">${d.tool_name}</span>(${formatArgs(
          d.arguments
        )}) intercepted before execution <span class="risk">${s.risk_score.toFixed(0)}/100</span>`,
        "block"
      );
      break;
    }

    case "action_result":
      addLog(`<span class="meta">→ ${escapeHtml(d.result)}</span>`, "msg");
      break;

    case "incident_report":
      addIncident(d.report);
      break;

    case "task_complete":
      addLog(
        `<span class="tag">DONE</span> ${escapeHtml(d.final_message || "Task complete.")}`,
        "system"
      );
      setButtonsBusy(false);
      break;

    case "error":
      addLog(`<span class="tag">ERROR</span> ${escapeHtml(d.message)}`, "error");
      setButtonsBusy(false);
      break;
  }
}

function formatArgs(args) {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${escapeHtml(String(v)).slice(0, 40)}`)
    .join(", ");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ------------------------------------------------------------- wire up ----
try {
  initChart();
} catch (e) {
  console.error("Chart.js failed to load — timeline will be unavailable, but the rest of the app still works.", e);
}
els.btnReplay.addEventListener("click", () => startSession("replay"));
els.btnLive.addEventListener("click", () => startSession("live"));