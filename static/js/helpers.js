/* ─── HELPERS ─── */
async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) { const t = await res.text(); throw new Error(t || 'API error'); }
  return res.json();
}

function formatUptime(total) {
  const h = String(Math.floor(total / 3600)).padStart(2, '0');
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
  const s = String(total % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function escapeHtml(v) {
  return String(v || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function providerTitle(p) {
  const map = { ollama_cloud: '☁️ Ollama Cloud', nvidia: '🟢 NVIDIA', openrouter: '🔀 OpenRouter', google: '🔵 Google', local: '💻 Local' };
  if (map[p]) return map[p];
  return p.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function providerEmoji(p) {
  const map = { ollama_cloud: '☁️', nvidia: '🟢', openrouter: '🔀', google: '🔵', local: '💻' };
  return map[p] || '🔌';
}

function defaultKeysState() {
  return keyProviders.reduce((acc, p) => { acc[p] = []; return acc; }, {});
}

function setKeysStatus(msg, level = 'info') {
  const el = document.getElementById('keysStatus');
  if (!el) return;
  el.style.color = level === 'error' ? 'var(--red)' : level === 'success' ? 'var(--green)' : 'var(--text-dim)';
  el.innerText = msg;
}

function setConfigStatus(msg, level = 'info') {
  const el = document.getElementById('configStatus');
  if (!el) return;
  el.style.color = level === 'error' ? 'var(--red)' : level === 'success' ? 'var(--green)' : 'var(--text-dim)';
  el.innerText = msg;
}

function applyConfigEditorMode(mode) {
  configEditorMode = mode;
  const editor = document.getElementById('configEditor');
  const guard = document.getElementById('configGuard');
  const saveBtn = document.getElementById('saveConfigBtn');
  const isLocked = mode === 'locked';
  const isEdit = mode === 'edit';

  editor.readOnly = !isEdit;
  editor.classList.toggle('is-protected', isLocked);
  guard.classList.toggle('hidden', !isLocked);
  saveBtn.disabled = !isEdit;

  if (isLocked) setConfigStatus('Éditeur verrouillé. Choisissez Voir ou Modifier.', 'info');
  else if (isEdit) setConfigStatus('Mode édition actif. Les clés sont visibles.', 'error');
  else setConfigStatus('Mode lecture seule actif.', 'success');
}

function unlockConfigEditor(mode) {
  const warning = "⚠️ Avertissement sécurité:\n\nLe fichier YAML contient des clés API en clair.\nEn continuant, elles seront visibles à l'écran.\n\nContinuer ?";
  if (!confirm(warning)) return;
  applyConfigEditorMode(mode === 'edit' ? 'edit' : 'view');
}

function lockConfigEditor() {
  applyConfigEditorMode('locked');
}

function setKeyTestCenterStatus(msg, level = 'info') {
  const el = document.getElementById('keyTestCenterStatus');
  if (!el) return;
  el.style.color = level === 'error' ? 'var(--red)' : level === 'success' ? 'var(--green)' : level === 'warn' ? 'var(--accent)' : 'var(--text-dim)';
  el.innerText = msg;
}

function getCenterStatusBadge(status) {
  if (status === 'ok') return { cls: 'green', text: '✅ OK' };
  if (status === 'quota') return { cls: 'amber', text: '⚠️ Quota' };
  if (status === 'warning') return { cls: 'amber', text: '⚠️ Alerte' };
  if (status === 'invalid') return { cls: 'red', text: '❌ Invalide' };
  if (status === 'network') return { cls: 'red', text: '🌐 Réseau' };
  if (status === 'error') return { cls: 'red', text: '❌ Erreur' };
  if (status === 'testing') return { cls: 'blue', text: '⏳ Test...' };
  return { cls: '', text: '—' };
}

function keyMask(v) {
  if (!v) return '';
  if (v.length <= 8) return '••••••••';
  return `${v.slice(0, 4)}••••${v.slice(-4)}`;
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    if (button) { const p = button.innerText; button.innerText = '✅'; setTimeout(() => button.innerText = p, 1200); }
  } catch {
    if (button) { const p = button.innerText; button.innerText = '❌'; setTimeout(() => button.innerText = p, 1200); }
  }
}

async function copyFrom(id, button) {
  const el = document.getElementById(id);
  await copyText((el?.innerText || '').trim(), button);
}

let welcomeVisible = true;

function toggleWelcome() {
  const banner = document.getElementById('welcomeBanner');
  const btn = document.getElementById('welcomeToggleBtn');
  if (!banner) return;
  welcomeVisible = !welcomeVisible;
  banner.style.display = welcomeVisible ? 'block' : 'none';
  if (btn) btn.title = welcomeVisible ? 'Masquer le panneau de bienvenue' : 'Afficher le panneau de bienvenue';
}

// Keep old function name as alias for any remaining references
function dismissWelcome() { toggleWelcome(); }

async function checkOllama() {
  try {
    const data = await api('/api/ollama/status');
    const card = document.getElementById('ollamaCard');
    if (!card) return;
    if (data.installed) {
      card.style.display = 'none';
    } else {
      card.style.display = 'flex';
    }
  } catch {
    const card = document.getElementById('ollamaCard');
    if (card) card.style.display = 'flex';
  }
}

async function openKeysCenter() {
  showTab('keys');
  await loadKeysCenter();
  await checkOllama();
}

async function installOllama() {
  const btn = document.getElementById('ollamaInstallBtn');
  if (!btn) return;
  btn.innerText = '⏳ Installation...';
  btn.disabled = true;
  try {
    await api('/api/ollama/install', 'POST');
    const poll = setInterval(async () => {
      try {
        const data = await api('/api/ollama/status');
        if (data.installed) {
          clearInterval(poll);
          document.getElementById('ollamaCard').style.display = 'none';
          btn.innerText = '✅ Installé';
        }
      } catch { }
    }, 3000);
  } catch (err) {
    btn.innerText = '⬇ Installer Ollama';
    btn.disabled = false;
  }
}

async function refreshAllCatalogues(btn) {
  btn.disabled = true;
  btn.innerText = '⏳ Rafraîchissement...';
  const st = document.getElementById('catalogueRefreshStatus');
  st.innerText = '';
  try {
    const res = await api('/api/catalogue/refresh', 'POST');
    const r = res.results || {};
    const parts = Object.entries(r).map(([k, v]) => `${k}: ${v >= 0 ? v + ' modèles' : 'erreur'}`);
    st.innerText = '✅ ' + parts.join(' · ');
    // reload current tab
    if (catTab === 'ollama') loadOllamaModels();
    else if (catTab === 'openrouter') loadOpenRouterModels();
    else if (catTab === 'nvidia') loadNvidiaModels();
    else if (catTab === 'local') loadLocalModels();
  } catch (err) {
    st.innerText = '❌ Erreur : ' + err.message;
  }
  btn.disabled = false;
  btn.innerText = '↺ Rafraîchir tous les catalogues';
}

function showCatalogueTimestamp(provider, ts) {
  const st = document.getElementById('catalogueRefreshStatus');
  if (st && ts) {
    const d = new Date(ts);
    st.innerText = `Dernière MAJ : ${d.toLocaleString()}`;
  }
}

function renderModelCard(m, source) {
  const isInstalled = m.installed || false;
  const isCloud = (m.tags || []).includes('cloud') || source === 'openrouter' || source === 'nvidia';
  const sizeLabel = m.size ? formatBytes(m.size) : m.parameter_size || '—';
  const paramSize = m.parameter_size || (m.details || {}).parameter_size || '';
  const family = (m.details || {}).family || '';
  const quant = (m.details || {}).quantization_level || '';

  const tagBadges = (m.tags || []).slice(0, 4).map(t => {
    const colors = { cloud: 'amber', vision: 'blue', tools: 'green', thinking: 'purple', code: 'green' };
    const c = colors[t] || '';
    return `<span class="badge ${c}" style="font-size:10px">${t}</span>`;
  }).join('');

  const extraBadges = [
    paramSize ? `<span class="badge" style="font-size:10px">🧠 ${paramSize}</span>` : '',
    family ? `<span class="badge" style="font-size:10px">🏷 ${family}</span>` : '',
    quant ? `<span class="badge purple" style="font-size:10px">⚙ ${quant}</span>` : '',
    m.downloads ? `<span class="badge" style="font-size:10px">⬇ ${m.downloads >= 1e6 ? (m.downloads / 1e6).toFixed(1) + 'M' : m.downloads >= 1e3 ? (m.downloads / 1e3).toFixed(0) + 'K' : m.downloads}</span>` : '',
  ].filter(Boolean).join('');

  const actionBtn = source === 'local'
    ? `<button class="danger" onclick="event.stopPropagation(); deleteLocalModel('${m.name}')" style="font-size:11px; padding:5px 8px">🗑 Supprimer</button>`
    : isCloud
      ? `<button class="primary" onclick="event.stopPropagation(); addToRotator('${m.name}','${source}')" style="font-size:11px; padding:5px 10px">➕ Ajouter au rotator</button>`
      : isInstalled
        ? `<button onclick="event.stopPropagation(); addToRotator('${m.name}','local')" style="font-size:11px; padding:5px 10px">➕ Ajouter au rotator</button>`
        : `<button class="primary" onclick="event.stopPropagation(); installModel('${m.name}', this)" style="font-size:11px; padding:5px 10px">⬇ Installer</button>`;

  const cardData = encodeURIComponent(JSON.stringify(m));

  return `
      <div id="modelcard-${m.name.replace(/[^a-z0-9]/gi, '-')}" onclick="showModelDetail(decodeURIComponent('${cardData}'), '${source}')" style="
        background:var(--surface); border:1px solid var(--border);
        border-radius:var(--r-lg); padding:16px; cursor:pointer;
        ${isInstalled ? 'border-color:var(--green-bdr);' : ''}
        transition: border-color .2s, transform .15s, box-shadow .15s;
      " onmouseover="this.style.borderColor='var(--border-hi)'; this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,.3)'"
         onmouseout="this.style.borderColor='${isInstalled ? 'var(--green-bdr)' : 'var(--border)'}'; this.style.transform='none'; this.style.boxShadow='none'">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px">
          <div style="font-family:var(--font-mono); font-size:13px; font-weight:600; color:#fff; flex:1; margin-right:8px">${m.name}</div>
          ${isInstalled
      ? '<span class="badge green" style="font-size:10px; flex-shrink:0">✅ Installé</span>'
      : isCloud
        ? '<span class="badge amber" style="font-size:10px; flex-shrink:0">☁️ Cloud</span>'
        : '<span class="badge" style="font-size:10px; flex-shrink:0">⬇ Disponible</span>'
    }
        </div>
        <div style="font-size:12px; color:var(--text-dim); margin-bottom:10px; line-height:1.4">
          ${(m.description || '').slice(0, 120)}${(m.description || '').length > 120 ? '...' : ''}
        </div>
        <div style="display:flex; gap:5px; flex-wrap:wrap; margin-bottom:10px">
          ${tagBadges}
          ${sizeLabel !== '—' ? `<span class="badge" style="font-size:10px">📦 ${sizeLabel}</span>` : ''}
          ${m.context_length ? `<span class="badge" style="font-size:10px">📐 ${formatContext(m.context_length)}</span>` : ''}
          ${extraBadges}
        </div>
        <div id="progress-${m.name.replace(/[^a-z0-9]/gi, '-')}" style="display:none; margin-bottom:10px">
          <div style="font-size:11px; color:var(--text-dim); margin-bottom:4px" id="progress-label-${m.name.replace(/[^a-z0-9]/gi, '-')}">Téléchargement...</div>
          <div class="progress"><span id="progress-bar-${m.name.replace(/[^a-z0-9]/gi, '-')}" style="width:0%"></span></div>
        </div>
        <div style="display:flex; gap:6px; justify-content:flex-end">${actionBtn}</div>
      </div>`;
}

function showModelDetail(jsonStr, source) {
  const m = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr;
  const isInstalled = m.installed || false;
  const isCloud = (m.tags || []).includes('cloud') || source === 'openrouter' || source === 'nvidia';
  const details = m.details || {};
  const sizeLabel = m.size ? formatBytes(m.size) : m.parameter_size || '—';

  document.getElementById('modelDetailTitle').innerText = m.name;

  const infoRows = [
    { label: 'Nom', value: m.name },
    { label: 'Description', value: m.description || '—' },
    { label: 'Taille', value: sizeLabel },
    { label: 'Paramètres', value: m.parameter_size || details.parameter_size || '—' },
    { label: 'Famille', value: details.family || '—' },
    { label: 'Quantization', value: details.quantization_level || '—' },
    { label: 'Format', value: details.format || '—' },
    { label: 'Contexte', value: m.context_length ? formatContext(m.context_length) : '—' },
    { label: 'Téléchargements', value: m.downloads ? m.downloads.toLocaleString() : '—' },
    { label: 'Source', value: source },
    { label: 'Statut', value: isInstalled ? '✅ Installé localement' : isCloud ? '☁️ Cloud' : '⬇ Disponible au téléchargement' },
  ].filter(r => r.value !== '—');

  const tagBadges = (m.tags || []).map(t => {
    const colors = { cloud: 'amber', vision: 'blue', tools: 'green', thinking: 'purple', code: 'green' };
    const c = colors[t] || '';
    return `<span class="badge ${c}" style="font-size:11px">${t}</span>`;
  }).join(' ');

  const actionBtn = source === 'local'
    ? `<button class="danger" onclick="closeModelDetail(); deleteLocalModel('${m.name}')" style="font-size:12px; padding:8px 16px">🗑 Supprimer</button>`
    : isCloud
      ? `<button class="primary" onclick="closeModelDetail(); addToRotator('${m.name}','${source}')" style="font-size:12px; padding:8px 16px">➕ Ajouter au rotator</button>`
      : isInstalled
        ? `<button onclick="closeModelDetail(); addToRotator('${m.name}','local')" style="font-size:12px; padding:8px 16px">➕ Ajouter au rotator</button>`
        : `<button class="primary" onclick="closeModelDetail(); installModel('${m.name}')" style="font-size:12px; padding:8px 16px">⬇ Installer</button>`;

  document.getElementById('modelDetailBody').innerHTML = `
      <div style="margin-bottom:16px">
        ${tagBadges ? `<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px">${tagBadges}</div>` : ''}
        <table style="width:100%; font-size:12px; border-collapse:collapse">
          ${infoRows.map(r => `
            <tr style="border-bottom:1px solid var(--border)">
              <td style="padding:8px 12px 8px 0; color:var(--text-muted); font-weight:600; white-space:nowrap; width:130px">${r.label}</td>
              <td style="padding:8px 0; color:var(--text); font-family:var(--font-mono); word-break:break-all">${r.value}</td>
            </tr>
          `).join('')}
        </table>
      </div>
      ${m.digest ? `<div style="font-size:11px; color:var(--text-muted); margin-bottom:14px; font-family:var(--font-mono); word-break:break-all">Digest: ${m.digest}</div>` : ''}
      <div style="display:flex; gap:8px; justify-content:flex-end; padding-top:8px; border-top:1px solid var(--border)">
        <button onclick="closeModelDetail()">Fermer</button>
        ${actionBtn}
      </div>
    `;

  document.getElementById('modelDetailModal').classList.add('active');
}

function closeModelDetail() {
  document.getElementById('modelDetailModal').classList.remove('active');
}

function formatBytes(bytes) {
  if (!bytes) return '—';
  const gb = bytes / 1e9;
  return gb >= 1 ? gb.toFixed(1) + ' GB' : (bytes / 1e6).toFixed(0) + ' MB';
}

function formatContext(n) {
  if (!n) return '—';
  return n >= 1000 ? (n / 1000).toFixed(0) + 'K' : n;
}

function showCatTab(name) {
  catTab = name;
  document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.cat-section').forEach(s => s.style.display = 'none');
  document.querySelector(`.cat-tab[onclick="showCatTab('${name}')"]`).classList.add('active');
  document.getElementById(`cat-${name}`).style.display = 'block';

  if (name === 'ollama' && ollamaModelsCache.length === 0) loadOllamaModels();
  if (name === 'openrouter') loadOpenRouterModels();
  if (name === 'nvidia') loadNvidiaModels();
  if (name === 'local') loadLocalModels();
}

async function loadOllamaModels() {
  document.getElementById('ollamaLoading').style.display = 'block';
  document.getElementById('ollamaModelGrid').innerHTML = '';
  try {
    const data = await api('/api/catalogue/ollama');
    ollamaModelsCache = data.models || [];
    filterOllamaModels();
    if (data.updated_at) showCatalogueTimestamp('ollama', data.updated_at);
  } catch (err) {
    document.getElementById('ollamaLoading').innerText = '❌ Impossible de charger le catalogue. Vérifiez votre connexion.';
  }
}

function filterOllamaModels() {
  const q = document.getElementById('ollamaSearch').value.toLowerCase();
  const type = document.getElementById('ollamaFilterType').value;
  const size = document.getElementById('ollamaFilterSize').value;

  const filtered = ollamaModelsCache.filter(m => {
    if (q && !m.name.toLowerCase().includes(q) && !(m.description || '').toLowerCase().includes(q)) return false;
    if (type && !(m.tags || []).includes(type)) return false;
    if (size) {
      const gb = (m.size || 0) / 1e9;
      if (size === 'tiny' && gb >= 2) return false;
      if (size === 'small' && (gb < 2 || gb >= 8)) return false;
      if (size === 'medium' && (gb < 8 || gb >= 30)) return false;
      if (size === 'large' && gb < 30) return false;
    }
    return true;
  });

  document.getElementById('ollamaLoading').style.display = 'none';
  document.getElementById('ollamaModelGrid').innerHTML =
    filtered.length
      ? filtered.map(m => renderModelCard(m, 'ollama')).join('')
      : '<div style="color:var(--text-muted); padding:20px; grid-column:1/-1">Aucun modèle trouvé.</div>';
}

async function loadOpenRouterModels() {
  document.getElementById('openrouterLoading').style.display = 'block';
  document.getElementById('openrouterModelGrid').innerHTML = '';
  try {
    const data = await api('/api/catalogue/openrouter');
    document.getElementById('openrouterLoading').style.display = 'none';
    document.getElementById('openrouterModelGrid').innerHTML =
      (data.models || []).map(m => renderModelCard(m, 'openrouter')).join('') ||
      '<div style="color:var(--text-muted); padding:20px">Aucun modèle gratuit trouvé.</div>';
    if (data.updated_at) showCatalogueTimestamp('openrouter', data.updated_at);
  } catch {
    document.getElementById('openrouterLoading').innerText = '❌ Erreur de chargement.';
  }
}

async function loadNvidiaModels() {
  document.getElementById('nvidiaLoading').style.display = 'block';
  document.getElementById('nvidiaModelGrid').innerHTML = '';
  try {
    const data = await api('/api/catalogue/nvidia');
    document.getElementById('nvidiaLoading').style.display = 'none';
    document.getElementById('nvidiaModelGrid').innerHTML =
      (data.models || []).map(m => renderModelCard(m, 'nvidia')).join('') ||
      '<div style="color:var(--text-muted); padding:20px">Configurez une clé NVIDIA pour voir les modèles.</div>';
    if (data.updated_at) showCatalogueTimestamp('nvidia', data.updated_at);
  } catch {
    document.getElementById('nvidiaLoading').innerText = '❌ Erreur de chargement.';
  }
}

async function loadLocalModels() {
  try {
    const data = await api('/api/catalogue/local');
    document.getElementById('localModelGrid').innerHTML =
      (data.models || []).map(m => renderModelCard(m, 'local')).join('') ||
      '<div style="color:var(--text-muted); padding:20px">Aucun modèle installé localement.</div>';
  } catch {
    document.getElementById('localModelGrid').innerHTML =
      '<div style="color:var(--text-muted); padding:20px">Ollama non détecté.</div>';
  }
}

async function installModel(modelName, button) {
  const safeId = modelName.replace(/[^a-z0-9]/gi, '-');
  button.disabled = true;
  button.innerText = '⏳ Démarrage...';
  const progressDiv = document.getElementById(`progress-${safeId}`);
  const progressBar = document.getElementById(`progress-bar-${safeId}`);
  const progressLabel = document.getElementById(`progress-label-${safeId}`);
  if (progressDiv) progressDiv.style.display = 'block';

  try {
    await api('/api/catalogue/install', 'POST', { model: modelName });
    const poll = setInterval(async () => {
      try {
        const status = await api(`/api/catalogue/install/status?model=${encodeURIComponent(modelName)}`);
        if (progressLabel) progressLabel.innerText = status.message || 'Téléchargement...';
        if (progressBar && status.progress !== undefined) progressBar.style.width = status.progress + '%';
        if (status.done) {
          clearInterval(poll);
          button.innerText = '✅ Installé';
          if (progressDiv) progressDiv.style.display = 'none';
          await loadLocalModels();
        }
        if (status.error) {
          clearInterval(poll);
          button.innerText = '❌ Erreur';
          button.disabled = false;
          if (progressDiv) progressDiv.style.display = 'none';
        }
      } catch { }
    }, 2000);
  } catch {
    button.innerText = '❌ Erreur';
    button.disabled = false;
    if (progressDiv) progressDiv.style.display = 'none';
  }
}

async function addToRotator(modelName, source) {
  try {
    await api('/api/catalogue/add-to-rotator', 'POST', { model: modelName, source });
    alert(`✅ ${modelName} ajouté au rotator ! Rechargez la config pour l'activer.`);
  } catch (err) {
    alert('❌ Erreur : ' + err.message);
  }
}

async function deleteLocalModel(modelName) {
  if (!confirm(`Supprimer ${modelName} de votre machine ?`)) return;
  try {
    await api('/api/catalogue/delete', 'POST', { model: modelName });
    await loadLocalModels();
  } catch (err) {
    alert('❌ Erreur : ' + err.message);
  }
}

async function restartProxy() {
  if (!confirm('Restart the proxy server?')) return;
  try {
    await api('/api/restart', 'POST');
    document.title = '⟳ Restarting…';
    setTimeout(() => { location.reload(); }, 3000);
  } catch (err) {
    alert('❌ Restart failed: ' + err.message);
  }
}
