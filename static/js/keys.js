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

// Cache for profiles to avoid repeated API calls
let cachedProfiles = null;

async function loadProfileCheckboxes(containerId, selectedProfiles) {
  // Load profiles from API if not cached
  if (!cachedProfiles) {
    try {
      const data = await api('/api/profiles/custom');
      cachedProfiles = {
        builtin: data.builtin_profiles || ['coding', 'reasoning', 'chat', 'long', 'vision', 'audio', 'translate'],
        custom: data.custom_profiles || []
      };
    } catch (e) {
      console.error('Failed to load profiles:', e);
      cachedProfiles = { builtin: ['coding', 'reasoning', 'chat', 'long', 'vision', 'audio', 'translate'], custom: [] };
    }
  }

  // Merge builtin and custom profiles
  const allProfiles = [...cachedProfiles.builtin, ...cachedProfiles.custom.map(p => p.name)];
  const container = document.getElementById(containerId);
  if (!container) return;

  // Get selected profiles as array
  const selected = selectedProfiles ? selectedProfiles.split(',').map(p => p.trim()).filter(p => p) : [];

  // Generate checkboxes
  container.innerHTML = allProfiles.map(profile => {
    const isChecked = selected.length === 0 || selected.includes(profile);
    return `
      <label style="font-size:11px; color:var(--text); display:flex; align-items:center; gap:2px">
        <input type="checkbox" class="profile-checkbox" value="${profile}" ${isChecked ? 'checked' : ''} /> ${profile}
      </label>
    `;
  }).join('');
}

function getSelectedProfiles(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return '';
  const checkboxes = container.querySelectorAll('.profile-checkbox:checked');
  return Array.from(checkboxes).map(cb => cb.value).join(',');
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
          <div class="card" style="padding:14px 16px; cursor:pointer" onclick="showProjectDetail(${p.id})" title="Cliquez pour voir les details">
            <div style="display:flex; align-items:center; gap:10px">
              <div style="font-size:14px; font-weight:700; color:#fff; flex:1">${escapeHtml(p.name)}</div>
              <span class="badge ${p.active ? 'green' : 'red'}">${p.active ? 'actif' : 'révoqué'}</span>
              ${quotaBadge}
            </div>
            <div style="display:grid; grid-template-columns:repeat(3,minmax(120px,1fr)); gap:8px; margin-top:10px; font-size:12px; color:var(--text-dim)">
              <div><b>Quota:</b> ${formatProjectQuota(p.daily_limit, p.requests_today)}</div>
              <div><b>Mode:</b> ${escapeHtml(p.quota_mode)}</div>
              <div><b>Token:</b> <span class="mono">${escapeHtml(p.token.substring(0, 12))}...</span></div>
            </div>
            <div class="flex-row" style="margin-top:10px" onclick="event.stopPropagation()">
              <button onclick="copyText('${escapeHtml(p.token)}', this)">Copier token</button>
              <button onclick="launchClaudeTerminal('${escapeHtml(p.token)}')">Claude</button>
              ${p.active ? `<button class="danger" onclick="revokeProject(${p.id})">Revoquer</button>` : ''}
            </div>
          </div>`;
    }).join('') || '<div style="color:var(--text-muted); font-size:12px">Aucun projet configure.</div>';
    // Update Claude summary card
    try { updateClaudeSummary(rows); } catch { }
    // Load profile checkboxes for new project form
    try { await loadProfileCheckboxes('newProjectProfileCheckboxes', ''); } catch { }
    setProjectsStatus('Projets charges.');
  } catch (err) { setProjectsStatus(`Chargement impossible: ${err.message}`, 'error'); }
}

function updateClaudeSummary(rows) {
  const items = rows || [];
  // Filter projects that have coding in allowed_profiles
  // If allowed_profiles is null/empty, it means ALL profiles are allowed
  const claudes = items.filter(p => {
    const allowed = (p.allowed_profiles || '').toLowerCase();
    // If allowed_profiles is empty/null, include all (all profiles allowed)
    // Otherwise only include if coding is explicitly allowed
    return !allowed || allowed.includes('coding');
  });
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
  const quota_mode = document.getElementById('projectQuotaMode').value;
  const allowed_profiles = getSelectedProfiles('newProjectProfileCheckboxes');
  if (!name) { setProjectsStatus('Nom du projet requis.', 'error'); return; }
  try {
    const res = await api('/api/projects', 'POST', { name, daily_limit: daily === '' ? null : Number(daily), quota_mode, allowed_profiles: allowed_profiles || null });
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

// ========== PROJECT DETAIL VIEW ==========
let currentProjectId = null;
let projectUsageChart = null;

async function showProjectDetail(projectId) {
  currentProjectId = projectId;
  document.getElementById('projectsList').style.display = 'none';
  document.getElementById('projectDetail').style.display = 'block';
  await loadProjectDetails(projectId);
  await loadProjectUsage();
}

function showProjectsList() {
  currentProjectId = null;
  document.getElementById('projectDetail').style.display = 'none';
  document.getElementById('projectsList').style.display = 'flex';
}

async function loadProjectDetails(projectId) {
  try {
    const data = await api(`/api/projects/${projectId}`);
    const p = data.project;

    document.getElementById('projectDetailName').textContent = p.name;

    const statusEl = document.getElementById('projectDetailStatus');
    statusEl.textContent = p.active ? 'actif' : 'revoque';
    statusEl.className = 'badge ' + (p.active ? 'green' : 'red');

    document.getElementById('projectDetailToken').textContent = p.token;
    document.getElementById('projectDetailQuotaMode').textContent = p.quota_mode;
    document.getElementById('projectDetailDailyLimit').textContent = p.daily_limit ? p.daily_limit + ' / jour' : 'Illimite';
    document.getElementById('projectDetailRateLimit').textContent = p.rate_limit ? p.rate_limit + ' req/min' : 'Illimite';
    document.getElementById('projectDetailMaxCost').textContent = p.max_cost ? p.max_cost + ' $/jour' : 'Illimite';
    document.getElementById('projectDetailAllowedProfiles').textContent = p.allowed_profiles || 'Tous';
    document.getElementById('projectDetailForcedProvider').textContent = p.forced_provider || 'Auto';
    document.getElementById('projectDetailCreated').textContent = new Date(p.created_at).toLocaleString('fr-FR');
    document.getElementById('projectDetailUpdated').textContent = new Date(p.updated_at).toLocaleString('fr-FR');

    // Show/hide revoke button based on active status
    document.getElementById('projectRevokeBtn').style.display = p.active ? 'inline-block' : 'none';

  } catch (err) {
    setProjectsStatus('Erreur chargement projet: ' + err.message, 'error');
  }
}

async function loadProjectUsage() {
  if (!currentProjectId) return;

  const days = document.getElementById('projectUsageRange')?.value || 30;

  try {
    const data = await api(`/api/projects/${currentProjectId}/usage?days=${days}`);
    const history = data.history || [];
    const total = data.total_requests || 0;

    // Update total display
    document.getElementById('projectUsageTotal').textContent =
      `Total: ${total.toLocaleString()} requetes sur ${days} jours`;

    // Render chart
    const ctx = document.getElementById('projectUsageChart');
    if (!ctx) return;

    if (projectUsageChart) {
      projectUsageChart.destroy();
    }

    const labels = history.map(h => h.date).reverse();
    const values = history.map(h => h.requests).reverse();

    projectUsageChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Requetes',
          data: values,
          backgroundColor: 'rgba(99, 102, 241, 0.6)',
          borderColor: '#6366f1',
          borderWidth: 1,
          borderRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          x: {
            ticks: { color: '#888', font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.04)' }
          },
          y: {
            ticks: { color: '#888', font: { size: 10 } },
            grid: { color: 'rgba(255,255,255,0.04)' },
            beginAtZero: true
          }
        }
      }
    });

  } catch (err) {
    console.error('Error loading project usage:', err);
  }
}

// ========== EDIT PROJECT MODAL ==========
async function showEditProjectModal() {
  if (!currentProjectId) return;

  try {
    const data = await api(`/api/projects/${currentProjectId}`);
    const p = data.project;

    document.getElementById('editProjectName').value = p.name || '';
    document.getElementById('editProjectDailyLimit').value = p.daily_limit || '';
    document.getElementById('editProjectNoLimit').checked = !p.daily_limit;
    document.getElementById('editProjectQuotaMode').value = p.quota_mode || 'hard_block';
    document.getElementById('editProjectRateLimit').value = p.rate_limit || '';
    document.getElementById('editProjectMaxCost').value = p.max_cost || '';
    document.getElementById('editProjectForcedProvider').value = p.forced_provider || '';

    // Load checkboxes for allowed profiles dynamically
    await loadProfileCheckboxes('editProjectProfileCheckboxes', p.allowed_profiles || '');

    toggleNoLimit();

    document.getElementById('editProjectModal').style.display = 'flex';
  } catch (err) {
    setProjectsStatus('Erreur: ' + err.message, 'error');
  }
}

function closeEditProjectModal() {
  document.getElementById('editProjectModal').style.display = 'none';
}

function toggleNoLimit() {
  const noLimit = document.getElementById('editProjectNoLimit')?.checked;
  const limitInput = document.getElementById('editProjectDailyLimit');
  if (limitInput) {
    limitInput.disabled = noLimit;
    if (noLimit) {
      limitInput.value = '';
    }
  }
}

async function saveProjectChanges() {
  if (!currentProjectId) return;

  const name = document.getElementById('editProjectName').value.trim();
  const noLimit = document.getElementById('editProjectNoLimit')?.checked;
  const dailyLimitRaw = document.getElementById('editProjectDailyLimit').value;
  const quotaMode = document.getElementById('editProjectQuotaMode').value;
  const rateLimitRaw = document.getElementById('editProjectRateLimit').value;
  const maxCostRaw = document.getElementById('editProjectMaxCost').value;
  const forcedProvider = document.getElementById('editProjectForcedProvider').value;

  // Get selected profiles from checkboxes (dynamically loaded)
  const allowedProfiles = getSelectedProfiles('editProjectProfileCheckboxes') || null;

  const payload = { quota_mode: quotaMode };

  if (name) payload.name = name;
  if (noLimit) {
    payload.daily_limit = null;
  } else if (dailyLimitRaw) {
    payload.daily_limit = parseInt(dailyLimitRaw, 10);
  }

  // New parameters
  if (rateLimitRaw) {
    payload.rate_limit = parseInt(rateLimitRaw, 10);
  } else {
    payload.rate_limit = null;
  }

  if (maxCostRaw) {
    payload.max_cost = parseFloat(maxCostRaw);
  } else {
    payload.max_cost = null;
  }

  if (allowedProfiles) {
    payload.allowed_profiles = allowedProfiles;
  } else {
    payload.allowed_profiles = null;
  }

  if (forcedProvider) {
    payload.forced_provider = forcedProvider;
  } else {
    payload.forced_provider = null;
  }

  try {
    await api(`/api/projects/${currentProjectId}`, 'PUT', payload);
    closeEditProjectModal();
    await loadProjectDetails(currentProjectId);
    await loadProjects(); // Refresh list
    setProjectsStatus('Projet mis a jour.', 'success');
  } catch (err) {
    setProjectsStatus('Erreur mise a jour: ' + err.message, 'error');
  }
}

// ========== PROJECT ACTIONS ==========
async function deleteProjectFromDetail() {
  if (!currentProjectId) return;

  const confirmed = confirm('Supprimer ce projet definitivement ?\n\nCette action est irreversible.');
  if (!confirmed) return;

  try {
    await api(`/api/projects/${currentProjectId}`, 'DELETE');
    showProjectsList();
    await loadProjects();
    setProjectsStatus('Projet supprime.', 'success');
  } catch (err) {
    setProjectsStatus('Erreur suppression: ' + err.message, 'error');
  }
}

async function revokeProjectFromDetail() {
  if (!currentProjectId) return;

  const confirmed = confirm('Revoquer ce token projet ?\n\nLe projet ne sera plus utilisable.');
  if (!confirmed) return;

  try {
    await api(`/api/projects/${currentProjectId}/revoke`, 'POST');
    await loadProjectDetails(currentProjectId);
    await loadProjects();
    setProjectsStatus('Token revoque.', 'success');
  } catch (err) {
    setProjectsStatus('Erreur revocation: ' + err.message, 'error');
  }
}

function copyProjectToken() {
  const token = document.getElementById('projectDetailToken')?.textContent;
  if (token) {
    copyText(token);
    setProjectsStatus('Token copie.', 'success');
  }
}

async function launchClaudeWithProject() {
  const token = document.getElementById('projectDetailToken')?.textContent;
  if (token) {
    await launchClaudeTerminal(token);
  }
}

// Update the project list to add click handlers
function initProjectDetailLinks() {
  // This function is called after loadProjects to add click handlers
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

// Add Provider Modal Functions
function openAddProviderModal() {
  document.getElementById('addProviderModal').style.display = 'flex';
  document.getElementById('addProviderName').value = '';
  document.getElementById('addProviderBaseUrl').value = '';
  document.getElementById('addProviderApiKey').value = '';
  document.getElementById('addProviderLabel').value = '';
  document.getElementById('addProviderStatus').textContent = '';
  document.getElementById('addProviderName').focus();
}

function closeAddProviderModal() {
  document.getElementById('addProviderModal').style.display = 'none';
}

async function addProvider() {
  const providerName = document.getElementById('addProviderName').value.trim().toLowerCase();
  const baseUrl = document.getElementById('addProviderBaseUrl').value.trim();
  const apiKey = document.getElementById('addProviderApiKey').value.trim();
  const label = document.getElementById('addProviderLabel').value.trim();
  const statusEl = document.getElementById('addProviderStatus');

  // Validation
  if (!providerName) {
    statusEl.textContent = '❌ Le nom du provider est requis';
    statusEl.style.color = 'var(--error)';
    return;
  }
  if (!baseUrl) {
    statusEl.textContent = '❌ La base URL est requise';
    statusEl.style.color = 'var(--error)';
    return;
  }
  if (!apiKey) {
    statusEl.textContent = '❌ La clé API est requise';
    statusEl.style.color = 'var(--error)';
    return;
  }

  // Check for valid characters in provider name
  if (!/^[a-z0-9_]+$/.test(providerName)) {
    statusEl.textContent = '❌ Le nom doit contenir uniquement des lettres minuscules, chiffres et underscores';
    statusEl.style.color = 'var(--error)';
    return;
  }

  statusEl.textContent = '⏳ Ajout en cours...';
  statusEl.style.color = 'var(--text-dim)';

  try {
    const res = await fetch('/api/config/providers/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: providerName,
        base_url: baseUrl,
        api_key: apiKey,
        label: label || providerName
      })
    });

    const data = await res.json();

    if (data.ok) {
      statusEl.textContent = data.message || '✅ Provider ajouté avec succès';
      statusEl.style.color = 'var(--success, green)';
      setTimeout(() => {
        closeAddProviderModal();
        loadKeysCenter(); // Reload keys to show the new provider
      }, 1000);
    } else {
      statusEl.textContent = data.message || '❌ Erreur lors de l\'ajout';
      statusEl.style.color = 'var(--error)';
    }
  } catch (err) {
    statusEl.textContent = '❌ Erreur réseau: ' + err.message;
    statusEl.style.color = 'var(--error)';
  }
}
