// CCTV Intelligence — frontend logic

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const grid       = $('#cameraGrid');
const alertsList = $('#alertsList');
const toast      = $('#toast');

let lastAlertSig = "";
const tileEls = new Map(); // cam_id -> { tile, dot, status, fps, recBtn }

function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.classList.toggle('error', !!isError);
  toast.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.remove('show'), 3500);
}

function tickClock() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  $('#clock').textContent =
    `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}  ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
setInterval(tickClock, 1000);
tickClock();

function buildTile(cam) {
  const tile = document.createElement('div');
  tile.className = 'tile';
  tile.dataset.id = cam.id;
  const faceBtnHtml = cam.face_recognition
    ? `<button class="face-btn" data-facecam="${cam.id}">⊙ FACES</button>`
    : '';
  const countBtnHtml = cam.supports_count
    ? `<button class="count-btn" data-countcam="${cam.id}">⊕ COUNT</button>`
    : '';
  tile.innerHTML = `
    <div class="tile-head">
      <span class="tile-id">${cam.id.toUpperCase()}</span>
      <span class="tile-name">${cam.name}</span>
      <span class="tile-status">
        <span class="dot connecting"></span>
        <span class="status-text">connecting</span>
      </span>
    </div>
    <div class="tile-video">
      <div class="placeholder">CONNECTING…</div>
      <img alt="" />
    </div>
    <div class="tile-foot">
      <span class="models">${(cam.models || []).join(' · ').toUpperCase() || 'NO MODEL'}</span>
      <span class="fps">-- FPS</span>
      ${faceBtnHtml}
      ${countBtnHtml}
      <button class="rec-btn" data-rec>● REC</button>
    </div>
  `;
  grid.appendChild(tile);

  const img = tile.querySelector('img');
  // Start MJPEG stream — the browser holds this connection open
  img.src = `/stream/${cam.id}?t=${Date.now()}`;
  img.onload = () => {
    const ph = tile.querySelector('.placeholder');
    if (ph) ph.style.display = 'none';
  };
  img.onerror = () => {
    const ph = tile.querySelector('.placeholder');
    if (ph) { ph.style.display = 'flex'; ph.textContent = 'STREAM ERROR'; }
  };

  if (cam.face_recognition) {
    tile.querySelector('[data-facecam]').addEventListener('click', () => {
      window.location.href = '/faces';
    });
  }

  if (cam.supports_count) {
    const countBtn = tile.querySelector('[data-countcam]');
    countBtn.addEventListener('click', () => toggleCount(cam.id, countBtn));
  }

  const recBtn = tile.querySelector('[data-rec]');
  recBtn.addEventListener('click', async () => {
    try {
      const r = await fetch(`/api/record/${cam.id}`, { method: 'POST' });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'failed');
      if (data.recording) {
        recBtn.classList.add('active');
        recBtn.textContent = '■ STOP';
        showToast(`Recording: ${data.path.split(/[\\/]/).pop()}`);
      } else {
        recBtn.classList.remove('active');
        recBtn.textContent = '● REC';
        showToast('Recording stopped');
      }
    } catch (e) {
      showToast('Recording error: ' + e.message, true);
    }
  });

  tileEls.set(cam.id, {
    tile,
    dot: tile.querySelector('.dot'),
    statusText: tile.querySelector('.status-text'),
    fps: tile.querySelector('.fps'),
    recBtn,
  });
}

async function refreshCameras() {
  try {
    const r = await fetch('/api/cameras');
    const data = await r.json();
    const cams = data.cameras || [];
    $('#cameraCount').textContent = `${cams.length} camera${cams.length === 1 ? '' : 's'}`;

    for (const cam of cams) {
      if (!tileEls.has(cam.id)) {
        buildTile(cam);
      }
      const els = tileEls.get(cam.id);
      const status = cam.status || 'idle';
      const cls = status.startsWith('live') ? 'live'
                : status.includes('connect') ? 'connecting'
                : 'disconnected';
      els.dot.className = 'dot ' + cls;
      els.statusText.textContent = status;
      els.fps.textContent = `${cam.fps.toFixed(1)} FPS`;
      els.recBtn.classList.toggle('active', !!cam.recording);
      els.recBtn.textContent = cam.recording ? '■ STOP' : '● REC';
    }
  } catch (e) {
    console.error('refreshCameras failed', e);
  }
}

function alertSignature(items) {
  if (!items.length) return "";
  return items[0].timestamp + '|' + items[0].cam_id;
}

function flashTile(camId) {
  const els = tileEls.get(camId);
  if (!els) return;
  els.tile.classList.remove('alert-flash');
  void els.tile.offsetWidth; // force reflow
  els.tile.classList.add('alert-flash');
}

async function refreshAlerts() {
  try {
    const r = await fetch('/api/alerts?limit=80');
    const data = await r.json();
    const items = data.alerts || [];
    $('#alertCount').textContent = items.length;

    if (!items.length) {
      alertsList.innerHTML = '<div class="empty">No alerts yet.</div>';
      return;
    }

    // Detect new alert -> flash tile
    const sig = alertSignature(items);
    if (sig && sig !== lastAlertSig && lastAlertSig !== "") {
      flashTile(items[0].cam_id);
    }
    lastAlertSig = sig;

    alertsList.innerHTML = '';
    for (const a of items) {
      const el = document.createElement('div');
      el.className = 'alert-item';
      const t = a.timestamp.replace('T', ' ').slice(11, 19); // HH:MM:SS
      const plates = (a.plates && a.plates.length)
        ? `<span class="alert-plate">${a.plates.join(' · ')}</span>` : '';
      const names = (a.names && a.names.length)
        ? `<span class="alert-name">${a.names.join(' · ')}</span>` : '';
      const thumb = (a.snapshot && a.snapshot.trim())
        ? `<img src="/api/snapshot/${a.snapshot}" alt="" loading="lazy"/>`
        : '';
      el.innerHTML = `
        <div class="alert-thumb">${thumb}</div>
        <div class="alert-body">
          <div class="alert-row1">
            <span class="alert-cam">${a.cam_name}</span>
            <span class="alert-time">${t}</span>
          </div>
          <div class="alert-classes">${a.classes || '—'}</div>
          ${plates}
          ${names}
        </div>
      `;
      el.addEventListener('click', () => {
        // ✅ FIX: Only open lightbox if snapshot exists and is non-empty
        if (a.snapshot && a.snapshot.trim()) {
          openLightbox(a.snapshot, a);
        } else {
          showToast('No snapshot available for this alert', true);
        }
      });
      alertsList.appendChild(el);
    }
  } catch (e) {
    console.error('refreshAlerts failed', e);
  }
}

function openLightbox(filename, alert) {
  // ✅ FIX: Guard against missing filename
  if (!filename || !filename.trim()) {
    showToast('No snapshot available', true);
    return;
  }

  const img = $('#lbImg');
  const lightbox = $('#lightbox');

  // ✅ FIX: Reset image first to avoid stale image flash
  img.src = '';

  // ✅ FIX: Auto-close lightbox if snapshot fails to load
  img.onerror = () => {
    lightbox.hidden = true;
    showToast('Failed to load snapshot', true);
  };

  // ✅ FIX: Only show lightbox after image successfully loads
  img.onload = () => {
    lightbox.hidden = false;
  };

  $('#lbMeta').textContent =
    `${alert.cam_name} · ${alert.timestamp} · ${alert.classes}` +
    (alert.plates && alert.plates.length ? ` · plate: ${alert.plates.join(', ')}` : '');

  // Trigger the load — handlers above will show/hide based on result
  img.src = `/api/snapshot/${filename}`;
}

function closeLightbox() {
  const lightbox = $('#lightbox');
  const img = $('#lbImg');
  lightbox.hidden = true;
  img.src = ''; // ✅ FIX: Clear src on close to free memory & cancel pending loads
}

$('#lbClose').addEventListener('click', closeLightbox);
$('#lightbox').addEventListener('click', (e) => {
  if (e.target.id === 'lightbox') closeLightbox();
});

// ✅ FIX: Allow ESC key to close lightbox
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#lightbox').hidden) {
    closeLightbox();
  }
});

$('#btnTestEmail').addEventListener('click', async () => {
  showToast('Sending test email…');
  try {
    const r = await fetch('/api/test-email', { method: 'POST' });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'failed');
    showToast('Test email sent ✓');
  } catch (e) {
    showToast('Email failed: ' + e.message, true);
  }
});

$('#btnRefresh').addEventListener('click', () => {
  refreshCameras();
  refreshAlerts();
});

// Initial + polling
refreshCameras();
refreshAlerts();
setInterval(refreshCameras, 2500);
setInterval(refreshAlerts, 2000);

// ===== People Count =====

const _countActive = new Map();
const _countIntervals = new Map();

function toggleCount(camId, btn) {
  if (_countActive.get(camId)) {
    clearInterval(_countIntervals.get(camId));
    _countActive.set(camId, false);
    _countIntervals.delete(camId);
    btn.textContent = '⊕ COUNT';
    btn.classList.remove('active');
  } else {
    _countActive.set(camId, true);
    btn.classList.add('active');
    _pollCount(camId, btn);
    _countIntervals.set(camId, setInterval(() => _pollCount(camId, btn), 2000));
  }
}

async function _pollCount(camId, btn) {
  try {
    const r = await fetch(`/api/count/${camId}`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    const n = data.counts?.person ?? data.total ?? 0;
    btn.textContent = `⊕ ${n} ${n === 1 ? 'PERSON' : 'PEOPLE'}`;
  } catch (_) {
    btn.textContent = '⊕ COUNT';
  }
}
