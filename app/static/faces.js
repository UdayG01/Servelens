// CCTV Intelligence — faces page logic

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const toast = $('#toast');
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

$('#faceImagesInput').addEventListener('change', () => {
  const files = $('#faceImagesInput').files;
  $('#faceFileLabel').textContent = files.length
    ? `${files.length} image${files.length > 1 ? 's' : ''} selected`
    : 'Choose images…';
});

let registeredFacesData = [];

async function loadFaceList() {
  const listEl = $('#faceList');
  listEl.innerHTML = '<span class="face-list-empty">Loading…</span>';
  try {
    const r = await fetch('/api/faces/list');
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Failed to reach DeepStack');
    registeredFacesData = data.faces || [];
    
    // Trigger loadRecentFaces so dropdown gets updated with the registered labels
    loadRecentFaces();

    if (!registeredFacesData.length) {
      listEl.innerHTML = '<span class="face-list-empty">No registered faces yet.</span>';
      return;
    }
    listEl.innerHTML = '';
    for (const name of registeredFacesData) {
      const item = document.createElement('div');
      item.className = 'face-item';
      item.innerHTML = `
        <span class="face-item-name">${name}</span>
        <button class="face-del-btn" data-name="${name}">Delete</button>
      `;
      item.querySelector('[data-name]').addEventListener('click', () => deleteFace(name));
      listEl.appendChild(item);
    }
  } catch (e) {
    listEl.innerHTML = `<span class="face-list-empty face-error">Error: ${e.message}</span>`;
  }
}

async function deleteFace(name) {
  if (!confirm(`Delete face profile for "${name}"?`)) return;
  try {
    const r = await fetch(`/api/faces/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Delete failed');
    showToast(`Deleted: ${name}`);
    loadFaceList();
  } catch (e) {
    showToast('Delete failed: ' + e.message, true);
  }
}

$('#faceRegisterBtn').addEventListener('click', async () => {
  const name = $('#faceNameInput').value.trim();
  const files = $('#faceImagesInput').files;
  const statusEl = $('#faceRegisterStatus');

  if (!name) { showToast('Enter a person name', true); return; }
  if (!files.length) { showToast('Select at least one image', true); return; }

  statusEl.textContent = 'Registering…';
  statusEl.className = 'face-status';

  const fd = new FormData();
  fd.append('name', name);
  for (const f of files) fd.append('images', f);

  try {
    const r = await fetch('/api/faces/register', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Registration failed');
    const ok = data.results.filter(x => x.success).length;
    const fail = data.results.length - ok;
    statusEl.textContent = `Registered ${ok} image(s) for "${name}"${fail ? ` (${fail} failed)` : ''}.`;
    statusEl.className = 'face-status face-status-ok';
    $('#faceNameInput').value = '';
    $('#faceImagesInput').value = '';
    $('#faceFileLabel').textContent = 'Choose images…';
    loadFaceList();
  } catch (e) {
    statusEl.textContent = 'Error: ' + e.message;
    statusEl.className = 'face-status face-status-error';
  }
});

$('#faceListRefreshBtn').addEventListener('click', loadFaceList);

// ===== Recent Faces Logic =====
let recentFacesData = [];
const selectedRecentFiles = new Set();

async function loadRecentFaces() {
  const listEl = $('#recentFaceList');
  const filterEl = $('#recentFaceFilter');
  listEl.innerHTML = '<span class="face-list-empty">Loading…</span>';
  try {
    const r = await fetch('/api/faces/recent');
    const data = await r.json();
    recentFacesData = data.recent || [];
    
    // Update filter dropdown with registered labels + recent labels
    const currentFilter = filterEl.value;
    const labels = new Set(recentFacesData.map(f => f.label));
    registeredFacesData.forEach(l => labels.add(l));
    labels.add("Unknown");

    filterEl.innerHTML = '<option value="all">All Labels</option>';
    if (labels.has("Unknown")) filterEl.innerHTML += '<option value="Unknown">Unknown</option>';
    for (const lbl of Array.from(labels).sort()) {
      if (lbl !== "Unknown") filterEl.innerHTML += `<option value="${lbl}">${lbl}</option>`;
    }
    if (labels.has(currentFilter) || currentFilter === "all") filterEl.value = currentFilter;
    else filterEl.value = "all";

    renderRecentFaces();
  } catch (e) {
    listEl.innerHTML = `<span class="face-list-empty face-error">Error: ${e.message}</span>`;
  }
}

function renderRecentFaces() {
  const listEl = $('#recentFaceList');
  const filter = $('#recentFaceFilter').value;
  
  const filtered = filter === "all" ? recentFacesData : recentFacesData.filter(f => f.label === filter);
  
  if (!filtered.length) {
    listEl.innerHTML = '<span class="face-list-empty">No recent faces found.</span>';
    return;
  }
  
  listEl.innerHTML = '';
  for (const f of filtered) {
    const el = document.createElement('div');
    el.className = 'recent-face-card';
    if (selectedRecentFiles.has(f.filename)) el.classList.add('selected');
    
    el.innerHTML = `
      <img src="/api/faces/recent/${f.filename}" loading="lazy" />
      <div class="recent-face-label">${f.label}</div>
    `;
    
    el.addEventListener('click', () => {
      if (selectedRecentFiles.has(f.filename)) {
        selectedRecentFiles.delete(f.filename);
        el.classList.remove('selected');
      } else {
        selectedRecentFiles.add(f.filename);
        el.classList.add('selected');
      }
    });
    listEl.appendChild(el);
  }
}

$('#recentFaceFilter').addEventListener('change', renderRecentFaces);
$('#recentFaceRefreshBtn').addEventListener('click', loadRecentFaces);

$('#recentFaceTrainBtn').addEventListener('click', async () => {
  const name = $('#recentFaceNameInput').value.trim();
  if (!name) { showToast('Enter a person name', true); return; }
  if (selectedRecentFiles.size === 0) { showToast('Select at least one face', true); return; }

  const btn = $('#recentFaceTrainBtn');
  const prevText = btn.textContent;
  btn.textContent = 'Training…';
  btn.disabled = true;

  const fd = new FormData();
  fd.append('name', name);
  fd.append('recent_filenames', JSON.stringify(Array.from(selectedRecentFiles)));

  try {
    const r = await fetch('/api/faces/register', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Registration failed');
    const ok = data.results.filter(x => x.success).length;
    const fail = data.results.length - ok;
    
    showToast(`Trained ${ok} face(s) as "${name}"${fail ? ` (${fail} failed)` : ''}`);
    $('#recentFaceNameInput').value = '';
    selectedRecentFiles.clear();
    loadFaceList();
  } catch (e) {
    showToast('Train error: ' + e.message, true);
  } finally {
    btn.textContent = prevText;
    btn.disabled = false;
  }
});

$('#recentFaceDeleteBtn').addEventListener('click', async () => {
  if (selectedRecentFiles.size === 0) { showToast('Select at least one face to delete', true); return; }
  if (!confirm(`Delete ${selectedRecentFiles.size} selected image(s)?`)) return;

  const btn = $('#recentFaceDeleteBtn');
  const prevText = btn.textContent;
  btn.textContent = 'Deleting…';
  btn.disabled = true;

  const fd = new FormData();
  fd.append('filenames', JSON.stringify(Array.from(selectedRecentFiles)));

  try {
    const r = await fetch('/api/faces/recent/delete', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Delete failed');
    
    showToast(`Deleted ${data.deleted} image(s)`);
    selectedRecentFiles.clear();
    loadRecentFaces();
  } catch (e) {
    showToast('Delete error: ' + e.message, true);
  } finally {
    btn.textContent = prevText;
    btn.disabled = false;
  }
});

loadFaceList();
