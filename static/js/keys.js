/* ─── KEYS CENTER ─── */
function updateKeyField(provider, index, field, value) {
  if (!keysState[provider]) return;
  keysState[provider][index][field] = value;
}

function isEnvRef(value) {
  const v = (value || '').trim();
  return v.startsWith('env:') || (v.startsWith('${') && v.endsWith('}') && v.length > 3);
}

function onKeyInput(provider, index, value) {
  updateKeyField(provider, index, 'value', value);
  const statusKey = `${provider}-${index}`;
  const statusEl = document.getElementById(`keystatus-${provider}-${index}`);
  keyTestStatus[statusKey] = 'pending';
  keyTestMessages[statusKey] = '';
  if (statusEl) { statusEl.innerText = ''; statusEl.title = ''; }
  if (keyTestTimers[statusKey]) clearTimeout(keyTestTimers[statusKey]);
  if (!value || value.length < 10) return;
  if (isEnvRef(value)) {
    keyTestStatus[statusKey] = 'pending';
    keyTestMessages[statusKey] = "Référence d'environnement détectée";
    if (statusEl) {
      statusEl.innerText = '🔗';
      statusEl.title = keyTestMessages[statusKey];
    }
    return;
  }
  if (statusEl) statusEl.innerText = '⏳';
  keyTestStatus[statusKey] = 'testing';
  keyTestTimers[statusKey] = setTimeout(() => { autoTestKey(provider, index, value); }, 800);
}

async function autoTestKey(provider, index, value) {
  const statusKey = `${provider}-${index}`;
  const statusEl = document.getElementById(`keystatus-${provider}-${index}`);
  if (statusEl) statusEl.innerText = '⏳';
  keyTestStatus[statusKey] = 'testing';
  try {
    const res = await api('/api/config/keys/test', 'POST', { provider, value });
    keyTestStatus[statusKey] = res.ok ? 'ok' : 'fail';
    keyTestMessages[statusKey] = res.message || '';
    if (statusEl) { statusEl.innerText = res.ok ? '✅' : '❌'; statusEl.title = res.message || ''; }
    setKeysStatus(res.message, res.ok ? 'success' : 'error');
  } catch (err) {
    keyTestStatus[statusKey] = 'fail';
    keyTestMessages[statusKey] = `Erreur de test: ${err.message}`;
    if (statusEl) { statusEl.innerText = '❌'; statusEl.title = keyTestMessages[statusKey]; }
    setKeysStatus('Erreur de test: ' + err.message, 'error');
  }
}

async function testKey(provider, index, button) {
  const item = (keysState[provider] || [])[index];
  if (!item || !item.value) { setKeysStatus(`Renseignez une clé pour ${provider} avant le test.`, 'error'); return; }
  const prev = button.innerText;
  button.innerText = '⏳';
  await autoTestKey(provider, index, item.value);
  button.innerText = prev;
}

function addKeyRow(provider) {
  if (!keysState[provider]) keysState[provider] = [];
  keysState[provider].push({ label: '', value: '' });
  renderKeysCenter();
}

function removeKeyRow(provider, index) {
  if (!keysState[provider]) return;
  keysState[provider].splice(index, 1);
  renderKeysCenter();
}

function toggleSecret(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  btn.innerText = isHidden ? '🙈' : '👁️';
}

function renderKeysCenter() {
  const host = document.getElementById('keysProviders');
  if (!host) return;
  host.innerHTML = keyProviders.map(provider => {
    const rows = (keysState[provider] || []).map((item, index) => {
      const inputId = `key-${provider}-${index}`;
      const statusKey = `${provider}-${index}`;
      const status = keyTestStatus[statusKey] || 'pending';
      const statusIcon = status === 'ok' ? '✅' : status === 'fail' ? '❌' : status === 'testing' ? '⏳' : '';
      const statusTitle = escapeHtml(keyTestMessages[statusKey] || '');
      return `
          <div style="display:grid; grid-template-columns:1fr 2fr auto auto; gap:8px; align-items:center; margin-top:8px">
            <input placeholder="Label" value="${escapeHtml(item.label || '')}" oninput="updateKeyField('${provider}', ${index}, 'label', this.value)"/>
            <input id="${inputId}" type="password" placeholder="Clé API" value="${escapeHtml(item.value || '')}" oninput="onKeyInput('${provider}', ${index}, this.value)"/>
            <span id="keystatus-${provider}-${index}" style="font-size:16px; flex-shrink:0; min-width:24px; text-align:center" title="${statusTitle}">${statusIcon}</span>
            <div class="flex-row" style="gap:4px">
              <button title="Afficher" onclick="toggleSecret('${inputId}', this)" style="padding:6px 8px">👁️</button>
              <button title="Tester" onclick="testKey('${provider}', ${index}, this)" style="padding:6px 8px">🧪</button>
              <button title="Copier" onclick="copyText(keysState['${provider}'][${index}]?.value||'',this)" style="padding:6px 8px">📋</button>
              <button title="Supprimer" onclick="removeKeyRow('${provider}',${index})" style="padding:6px 8px" class="danger">🗑</button>
            </div>
          </div>`;
    }).join('');
    return `
        <div class="key-center-card">
          <div style="display:flex; justify-content:space-between; align-items:center">
            <div style="font-size:14px; font-weight:700; color:#fff">${providerTitle(provider)}</div>
            <span class="badge">${(keysState[provider] || []).length} clé(s)</span>
          </div>
          <div style="font-size:12px; color:var(--text-dim); margin-top:4px">Ajoutez, testez et confirmez vos clés.</div>
          ${rows || '<div style="font-size:12px; color:var(--text-muted); margin-top:10px">Aucune clé configurée.</div>'}
          <button style="margin-top:12px; width:100%" onclick="addKeyRow('${provider}')">+ Ajouter une clé ${providerTitle(provider)}</button>
        </div>`;
  }).join('');
}

async function loadKeysCenter() {
  try {
    const data = await api('/api/config/keys');
    keysState = defaultKeysState();
    if (data.providers && Array.isArray(data.providers)) {
      keyProviders = data.providers;
    }
    keyProviders.forEach(p => {
      const list = data.keys?.[p] || [];
      keysState[p] = list.map((item, index) => {
        keyTestStatus[`${p}-${index}`] = 'pending';
        keyTestMessages[`${p}-${index}`] = '';
        return { label: item.label || '', value: item.value || '' };
      });
    });
    renderKeysCenter();
    setKeysStatus('Clés chargées depuis config.yaml');
  } catch (err) { setKeysStatus(`Chargement impossible: ${err.message}`, 'error'); }
}

async function saveKeysCenter() {
  const failed = [];
  keyProviders.forEach(provider => {
    (keysState[provider] || []).forEach((item, index) => {
      if (!item.value || item.value.length < 10) return;
      if (isEnvRef(item.value)) return;
      const status = keyTestStatus[`${provider}-${index}`];
      if (status !== 'ok') failed.push(`${provider} clé ${index + 1}`);
    });
  });
  if (failed.length > 0) {
    setKeysStatus(`❌ Certaines clés sont invalides. Corrigez-les avant de sauvegarder. (${failed.join(', ')})`, 'error');
    return;
  }
  try {
    await api('/api/config/keys', 'POST', { keys: keysState });
    setKeysStatus('✅ Toutes les clés validées et enregistrées.', 'success');
    await refreshRouting();
  } catch (err) { setKeysStatus(`Sauvegarde impossible: ${err.message}`, 'error'); }
}

function exportKeys() {
  const blob = new Blob([JSON.stringify({ keys: keysState }, null, 2)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'rotator-keys.json'; a.click();
}

function setProjectsStatus(msg, level = 'info') {
  const el = document.getElementById('projectsStatus');
  if (!el) return;
  el.style.color = level === 'error' ? 'var(--red)' : level === 'success' ? 'var(--green)' : 'var(--text-dim)';
  el.innerText = msg;
}

function setMaintenanceStatus(msg, level = 'info') {
  const el = document.getElementById('maintenanceStatus');
  if (!el) return;
  el.style.color = level === 'error' ? 'var(--red)' : level === 'success' ? 'var(--green)' : level === 'warn' ? 'var(--accent)' : 'var(--text-dim)';
  el.innerText = msg;
}

function formatProjectQuota(limit, used) {
  if (limit === null || limit === undefined) return `${used} / ∞`;
  return `${used} / ${limit}`;
}

async function loadProjects() {
  try {
    const data = await api('/api/projects');
    const rows = data.items || [];
    document.getElementById('projectsList').innerHTML = rows.map(p => {
      const pct = p.daily_limit ? Math.min(100, Math.round((p.requests_today / p.daily_limit) * 100)) : 0;
      const quotaBadge = p.daily_limit
        ? `<span class="badge ${pct >= 90 ? 'red' : pct >= 70 ? 'amber' : 'green'}">${pct}%</span>`
        : '<span class="badge blue">illimité</span>';
      return `
          <div class="card" style="padding:14px 16px">
            <div style="display:flex; align-items:center; gap:10px">
              <div style="font-size:14px; font-weight:700; color:#fff; flex:1">${escapeHtml(p.name)}</div>
              <span class="badge ${p.active ? 'green' : 'red'}">${p.active ? 'actif' : 'révoqué'}</span>
              ${quotaBadge}
            </div>
            <div style="display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:8px; margin-top:10px; font-size:12px; color:var(--text-dim)">
              <div><b>Quota:</b> ${formatProjectQuota(p.daily_limit, p.requests_today)}</div>
              <div><b>Policy:</b> ${escapeHtml(p.policy)}</div>
              <div><b>Mode:</b> ${escapeHtml(p.quota_mode)}</div>
              <div><b>Token:</b> <span class="mono">${escapeHtml(p.token)}</span></div>
            </div>
            <div class="flex-row" style="margin-top:10px">
              <button onclick="copyText('${escapeHtml(p.token)}', this)">📋 Copier token</button>
              <button onclick="launchClaudeTerminal('${escapeHtml(p.token)}')">🖥 Ouvrir terminal Claude</button>
              ${p.active ? `<button class="danger" onclick="revokeProject(${p.id})">🔒 Révoquer</button>` : ''}
            </div>
          </div>`;
    }).join('') || '<div style="color:var(--text-muted); font-size:12px">Aucun projet configuré.</div>';
    // Update Claude summary card
    try { updateClaudeSummary(rows); } catch { }
    setProjectsStatus('Projets chargés.');
  } catch (err) { setProjectsStatus(`Chargement impossible: ${err.message}`, 'error'); }
}

function updateClaudeSummary(rows) {
  const items = rows || [];
  const claudes = items.filter(p => String(p.policy || '').toLowerCase() === 'coding_only');
  const count = claudes.length;
  const totalRequests = claudes.reduce((s, p) => s + (Number(p.requests_today ?? p.used_today ?? 0) || 0), 0);
  const elCount = document.getElementById('claudeSummaryCount');
  const elReq = document.getElementById('claudeSummaryRequests');
  if (elCount) elCount.innerText = count;
  if (elReq) elReq.innerText = totalRequests.toLocaleString();
}

async function createProjectFromForm() {
  const name = document.getElementById('projectName').value.trim();
  const daily = document.getElementById('projectDailyLimit').value;
  const policy = document.getElementById('projectPolicy').value;
  const quota_mode = document.getElementById('projectQuotaMode').value;
  if (!name) { setProjectsStatus('Nom du projet requis.', 'error'); return; }
  try {
    const res = await api('/api/projects', 'POST', { name, daily_limit: daily === '' ? null : Number(daily), policy, quota_mode });
    setProjectsStatus(`✅ Projet créé: ${res.project.name}`, 'success');
    document.getElementById('projectName').value = '';
    document.getElementById('projectDailyLimit').value = '';
    await loadProjects();
  } catch (err) { setProjectsStatus(`Création impossible: ${err.message}`, 'error'); }
}

async function revokeProject(id) {
  showConfirm('Révoquer token projet', 'Révoquer ce token projet ?\n\nCette action est irréversible.', 'Révoquer', async () => {
    await api(`/api/projects/${id}/revoke`, 'POST');
    await loadProjects();
    setProjectsStatus('Token révoqué.', 'success');
  });
}

async function launchClaudeTerminal(token) {
  const install = !!document.getElementById('claudeInstallFlag')?.checked;
  try {
    await api('/api/projects/claude-onboarding/launch', 'POST', { token, install_claude: install });
    setProjectsStatus('Terminal Claude ouvert.', 'success');
  } catch (err) { setProjectsStatus(`Ouverture terminal impossible: ${err.message}`, 'error'); }
}

async function createClaudeProjectAndLaunch() {
  const daily = document.getElementById('claudeDailyLimit').value;
  try {
    const res = await api('/api/projects/claude-onboarding', 'POST', { daily_limit: daily === '' ? null : Number(daily) });
    const token = res.project.token;
    const tokenEl = document.getElementById('claudeOnboardToken');
    tokenEl.style.display = 'block';
    tokenEl.innerText = token;
    await copyText(token);
    await loadProjects();
    await launchClaudeTerminal(token);
  } catch (err) { setProjectsStatus(`Onboarding Claude impossible: ${err.message}`, 'error'); }
}

async function importKeys(event) {
  const file = event.target.files?.[0]; if (!file) return;
  try {
    const text = await file.text(); const parsed = JSON.parse(text);
    if (!parsed?.keys) throw new Error('Format invalide');
    keysState = defaultKeysState();
    keyProviders.forEach(p => { keysState[p] = (parsed.keys?.[p] || []).map(item => ({ label: item.label || '', value: item.value || '' })); });
    renderKeysCenter(); setKeysStatus('Import chargé. Cliquez sur "Enregistrer" pour appliquer.', 'success');
  } catch (err) { setKeysStatus(`Import impossible: ${err.message}`, 'error'); }
  finally { event.target.value = ''; }
}

async function loadKeyTestCenter() {
  try {
    const data = await api('/api/config/keys');
    if (data.providers && Array.isArray(data.providers)) {
      keyProviders = data.providers;
    }
    keyTestCenterState = {};
    keyProviders.forEach(provider => {
      const list = (data.keys?.[provider] || []);
      keyTestCenterState[provider] = list.map(item => ({
        label: item.label || provider,
        value: item.value || '',
        status: 'idle',
        message: 'Pas encore testé',
      }));
    });
    renderKeyTestCenter();
    setKeyTestCenterStatus('Clés chargées.');
  } catch (err) { setKeyTestCenterStatus(`Chargement impossible: ${err.message}`, 'error'); }
}

function renderKeyTestCenter() {
  const host = document.getElementById('keyTestCenterHost');
  if (!host) return;
  host.innerHTML = keyProviders.map(provider => {
    const rows = keyTestCenterState[provider] || [];
    const providerLabel = providerTitle(provider);
    const tested = rows.filter(r => r.status !== 'idle').length;
    const rowHtml = rows.map((row, index) => {
      const badge = getCenterStatusBadge(row.status);
      const safeMsg = escapeHtml(row.message || '');
      return `
          <div style="display:grid; grid-template-columns:1.2fr 1fr auto auto; gap:8px; align-items:center; margin-top:8px; background:var(--surface2); border:1px solid var(--border); border-radius:var(--r-sm); padding:8px 10px">
            <div>
              <div style="font-size:12px; color:#fff; font-weight:600">${escapeHtml(row.label)}</div>
              <div style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono)">${escapeHtml(keyMask(row.value))}</div>
            </div>
            <div style="font-size:11px; color:var(--text-dim)">${safeMsg}</div>
            <span class="badge ${badge.cls}" style="font-size:10px">${badge.text}</span>
            <button onclick="testSingleKeyCenter('${provider}', ${index})" ${keyTestCenterRunning ? 'disabled' : ''} style="padding:6px 10px; font-size:11px">Tester</button>
          </div>`;
    }).join('') || '<div style="font-size:12px; color:var(--text-muted); margin-top:8px">Aucune clé configurée.</div>';

    return `
        <div class="key-center-card">
          <div style="display:flex; align-items:center; gap:8px">
            <div style="font-size:14px; font-weight:700; color:#fff; flex:1">${providerLabel}</div>
            <span class="badge">${tested}/${rows.length} testées</span>
            <button onclick="testProviderKeysCenter('${provider}')" ${keyTestCenterRunning ? 'disabled' : ''} style="font-size:11px; padding:6px 10px">Tester ce provider</button>
          </div>
          ${rowHtml}
        </div>`;
  }).join('');
}

async function testSingleKeyCenter(provider, index) {
  const row = keyTestCenterState?.[provider]?.[index];
  if (!row || !row.value) return;
  row.status = 'testing';
  row.message = 'Test en cours...';
  renderKeyTestCenter();
  try {
    const res = await api('/api/config/keys/test', 'POST', { provider, value: row.value });
    row.status = res.status || (res.ok ? 'ok' : 'error');
    row.message = res.message || '';
    renderKeyTestCenter();
    const level = row.status === 'ok' ? 'success' : row.status === 'quota' || row.status === 'warning' ? 'warn' : 'error';
    setKeyTestCenterStatus(`${providerTitle(provider)} · ${row.label}: ${row.message}`, level);
  } catch (err) {
    row.status = 'network';
    row.message = `Erreur réseau: ${err.message}`;
    renderKeyTestCenter();
    setKeyTestCenterStatus(`Erreur test ${provider} / ${row.label}: ${err.message}`, 'error');
  }
}

async function testProviderKeysCenter(provider) {
  if (keyTestCenterRunning) return;
  const rows = keyTestCenterState?.[provider] || [];
  if (!rows.length) { setKeyTestCenterStatus(`Aucune clé pour ${providerTitle(provider)}.`, 'warn'); return; }
  keyTestCenterRunning = true;
  renderKeyTestCenter();
  for (let i = 0; i < rows.length; i++) await testSingleKeyCenter(provider, i);
  keyTestCenterRunning = false;
  renderKeyTestCenter();
  setKeyTestCenterStatus(`Tests terminés pour ${providerTitle(provider)}.`, 'success');
}

async function testAllKeysCenter() {
  if (keyTestCenterRunning) return;
  keyTestCenterRunning = true;
  renderKeyTestCenter();
  setKeyTestCenterStatus('Test de toutes les clés en cours...');
  for (const provider of keyProviders) {
    const rows = keyTestCenterState?.[provider] || [];
    for (let i = 0; i < rows.length; i++) await testSingleKeyCenter(provider, i);
  }
  keyTestCenterRunning = false;
  renderKeyTestCenter();
  setKeyTestCenterStatus('✅ Test de toutes les clés terminé.', 'success');
}
