// Analytics dashboard — ServeLens AI

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

// ===== Clock =====
function tickClock() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  $('#clock').textContent =
    `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}  ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
setInterval(tickClock, 1000);
tickClock();

// ===== Chart.js global defaults (dark theme) =====
Chart.defaults.color = '#8a96a8';
Chart.defaults.borderColor = '#232831';
Chart.defaults.font.family = '"JetBrains Mono", monospace';
Chart.defaults.font.size = 10;

const TOOLTIP = {
  backgroundColor: '#161a21',
  borderColor: '#2e3540',
  borderWidth: 1,
  titleColor: '#e6ebf2',
  bodyColor: '#8a96a8',
  padding: 10,
  cornerRadius: 2,
};

const CLASS_COLORS = {
  person:          '#4ade80',
  face:            '#60a5fa',
  fire:            '#ff5470',
  smoke:           '#94a3b8',
  license_plate:   '#ffe45c',
};

function classColor(cls) {
  return CLASS_COLORS[cls.toLowerCase()] || '#8b5cf6';
}

// ===== State =====
let currentDays = 7;
const charts = {};

// ===== Period selector =====
$$('.period-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.period-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    currentDays = +btn.dataset.days;
    loadAnalytics(currentDays);
  });
});

// ===== Data loader =====
async function loadAnalytics(days) {
  try {
    const r = await fetch(`/api/analytics?days=${days}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    renderKPIs(d.summary);
    renderTimeline(d.events_by_day, d.events_by_hour, days);
    renderTypes(d.events_by_class);
    renderCameras(d.events_by_camera);
    renderHeatmap(d.heatmap);
    renderPlates(d.top_plates);
    renderEvents(d.recent_events);
    const ts = $('#lastUpdate');
    if (ts) ts.textContent = new Date().toLocaleTimeString();
  } catch (e) {
    console.error('[Analytics] load failed:', e);
  }
}

// ===== KPIs =====
function setText(sel, val) {
  const el = $(sel);
  if (!el) return;
  el.textContent = typeof val === 'number' ? val.toLocaleString() : (val != null ? val : '—');
}

function renderKPIs(s) {
  if (!s) return;
  setText('#kpiTotal',     s.total_events);
  setText('#kpiToday',     s.events_today);
  setText('#kpiFireSmoke', s.fire_smoke_alerts);
  setText('#kpiPeople',    s.person_detections);
  setText('#kpiFaces',     s.face_detections);
  setText('#kpiPlates',    s.plate_reads);
}

// ===== Events over time (bar) =====
function renderTimeline(byDay, byHour, days) {
  const ctx = $('#chartTimeline');
  if (!ctx) return;

  let labels, data;
  if (days <= 2) {
    labels = byHour.map((x) => `${String(x.hour).padStart(2, '0')}:00`);
    data   = byHour.map((x) => x.count);
    const hint = $('#timelineHint');
    if (hint) hint.textContent = 'hourly';
  } else {
    labels = byDay.map((x) => x.date.slice(5)); // MM-DD
    data   = byDay.map((x) => x.count);
    const hint = $('#timelineHint');
    if (hint) hint.textContent = 'daily';
  }

  if (charts.timeline) charts.timeline.destroy();
  charts.timeline = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: 'rgba(255,174,0,0.18)',
        borderColor:     '#ffae00',
        borderWidth:     1,
        borderRadius:    2,
        borderSkipped:   false,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: {
        legend:  { display: false },
        tooltip: { ...TOOLTIP, callbacks: { title: (i) => i[0].label, label: (i) => ` ${i.parsed.y} events` } },
      },
      scales: {
        x: { grid: { color: '#1a1f28' }, ticks: { maxRotation: 0, maxTicksLimit: 14 } },
        y: { grid: { color: '#1a1f28' }, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

// ===== Detection type doughnut =====
function renderTypes(byClass) {
  const ctx = $('#chartTypes');
  if (!ctx) return;

  if (!byClass || !byClass.length) {
    drawEmpty(ctx, 'No events in period');
    return;
  }

  const labels = byClass.map((x) => x.class.toUpperCase());
  const data   = byClass.map((x) => x.count);
  const colors = byClass.map((x) => classColor(x.class));

  if (charts.types) charts.types.destroy();
  charts.types = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor:     colors.map((c) => c + 'aa'),
        borderColor:         colors,
        borderWidth:         1.5,
        hoverBackgroundColor: colors,
        hoverBorderWidth:    2,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      cutout:              '62%',
      plugins: {
        legend: {
          position: 'right',
          labels: {
            boxWidth: 10,
            padding:  12,
            color:    '#8a96a8',
            font:     { size: 10, family: '"JetBrains Mono", monospace' },
          },
        },
        tooltip: {
          ...TOOLTIP,
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed.toLocaleString()}`,
          },
        },
      },
    },
  });
}

// ===== Camera alert horizontal bar =====
function renderCameras(byCam) {
  const ctx = $('#chartCameras');
  if (!ctx) return;

  if (!byCam || !byCam.length) {
    drawEmpty(ctx, 'No data');
    return;
  }

  if (charts.cameras) charts.cameras.destroy();
  charts.cameras = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: byCam.map((x) => x.cam_name),
      datasets: [{
        data:            byCam.map((x) => x.count),
        backgroundColor: 'rgba(96,165,250,0.22)',
        borderColor:     '#60a5fa',
        borderWidth:     1,
        borderRadius:    2,
        borderSkipped:   false,
      }],
    },
    options: {
      indexAxis:           'y',
      responsive:          true,
      maintainAspectRatio: false,
      plugins: {
        legend:  { display: false },
        tooltip: { ...TOOLTIP, callbacks: { label: (i) => ` ${i.parsed.x} events` } },
      },
      scales: {
        x: { grid: { color: '#1a1f28' }, beginAtZero: true, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
  });
}

// ===== Activity heatmap (DOM-based, 7 days × 24 hours) =====
function renderHeatmap({ data, max }) {
  const el = $('#heatmapGrid');
  if (!el) return;

  const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const effectiveMax = max || 1;

  let html = '<div class="heatmap-container">';

  // Day labels column
  html += '<div class="heatmap-days">';
  for (const d of DAY_LABELS) {
    html += `<div class="heatmap-day-label">${d}</div>`;
  }
  html += '</div>';

  // Grid
  html += '<div class="heatmap-grid-wrap">';

  // Hour labels row
  html += '<div class="heatmap-hours-row">';
  for (let h = 0; h < 24; h++) {
    html += `<div class="heatmap-hour-label">${h % 6 === 0 ? String(h).padStart(2, '0') : ''}</div>`;
  }
  html += '</div>';

  // Data rows
  for (let d = 0; d < 7; d++) {
    html += '<div class="heatmap-row">';
    for (let h = 0; h < 24; h++) {
      const v   = data[d][h];
      const op  = v === 0 ? 0.06 : +(0.15 + (v / effectiveMax) * 0.85).toFixed(3);
      const tip = `${DAY_LABELS[d]} ${String(h).padStart(2, '0')}:00 — ${v} event${v !== 1 ? 's' : ''}`;
      html += `<div class="heatmap-cell" style="opacity:${op}" title="${tip}"></div>`;
    }
    html += '</div>';
  }

  html += '</div></div>'; // heatmap-grid-wrap, heatmap-container
  el.innerHTML = html;
}

// ===== License plates table =====
function renderPlates(plates) {
  const tbody = $('#platesBody');
  if (!tbody) return;

  if (!plates || !plates.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="table-empty">No plates recorded</td></tr>';
    return;
  }

  tbody.innerHTML = plates.map((p) => `
    <tr>
      <td><span class="alert-plate">${esc(p.plate)}</span></td>
      <td class="col-center col-bold">${p.count}</td>
      <td class="col-time">${p.last_seen ? p.last_seen.replace('T', ' ').slice(0, 16) : '—'}</td>
    </tr>
  `).join('');
}

// ===== Recent events table =====
function renderEvents(events) {
  const tbody = $('#eventsBody');
  if (!tbody) return;

  if (!events || !events.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="table-empty">No events recorded</td></tr>';
    return;
  }

  tbody.innerHTML = events.map((e) => {
    const t      = e.timestamp.replace('T', ' ').slice(0, 19);
    const plates = (e.plates || []).map((p) => `<span class="alert-plate">${esc(p)}</span>`).join(' ');
    const snap   = e.snapshot
      ? `<a href="/api/snapshot/${esc(e.snapshot)}" target="_blank" class="snap-link">VIEW</a>`
      : '<span style="color:var(--text-faint)">—</span>';
    return `
      <tr>
        <td class="col-time">${t}</td>
        <td>${esc(e.cam_name)}</td>
        <td><span class="classes-text">${esc(e.classes) || '—'}</span> ${plates}</td>
        <td class="col-center">${snap}</td>
      </tr>
    `;
  }).join('');
}

// ===== Helpers =====
function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function drawEmpty(canvas, msg) {
  const ctx2d = canvas.getContext('2d');
  const w = canvas.offsetWidth || 200;
  const h = canvas.offsetHeight || 160;
  canvas.width  = w;
  canvas.height = h;
  ctx2d.clearRect(0, 0, w, h);
  ctx2d.fillStyle = '#4f5868';
  ctx2d.font = '11px "JetBrains Mono", monospace';
  ctx2d.textAlign = 'center';
  ctx2d.fillText(msg, w / 2, h / 2);
}

// ===== Bootstrap =====
loadAnalytics(currentDays);
setInterval(() => loadAnalytics(currentDays), 30000);
