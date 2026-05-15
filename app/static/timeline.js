// Camera Detail Page — Live stream, Event Timeline, Video Playback

const $ = (sel) => document.querySelector(sel);

const toast      = $('#toast');
const liveImg    = $('#liveImg');
const recPlayer  = $('#recPlayer');
const placeholder = $('#videoPlaceholder');

// ===== Toast =====
function showToast(msg, isErr = false) {
  toast.textContent = msg;
  toast.classList.toggle('error', !!isErr);
  toast.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.remove('show'), 3500);
}

// ===== Clock =====
function tickClock() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  $('#clock').textContent =
    `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}  ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
setInterval(tickClock, 1000);
tickClock();

// ===== Live stream =====
liveImg.src = `/stream/${CAM_ID}?t=${Date.now()}`;
liveImg.onload = () => { placeholder.style.display = 'none'; };
liveImg.onerror = () => { placeholder.textContent = 'STREAM ERROR'; };

// ===== Mode toggle (Live / Playback) =====
let currentMode = 'live';

function setMode(m) {
  currentMode = m;
  if (m === 'live') {
    liveImg.style.display = 'block';
    recPlayer.style.display = 'none';
    placeholder.style.display = 'none';
    $('#btnLive').classList.add('active');
    $('#btnPlayback').classList.remove('active');
    $('#nowPlaying').textContent = '';
    // Re-attach stream if src was cleared
    if (!liveImg.getAttribute('src') || !liveImg.getAttribute('src').includes('/stream/')) {
      liveImg.src = `/stream/${CAM_ID}?t=${Date.now()}`;
    }
  } else {
    liveImg.style.display = 'none';
    recPlayer.style.display = 'block';
    $('#btnLive').classList.remove('active');
    $('#btnPlayback').classList.add('active');
    if (!recPlayer.src || recPlayer.src === window.location.href) {
      placeholder.style.display = 'flex';
      placeholder.textContent = 'SELECT AN EVENT ON THE TIMELINE';
      $('#nowPlaying').textContent = 'Click a red marker on the timeline';
    }
  }
}

$('#btnLive').addEventListener('click', () => setMode('live'));
$('#btnPlayback').addEventListener('click', () => setMode('playback'));

// ===== Camera status polling =====
async function pollStatus() {
  try {
    const r = await fetch('/api/cameras');
    const data = await r.json();
    const cam = (data.cameras || []).find(c => c.id === CAM_ID);
    if (!cam) return;
    const dot  = $('#statusDot');
    const txt  = $('#statusText');
    const st   = cam.status || 'idle';
    const cls  = st.startsWith('live') ? 'live'
               : st.includes('connect') ? 'connecting'
               : 'disconnected';
    dot.className = 'dot ' + cls;
    txt.textContent = st;
  } catch (_) {}
}
setInterval(pollStatus, 3000);
pollStatus();

// ===== Data state =====
let recordings  = [];
let events      = [];
let tlMinMs     = 0;
let tlMaxMs     = 0;
let tlZoom      = 1.0;
let activeMarker = null;

const TL_PX_PER_SEC_BASE = 3;    // pixels per second at zoom 1x
const TL_MIN_WIDTH_PX    = 900;  // minimum track width

// ===== Load data from API =====
async function loadData() {
  try {
    const [rr, er] = await Promise.all([
      fetch(`/api/recordings/${CAM_ID}`),
      fetch(`/api/events/${CAM_ID}?limit=500`),
    ]);
    const rd = await rr.json();
    const ed = await er.json();
    recordings = rd.recordings || [];
    events     = ed.events || [];
    buildEventsList();
    buildTimeline();
  } catch (e) {
    console.error('loadData failed', e);
    showToast('Could not load recordings/events', true);
  }
}

// ===== Events sidebar =====
function buildEventsList() {
  const list = $('#evtList');
  $('#evtCount').textContent = events.length;

  if (!events.length) {
    list.innerHTML = '<div class="empty">No events recorded.</div>';
    return;
  }

  list.innerHTML = '';
  for (const evt of events) {
    const el  = document.createElement('div');
    el.className = 'alert-item';
    const t   = evt.timestamp.replace('T', ' ').slice(11, 19);
    const dt  = evt.timestamp.slice(0, 10);
    const plates = evt.plates && evt.plates.length
      ? `<span class="alert-plate">${evt.plates.join(' · ')}</span>` : '';
    const names = evt.names && evt.names.length
      ? `<span class="alert-name">${evt.names.join(' · ')}</span>` : '';
    const thumb = evt.snapshot && evt.snapshot.trim()
      ? `<img src="/api/snapshot/${evt.snapshot}" alt="" loading="lazy"/>` : '';

    el.innerHTML = `
      <div class="alert-thumb">${thumb}</div>
      <div class="alert-body">
        <div class="alert-row1">
          <span class="alert-cam">${dt}</span>
          <span class="alert-time">${t}</span>
        </div>
        <div class="alert-classes">${evt.classes || '—'}</div>
        ${plates}${names}
      </div>
    `;
    el.addEventListener('click', () => jumpToEvent(evt));
    list.appendChild(el);
  }
}

// ===== Find recording that covers an event =====
function findRecordingForEvent(evt) {
  const evtMs = new Date(evt.timestamp).getTime();
  // 5-second tolerance on both ends to account for clock skew
  for (const rec of recordings) {
    if (!rec.start_time) continue;
    const startMs = new Date(rec.start_time).getTime();
    const endMs   = startMs + rec.duration * 1000;
    if (evtMs >= startMs - 5000 && evtMs <= endMs + 5000) {
      const seekTime = Math.max(0, (evtMs - startMs) / 1000 - 2); // 2s before event
      return { recording: rec, seekTime };
    }
  }
  return null;
}

// ===== Jump to event (from sidebar click or marker click) =====
function jumpToEvent(evt) {
  const match = findRecordingForEvent(evt);
  if (match) {
    loadRecording(match.recording, match.seekTime, evt);
  } else {
    showToast('No recording found for this event — showing snapshot only');
  }
}

// ===== Load a recording into the player and seek =====
function loadRecording(rec, seekTime, evt = null) {
  setMode('playback');
  placeholder.style.display = 'none';

  const label = rec.filename.replace(/_/g, ' ').replace('.mp4', '') +
                (seekTime > 0 ? ` @${Math.round(seekTime)}s` : '');
  $('#nowPlaying').textContent = label;

  // Highlight active segment on timeline
  if (activeMarker) activeMarker.classList.remove('tl-marker-active');
  if (evt) {
    const ms  = new Date(evt.timestamp).getTime();
    const m   = document.querySelector(`.tl-marker[data-ts="${ms}"]`);
    if (m) { m.classList.add('tl-marker-active'); activeMarker = m; }
  }
  // Highlight active segment
  document.querySelectorAll('.tl-segment').forEach(s => s.classList.remove('tl-segment-active'));
  const seg = document.querySelector(`.tl-segment[data-file="${rec.filename}"]`);
  if (seg) seg.classList.add('tl-segment-active');

  // If same file already loaded — just seek
  if (recPlayer.dataset.currentFile === rec.filename) {
    recPlayer.currentTime = seekTime;
    recPlayer.play().catch(() => {});
    updatePlayhead(rec, seekTime);
    return;
  }

  recPlayer.dataset.currentFile = rec.filename;
  recPlayer.src = `/recordings/${encodeURIComponent(rec.filename)}`;
  recPlayer.load();

  const onLoaded = () => {
    recPlayer.removeEventListener('loadedmetadata', onLoaded);
    recPlayer.currentTime = seekTime;
    recPlayer.play().catch(() => {});
    updatePlayhead(rec, seekTime);
  };
  recPlayer.addEventListener('loadedmetadata', onLoaded);

  recPlayer.addEventListener('timeupdate', () => updatePlayhead(rec, recPlayer.currentTime));
  recPlayer.addEventListener('error', () => {
    showToast('Could not play recording — codec may not be supported by browser', true);
    placeholder.style.display = 'flex';
    placeholder.textContent = 'PLAYBACK ERROR';
  });
}

// ===== Build / refresh timeline =====
function buildTimeline() {
  const tlOuter = $('#tlOuter');
  const tlEmpty = $('#tlEmpty');

  if (!recordings.length && !events.length) {
    tlOuter.style.display = 'none';
    tlEmpty.style.display = 'block';
    return;
  }

  tlOuter.style.display = 'block';
  tlEmpty.style.display = 'none';

  // Compute time bounds from recordings + events
  const allMs = [];
  for (const r of recordings) {
    if (r.start_time) {
      const s = new Date(r.start_time).getTime();
      allMs.push(s, s + r.duration * 1000);
    }
  }
  for (const e of events) {
    if (e.timestamp) allMs.push(new Date(e.timestamp).getTime());
  }

  if (!allMs.length) {
    tlOuter.style.display = 'none';
    tlEmpty.style.display = 'block';
    return;
  }

  const pad   = 60 * 1000; // 1-minute padding on each side
  tlMinMs = Math.min(...allMs) - pad;
  tlMaxMs = Math.max(...allMs) + pad;

  const fmt = (ms) => {
    const d = new Date(ms);
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };
  $('#tlRange').textContent = `${fmt(tlMinMs)} → ${fmt(tlMaxMs)}`;

  renderTimeline();
}

// ===== Render timeline (called on data load + zoom change) =====
function renderTimeline() {
  const tlTrack    = $('#tlTrack');
  const tlAxis     = $('#tlAxis');
  const tlPlayhead = $('#tlPlayhead');

  const totalSec   = (tlMaxMs - tlMinMs) / 1000;
  const pxPerSec   = TL_PX_PER_SEC_BASE * tlZoom;
  const totalWidth = Math.max(TL_MIN_WIDTH_PX, Math.ceil(totalSec * pxPerSec));

  tlTrack.style.width = totalWidth + 'px';
  tlAxis.style.width  = totalWidth + 'px';

  // Convert timestamp (ms) to pixel position
  const px = (ms) => Math.round(((ms - tlMinMs) / (tlMaxMs - tlMinMs)) * totalWidth);

  // Clear track (keep playhead)
  Array.from(tlTrack.children).forEach(child => {
    if (child.id !== 'tlPlayhead') child.remove();
  });
  tlAxis.innerHTML = '';

  // ---- Recording segments ----
  for (const rec of recordings) {
    if (!rec.start_time) continue;
    const startMs = new Date(rec.start_time).getTime();
    const endMs   = startMs + rec.duration * 1000;
    const left    = px(startMs);
    const width   = Math.max(3, px(endMs) - px(startMs));

    const seg = document.createElement('div');
    seg.className = `tl-segment tl-segment-${rec.type}`;
    seg.dataset.file = rec.filename;
    seg.style.left  = left + 'px';
    seg.style.width = width + 'px';
    seg.title = `${rec.filename}  (${rec.duration.toFixed(1)}s · ${rec.size_mb} MB)`;
    seg.addEventListener('click', () => loadRecording(rec, 0));
    tlTrack.appendChild(seg);
  }

  // ---- Event markers (red dots) ----
  for (const evt of events) {
    if (!evt.timestamp) continue;
    const evtMs = new Date(evt.timestamp).getTime();
    const left  = px(evtMs);

    const marker = document.createElement('div');
    marker.className = 'tl-marker';
    marker.style.left = left + 'px';
    marker.dataset.ts = String(evtMs);

    marker.addEventListener('mouseenter', (e) => showTooltip(e, evt));
    marker.addEventListener('mouseleave', hideTooltip);
    marker.addEventListener('click', () => {
      jumpToEvent(evt);
      scrollToPosition(left);
    });

    tlTrack.appendChild(marker);
  }

  // ---- Time axis labels ----
  const intervalSec = pickLabelInterval(totalSec, totalWidth);
  const firstMs     = Math.ceil(tlMinMs / (intervalSec * 1000)) * (intervalSec * 1000);

  for (let ms = firstMs; ms <= tlMaxMs; ms += intervalSec * 1000) {
    const left = px(ms);
    const d    = new Date(ms);
    const p    = (n) => String(n).padStart(2, '0');

    // Choose label format based on interval
    let labelText;
    if (intervalSec >= 86400) {
      labelText = `${d.getMonth()+1}/${d.getDate()}`;
    } else if (intervalSec >= 3600) {
      labelText = `${p(d.getHours())}:00`;
    } else {
      labelText = `${p(d.getHours())}:${p(d.getMinutes())}`;
    }

    const lbl = document.createElement('div');
    lbl.className = 'tl-label';
    lbl.style.left = left + 'px';
    lbl.textContent = labelText;
    tlAxis.appendChild(lbl);

    const tick = document.createElement('div');
    tick.className = 'tl-tick';
    tick.style.left = left + 'px';
    tlAxis.appendChild(tick);
  }

  // Re-position playhead if we have an active recording
  if (recPlayer.dataset.currentFile) {
    const rec = recordings.find(r => r.filename === recPlayer.dataset.currentFile);
    if (rec) updatePlayhead(rec, recPlayer.currentTime || 0);
  }
}

// Pick a human-friendly label interval so labels are at least 60px apart
function pickLabelInterval(totalSec, totalWidthPx) {
  const minPxPerLabel = 60;
  const candidates = [30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 43200, 86400];
  for (const c of candidates) {
    const numLabels = totalSec / c;
    if (numLabels === 0) continue;
    if ((totalWidthPx / numLabels) >= minPxPerLabel) return c;
  }
  return candidates[candidates.length - 1];
}

// ===== Update amber playhead =====
function updatePlayhead(rec, seekTime) {
  const tlPlayhead = $('#tlPlayhead');
  if (!rec || !rec.start_time || !tlMinMs) {
    tlPlayhead.style.display = 'none';
    return;
  }
  const totalSec   = (tlMaxMs - tlMinMs) / 1000;
  const pxPerSec   = TL_PX_PER_SEC_BASE * tlZoom;
  const totalWidth = Math.max(TL_MIN_WIDTH_PX, Math.ceil(totalSec * pxPerSec));

  const evtMs = new Date(rec.start_time).getTime() + seekTime * 1000;
  const left  = Math.round(((evtMs - tlMinMs) / (tlMaxMs - tlMinMs)) * totalWidth);

  tlPlayhead.style.display = 'block';
  tlPlayhead.style.left    = left + 'px';
}

// Smoothly scroll the timeline outer container to center on a pixel position
function scrollToPosition(leftPx) {
  const outer = $('#tlOuter');
  const target = leftPx - outer.clientWidth / 2;
  outer.scrollTo({ left: Math.max(0, target), behavior: 'smooth' });
}

// ===== Tooltip =====
const tooltip = $('#tlTooltip');

function showTooltip(e, evt) {
  const t     = evt.timestamp.replace('T', ' ');
  const lines = [t, evt.classes || ''];
  if (evt.plates && evt.plates.length) lines.push('Plate: ' + evt.plates.join(', '));
  if (evt.names  && evt.names.length)  lines.push('Face: '  + evt.names.join(', '));
  tooltip.innerHTML = lines.filter(Boolean).join('<br>');
  tooltip.style.display = 'block';
  moveTooltip(e);
}

function moveTooltip(e) {
  const x = e.clientX + 14;
  const y = e.clientY - 50;
  tooltip.style.left = Math.min(x, window.innerWidth  - 290) + 'px';
  tooltip.style.top  = Math.max(8, y) + 'px';
}

function hideTooltip() {
  tooltip.style.display = 'none';
}

document.addEventListener('mousemove', (e) => {
  if (tooltip.style.display === 'block') moveTooltip(e);
});

// ===== Zoom controls =====
$('#btnZoomIn').addEventListener('click', () => {
  tlZoom = Math.min(tlZoom * 2, 128);
  renderTimeline();
});
$('#btnZoomOut').addEventListener('click', () => {
  tlZoom = Math.max(tlZoom / 2, 0.0625);
  renderTimeline();
});

// ===== Scroll buttons =====
const SCROLL_STEP = 300;
$('#btnScrollLeft').addEventListener('click',  () => {
  $('#tlOuter').scrollBy({ left: -SCROLL_STEP, behavior: 'smooth' });
});
$('#btnScrollRight').addEventListener('click', () => {
  $('#tlOuter').scrollBy({ left: SCROLL_STEP, behavior: 'smooth' });
});

// ===== Init =====
loadData();
// Refresh data every 30s to pick up new recordings/events
setInterval(loadData, 30000);
