/* ZESCO DLR Digital Twin - dashboard controller (vanilla JS) */
"use strict";

const REFRESH_MS = 3000;
const STREAM_MS = 4000;

const state = {
  history: [],
  latest: null,
  events: [],
  forecast: null,
  streamTimer: null,
};

const els = {
  liveBadge: document.getElementById("liveBadge"),
  liveText: document.getElementById("liveText"),
  clock: document.getElementById("clock"),
  statusBanner: document.getElementById("statusBanner"),
  statusMessage: document.getElementById("statusMessage"),
  mCurrent: document.getElementById("mCurrent"),
  mCurrentSub: document.getElementById("mCurrentSub"),
  mStatic: document.getElementById("mStatic"),
  mDynamic: document.getElementById("mDynamic"),
  mDynamicSub: document.getElementById("mDynamicSub"),
  mTemp: document.getElementById("mTemp"),
  mTempSub: document.getElementById("mTempSub"),
  mSag: document.getElementById("mSag"),
  mClearance: document.getElementById("mClearance"),
  eventList: document.getElementById("eventList"),
  footerStatus: document.getElementById("footerStatus"),
  dataSource: document.getElementById("dataSource"),
  simAmbient: document.getElementById("simAmbient"),
  simAmbientV: document.getElementById("simAmbientV"),
  simWind: document.getElementById("simWind"),
  simWindV: document.getElementById("simWindV"),
  simCurrent: document.getElementById("simCurrent"),
  simCurrentV: document.getElementById("simCurrentV"),
  btnSend: document.getElementById("btnSend"),
  btnStream: document.getElementById("btnStream"),
};

const charts = {};

/* ----------------------- fetch helpers ----------------------- */
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(url + " -> " + res.status);
  return res.json();
}

/* ----------------------- charts ----------------------- */
Chart.defaults.color = "#8799bd";
Chart.defaults.borderColor = "rgba(255,255,255,0.06)";
Chart.defaults.font.family = '"Segoe UI", Roboto, sans-serif';

function baseOptions(extra) {
  return Object.assign(
    {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { boxWidth: 12, usePointStyle: true } } },
    },
    extra || {}
  );
}

function initCharts() {
  charts.capacity = new Chart(document.getElementById("capacityChart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Actual Load", data: [], borderColor: "#f7c948", backgroundColor: "rgba(247,201,72,0.15)", fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2.5 },
        { label: "Static Limit", data: [], borderColor: "#e63946", borderDash: [6, 4], pointRadius: 0, borderWidth: 2 },
        { label: "Dynamic Limit (DLR)", data: [], borderColor: "#2ecc71", pointRadius: 0, borderWidth: 2.5, tension: 0.3 },
      ],
    },
    options: baseOptions({ scales: { y: { title: { display: true, text: "Amperes (A)" }, suggestedMin: 0 } } }),
  });

  charts.thermal = new Chart(document.getElementById("thermalChart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Conductor Temp", data: [], borderColor: "#ff7849", tension: 0.3, pointRadius: 0, borderWidth: 2.5, yAxisID: "y" },
        { label: "Ambient Temp", data: [], borderColor: "#38bdf8", borderDash: [4, 4], pointRadius: 0, borderWidth: 2, yAxisID: "y" },
        { label: "Wind Speed", data: [], borderColor: "#b794f4", borderDash: [2, 3], pointRadius: 0, borderWidth: 1.5, yAxisID: "y2" },
      ],
    },
    options: baseOptions({
      scales: {
        y: { title: { display: true, text: "Temperature (deg C)" } },
        y2: { position: "right", title: { display: true, text: "Wind (m/s)" }, grid: { drawOnChartArea: false } },
      },
    }),
  });

  charts.sag = new Chart(document.getElementById("sagChart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Sag", data: [], borderColor: "#38bdf8", fill: true, backgroundColor: "rgba(56,189,248,0.12)", tension: 0.3, pointRadius: 0, borderWidth: 2.5 },
        { label: "Ground Clearance", data: [], borderColor: "#2ecc71", tension: 0.3, pointRadius: 0, borderWidth: 2.5 },
        { label: "Min Clearance", data: [], borderColor: "#e63946", borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: baseOptions({ scales: { y: { title: { display: true, text: "Meters (m)" }, suggestedMin: 0 } } }),
  });

  charts.forecast = new Chart(document.getElementById("forecastChart"), {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Forecast Dynamic Rating", data: [], borderColor: "#2ecc71", fill: true, backgroundColor: "rgba(46,204,113,0.14)", tension: 0.3, pointRadius: 2, borderWidth: 2.5, yAxisID: "y" },
        { label: "Static Rating", data: [], borderColor: "#e63946", borderDash: [6, 4], pointRadius: 0, borderWidth: 2, yAxisID: "y" },
        { label: "Ambient", data: [], borderColor: "#38bdf8", pointRadius: 0, borderWidth: 1.5, yAxisID: "y2" },
      ],
    },
    options: baseOptions({
      scales: {
        y: { title: { display: true, text: "Amperes (A)" }, suggestedMin: 0 },
        y2: { position: "right", title: { display: true, text: "Ambient (deg C)" }, grid: { drawOnChartArea: false } },
      },
    }),
  });
}

function updateCapacityChart() {
  const h = state.history;
  charts.capacity.data.labels = h.map((r) => (r.timestamp || "").slice(11, 19));
  charts.capacity.data.datasets[0].data = h.map((r) => r.current_load);
  charts.capacity.data.datasets[1].data = h.map((r) => r.static_rating);
  charts.capacity.data.datasets[2].data = h.map((r) => r.dynamic_rating);
  charts.capacity.update("none");
}

function updateThermalChart() {
  const h = state.history;
  charts.thermal.data.labels = h.map((r) => (r.timestamp || "").slice(11, 19));
  charts.thermal.data.datasets[0].data = h.map((r) => r.conductor_temp);
  charts.thermal.data.datasets[1].data = h.map((r) => r.ambient_temp);
  charts.thermal.data.datasets[2].data = h.map((r) => r.wind_speed);
  charts.thermal.update("none");
}

function updateSagChart() {
  const h = state.history;
  charts.sag.data.labels = h.map((r) => (r.timestamp || "").slice(11, 19));
  charts.sag.data.datasets[0].data = h.map((r) => r.sag_m);
  charts.sag.data.datasets[1].data = h.map((r) => r.clearance_m);
  charts.sag.data.datasets[2].data = h.map(() => 5.5);
  charts.sag.update("none");
}

function updateForecastChart(fc) {
  if (!fc) return;
  charts.forecast.data.labels = fc.hours;
  charts.forecast.data.datasets[0].data = fc.dynamic_rating;
  charts.forecast.data.datasets[1].data = fc.dynamic_rating.map(() => fc.static_rating);
  charts.forecast.data.datasets[2].data = fc.ambient;
  charts.forecast.update("none");
}

/* ----------------------- metrics & status ----------------------- */
function setStatus(kind, message) {
  els.statusBanner.className = "status-banner " + kind;
  els.statusMessage.textContent = message;
}

function renderMetrics(rec) {
  if (!rec) return;
  els.mCurrent.textContent = rec.current_load.toFixed(2) + " A";
  els.mCurrentSub.textContent = "load " + Math.round((rec.current_load / rec.dynamic_rating) * 100) + "% of dynamic";

  els.mStatic.textContent = rec.static_rating.toFixed(2) + " A";
  els.mDynamic.textContent = rec.dynamic_rating.toFixed(2) + " A";
  const gain = rec.capacity_gain_pct;
  const sign = gain >= 0 ? "+" : "";
  els.mDynamicSub.textContent = sign + gain + "% capacity vs static";
  els.mDynamicSub.className = "metric-sub " + (gain >= 0 ? "accent-good" : "accent-warn");

  els.mTemp.textContent = rec.conductor_temp.toFixed(1) + " deg C";
  const margin = 75.0 - rec.conductor_temp;
  els.mTempSub.textContent = margin.toFixed(1) + " deg C margin to max";
  els.mTempSub.className = "metric-sub " + (margin < 10 ? "accent-bad" : margin < 25 ? "accent-warn" : "");

  els.mSag.textContent = rec.sag_m.toFixed(2) + " m";
  els.mClearance.textContent = "clearance " + rec.clearance_m.toFixed(2) + " m";

  if (rec.status === "OK") {
    setStatus("ok", "Line operating within dynamic limits. Current load " + rec.current_load.toFixed(2) + " A is safe.");
  } else if (rec.status === "WARNING") {
    setStatus("warning", "UNLOCKED CAPACITY: " + rec.current_load.toFixed(2) + " A exceeds the static limit (" + rec.static_rating.toFixed(2) + " A) but is safe under current wind cooling (" + rec.wind_speed.toFixed(1) + " m/s).");
  } else {
    setStatus("", "CRITICAL OVERLOAD: " + rec.current_load.toFixed(2) + " A exceeds the dynamic limit (" + rec.dynamic_rating.toFixed(2) + " A). Thermal sagging risk - reduce load or dispatch crew.");
  }
}

function renderEvents(events) {
  els.eventList.innerHTML = "";
  if (!events.length) {
    els.eventList.innerHTML = '<li class="event-empty">No events yet</li>';
    return;
  }
  events.forEach((e) => {
    const li = document.createElement("li");
    li.className = "event-item " + (e.level || "info").toLowerCase();
    const t = document.createElement("span");
    t.className = "ev-time";
    t.textContent = (e.timestamp || "").slice(11, 19);
    const m = document.createElement("span");
    m.className = "ev-msg";
    m.textContent = e.message;
    li.appendChild(t);
    li.appendChild(m);
    els.eventList.appendChild(li);
  });
}

/* ----------------------- data loading ----------------------- */
async function loadAll() {
  try {
    const [latest, history, events, forecast] = await Promise.all([
      getJSON("/api/telemetry/latest"),
      getJSON("/api/telemetry/history?limit=60"),
      getJSON("/api/telemetry/events?limit=20"),
      getJSON("/api/forecast"),
    ]);

    state.latest = latest;
    state.history = history;
    state.events = events;
    state.forecast = forecast;

    renderMetrics(latest);
    renderEvents(events);
    updateCapacityChart();
    updateThermalChart();
    updateSagChart();
    updateForecastChart(forecast);

    els.liveBadge.classList.remove("offline");
    els.liveText.textContent = "Live";
    els.footerStatus.textContent = "Connected to backend";
  } catch (err) {
    els.liveBadge.classList.add("offline");
    els.liveText.textContent = "Offline";
    els.footerStatus.textContent = "Cannot reach backend - " + err.message;
    setStatus("", "Backend unreachable. Check that the Flask service is running.");
  }
}

/* ----------------------- simulator ----------------------- */
function simValues() {
  return {
    ambient_temp: parseFloat(els.simAmbient.value),
    wind_speed: parseFloat(els.simWind.value),
    current_load: parseFloat(els.simCurrent.value),
    conductor_temp: 0, // engine will predict if not measured
    humidity: 50,
  };
}

async function sendSimReading() {
  els.btnSend.disabled = true;
  try {
    const res = await fetch("/api/demo/telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(simValues()),
    });
    if (!res.ok) throw new Error("POST failed: " + res.status);
    await loadAll();
    els.dataSource.textContent = "simulator";
  } catch (err) {
    setStatus("", "Failed to send simulator reading: " + err.message);
  } finally {
    els.btnSend.disabled = false;
  }
}

function toggleStream() {
  if (state.streamTimer) {
    clearInterval(state.streamTimer);
    state.streamTimer = null;
    els.btnStream.innerHTML = '<i class="fa-solid fa-play"></i> Auto Stream';
    return;
  }
  state.streamTimer = setInterval(sendSimReading, STREAM_MS);
  els.btnStream.innerHTML = '<i class="fa-solid fa-pause"></i> Stop Stream';
}

/* ----------------------- misc UI ----------------------- */
function updateClock() {
  const d = new Date();
  els.clock.textContent =
    d.toLocaleTimeString("en-GB", { hour12: false }) + "  " +
    d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function bindSlider(labelEl, valueEl, unit, decimals) {
  return function () {
    const v = parseFloat(labelEl.value).toFixed(decimals);
    valueEl.textContent = v + (unit || "");
  };
}

/* ----------------------- init ----------------------- */
function init() {
  initCharts();
  updateClock();
  setInterval(updateClock, 1000);

  const syncAmbient = bindSlider(els.simAmbient, els.simAmbientV, " deg C", 1);
  const syncWind = bindSlider(els.simWind, els.simWindV, " m/s", 1);
  const syncCurrent = bindSlider(els.simCurrent, els.simCurrentV, " A", 1);
  syncAmbient(); syncWind(); syncCurrent();

  els.simAmbient.addEventListener("input", syncAmbient);
  els.simWind.addEventListener("input", syncWind);
  els.simCurrent.addEventListener("input", syncCurrent);

  els.btnSend.addEventListener("click", sendSimReading);
  els.btnStream.addEventListener("click", toggleStream);

  loadAll();
  setInterval(loadAll, REFRESH_MS);
}

document.addEventListener("DOMContentLoaded", init);
