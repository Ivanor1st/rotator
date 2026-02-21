  /* ─── MODELS ─── */
  async function loadModels() {
    const data = await api('/api/models');
    modelsCatalog = data.providers || {};
    const allModels = Object.values(modelsCatalog).flat().map(m => m.model);
    ['compareM1', 'compareM2', 'compareM3'].forEach(id => {
      const sel = document.getElementById(id);
      if (sel) sel.innerHTML = allModels.map(m => `<option value="${m}">${m}</option>`).join('');
    });
  }

  /* ─── ROUTING ─── */
  async function refreshRouting() {
    const data = await api('/api/status');
    document.getElementById('uptime').innerText = formatUptime(data.uptime_seconds);
    document.getElementById('totalReq').innerText = (data.total_requests_today || 0).toLocaleString();
    document.getElementById('activeProv').innerText = data.active_providers || 0;
    document.getElementById('sidebarPort').innerText = data.port || 47822;

    const modeBadge = document.getElementById('modeBadge');
    modeBadge.innerText = data.mode || 'AUTO';
    modeBadge.className = 'mode-badge' + (data.mode === 'LOCKED' ? ' locked' : data.mode === 'PRESET' ? ' preset' : '');

    const port = data.port || 47822;
    document.getElementById('onboardBase').innerText = `http://localhost:${port}/v1`;
    document.getElementById('onboardModels').innerText = `http://localhost:${port}/v1/models`;

    const profileEmojis = { coding:'💻', reasoning:'🧠', chat:'💬', long:'📄', vision:'👁️', audio:'🎵', translate:'🌍' };
    const options = ['auto','ollama_cloud','nvidia','openrouter','google','local'];

    const maxReqs = Math.max(1, ...data.profiles.map(p => p.requests_today || 0));

    document.getElementById('profileCards').innerHTML = data.profiles.map(p => {
      const emoji = profileEmojis[p.name] || '⚡';
      const isLocked = !!p.locked_model;
      const barWidth = maxReqs > 0 ? Math.min(100, Math.round((p.requests_today || 0) / maxReqs * 100)) : 0;
      return `
        <div class="profile-card ${isLocked ? 'locked-card' : ''}">
          <div style="display:flex; justify-content:space-between; align-items:flex-start">
            <span class="profile-emoji">${emoji}</span>
            <button onclick="openLockModal('${p.name}')" style="font-size:11px; padding:4px 8px">${isLocked ? '🔒' : '🔓'} Lock</button>
          </div>
          <div class="profile-name">${p.name}</div>
          <div class="profile-model">${p.model || '—'}</div>
          <div class="profile-provider">${providerEmoji(p.provider)} ${p.provider}</div>
          <div class="profile-bar"><div class="profile-bar-fill" style="width:${barWidth}%"></div></div>
          <div class="profile-footer">
            <span class="req-count">${p.requests_today} req</span>
            <select onchange="forceProfile('${p.name}', this.value)" style="font-size:11px; padding:4px 6px; width:auto">
              ${options.map(o => `<option value="${o}" ${o===p.override?'selected':''}>${o}</option>`).join('')}
            </select>
          </div>
          ${isLocked ? `<div style="margin-top:8px; font-size:10.5px; color:var(--accent); font-family:var(--font-mono)">🔒 ${p.locked_model}</div>` : ''}
        </div>`;
    }).join('');

    document.getElementById('providerGrid').innerHTML = Object.values(data.provider_status).map(p => {
      const suspended = data.suspensions && data.suspensions[p.provider];
      const keys = p.keys.map(k => `
        <div class="key-chip">
          <div class="key-dot ${suspended ? 'red' : ''}"></div>
          <span class="key-label">${k.label || k.key_id}</span>
          <span class="key-stat">${k.rpm} rpm</span>
        </div>`).join('');
      return `
        <div class="provider-card">
          <div class="provider-header">
            <span class="provider-name">${providerTitle(p.provider)}</span>
            <span class="badge ${suspended ? 'red' : 'green'}">${suspended ? '⏸ Suspendu' : '✅ Actif'}</span>
          </div>
          <div class="provider-meter">
            <div class="meter-label"><span>Charge RPM</span><span>${p.rpm || 0}/${p.rpm_limit || 40}</span></div>
            <div class="meter-bar"><div class="meter-fill ${(p.rpm||0)/(p.rpm_limit||40)>.8?'red':(p.rpm||0)/(p.rpm_limit||40)>.5?'amber':'green'}" style="width:${Math.min(100,(p.rpm||0)/(p.rpm_limit||40)*100)}%"></div></div>
          </div>
          <div class="key-row-list">${keys || '<div style="font-size:11px; color:var(--text-muted)">Aucune clé active</div>'}</div>
          <div class="flex-row">
            <button onclick="suspendProvider('${p.provider}')" ${suspended?'disabled':''}>⏸ Suspendre 1h</button>
            <button onclick="skipProvider('${p.provider}')">⏭ Clé suivante</button>
            ${suspended ? `<button class="primary" onclick="resumeProvider('${p.provider}')">▶ Réactiver</button>` : ''}
          </div>
        </div>`;
    }).join('');

    const sec = data.security || {};
    const metrics = sec.metrics || {};
    const blockedEntries = Object.entries(sec.blocked_clients || {});
    const blockedHtml = blockedEntries.length
      ? blockedEntries.map(([client, until]) => `<div style="font-size:11.5px; color:var(--text-dim)"><span class="mono">${client}</span> bloqué jusqu'à <span class="mono">${until}</span></div>`).join('')
      : '<div style="font-size:11.5px; color:var(--text-muted)">Aucun client bloqué actuellement</div>';

    document.getElementById('securityCard').innerHTML = `
      <div class="grid-3" style="margin-bottom:12px">
        <div class="card stat-kpi" style="background:var(--surface2)">
          <div class="stat-kpi-label">🔐 Auth header requis</div>
          <div class="stat-kpi-val" style="font-size:18px; color:${sec.require_auth_header ? 'var(--green)' : 'var(--text-dim)'}">${sec.require_auth_header ? 'ON' : 'OFF'}</div>
        </div>
        <div class="card stat-kpi" style="background:var(--surface2)">
          <div class="stat-kpi-label">🛡 Protection brute-force</div>
          <div class="stat-kpi-val" style="font-size:18px; color:${sec.auth_bruteforce_protection ? 'var(--green)' : 'var(--text-dim)'}">${sec.auth_bruteforce_protection ? 'ON' : 'OFF'}</div>
        </div>
        <div class="card stat-kpi" style="background:var(--surface2)">
          <div class="stat-kpi-label">⛔ Clients bloqués</div>
          <div class="stat-kpi-val" style="font-size:18px; color:${(sec.blocked_clients_count || 0) > 0 ? 'var(--red)' : 'var(--green)'}">${(sec.blocked_clients_count || 0).toLocaleString()}</div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin-bottom:10px">
        <div style="font-size:11.5px; color:var(--text-dim)">Échecs token: <span class="mono" style="color:var(--text)">${(metrics.invalid_token_failures_total || 0).toLocaleString()}</span></div>
        <div style="font-size:11.5px; color:var(--text-dim)">Blocages déclenchés: <span class="mono" style="color:var(--text)">${(metrics.auth_blocks_triggered_total || 0).toLocaleString()}</span></div>
        <div style="font-size:11.5px; color:var(--text-dim)">Hits sur blocage: <span class="mono" style="color:var(--text)">${(metrics.auth_block_hits_total || 0).toLocaleString()}</span></div>
        <div style="font-size:11.5px; color:var(--text-dim)">Resets auth OK: <span class="mono" style="color:var(--text)">${(metrics.auth_success_resets_total || 0).toLocaleString()}</span></div>
      </div>

      <div style="font-size:11px; color:var(--text-muted); margin-bottom:6px">Paramètres actifs: limite <span class="mono">${sec.invalid_token_limit_per_minute ?? '-'} / min</span>, fenêtre <span class="mono">${sec.invalid_token_window_seconds ?? '-'}s</span>, blocage <span class="mono">${sec.invalid_token_block_seconds ?? '-'}s</span></div>
      <div style="display:flex; flex-direction:column; gap:4px">${blockedHtml}</div>
    `;

    const sug = data.suggestions || [];
    document.getElementById('suggestions').innerHTML = sug.length ? sug.map((s, i) => `
      <div class="suggestion-banner">
        <span style="font-size:16px">💡</span>
        <div style="flex:1">
          <div style="font-size:12.5px; font-weight:700; color:var(--accent)">Suggestion de performance</div>
          <div style="font-size:12px; color:var(--text-dim); margin-top:2px">Pour le profil <b>${s.profile}</b>, <b>${s.suggested}</b> est plus performant que <b>${s.current}</b> actuellement.</div>
        </div>
        <button class="primary" onclick="applySuggestion(${i})">Appliquer</button>
        <button onclick="dismissSuggestion(${i})">Ignorer</button>
      </div>`).join('') : '';
  }

  /* ─── LOGS ─── */
  async function refreshLogs() {
    const data = await api('/api/logs');
    logsCache = data.items || [];
    renderLogs();
  }

  function renderLogs() {
    const needle = (document.getElementById('logSearch')?.value || '').toLowerCase();
    const filtered = logsCache.filter(l => !needle || JSON.stringify(l).toLowerCase().includes(needle));
    document.getElementById('logs').innerHTML = filtered.length
      ? filtered.map(l => {
          const cls = l.level === 'error' ? 'err' : l.level === 'rotation' ? 'warn' : l.level === 'system' ? 'sys' : 'ok';
          return `<div>[${l.time}] [${l.profile||'sys'}] [${l.provider||'—'}] ${l.model||''} → <span class="${cls}">${l.message}</span></div>`;
        }).join('')
      : '<div style="color:var(--text-muted); padding:20px; text-align:center">Aucune activité récente</div>';
  }

  /* ─── STATS ─── */
  async function refreshStats() {
    const period = document.getElementById('statsRange')?.value || 'today';
    const data = await api(`/api/stats?period=${period}`);
    document.getElementById('kpi').innerHTML = [
      { label: 'Total requêtes', val: data.totals?.total || 0, icon: '📥' },
      { label: 'Succès',         val: data.totals?.success || 0, icon: '✅', color: 'var(--green)' },
      { label: 'Échecs',         val: data.totals?.failed || 0, icon: '❌', color: 'var(--red)' },
    ].map(k => `
      <div class="card stat-kpi">
        <div class="stat-kpi-label">${k.icon} ${k.label}</div>
        <div class="stat-kpi-val" style="${k.color?'color:'+k.color:''}">${k.val.toLocaleString()}</div>
      </div>`).join('');
    const ctxP = document.getElementById('chartProviders');
    const ctxR = document.getElementById('chartProfiles');
    if (charts.providers) charts.providers.destroy();
    if (charts.profiles) charts.profiles.destroy();
    const chartOpts = {
      plugins:{ legend:{ labels:{ color:'#888', font:{ family:'Syne', size:11 } } } },
      scales:{
        x:{ ticks:{ color:'#555', font:{ family:'JetBrains Mono' } }, grid:{ color:'rgba(255,255,255,0.04)' } },
        y:{ ticks:{ color:'#555', font:{ family:'JetBrains Mono' } }, grid:{ color:'rgba(255,255,255,0.04)' } }
      }
    };
    charts.providers = new Chart(ctxP, { type:'bar', data:{ labels:Object.keys(data.by_provider||{}), datasets:[{ label:'Requêtes', data:Object.values(data.by_provider||{}), backgroundColor:'rgba(245,158,11,0.55)', borderColor:'#f59e0b', borderWidth:1, borderRadius:5 }] }, options:chartOpts });
    charts.profiles  = new Chart(ctxR, { type:'doughnut', data:{ labels:Object.keys(data.by_profile||{}), datasets:[{ data:Object.values(data.by_profile||{}), backgroundColor:['#f59e0b','#10b981','#6366f1','#ef4444','#a78bfa','#38bdf8','#34d399'], borderWidth:0 }] }, options:{ plugins:{ legend:{ labels:{ color:'#888', font:{ family:'Syne' } } } }, cutout:'68%' } });
  }

  /* ─── PRESETS ─── */
  function buildPresetDraft(data) {
    presetDraft = data || { profiles: {} };
    ['coding','reasoning','chat','long','vision','audio','translate'].forEach(p => {
      if (!presetDraft.profiles[p]) presetDraft.profiles[p] = { models: [], lock_top: false };
    });
  }

  function renderPresetEditor() {
    const editor = document.getElementById('presetEditor');
    const profileEmojis = { coding:'💻', reasoning:'🧠', chat:'💬', long:'📄', vision:'👁️', audio:'🎵', translate:'🌍' };

    // Gather all known model names from catalog + ollama cache
    let allModels = Object.values(modelsCatalog).flat().map(m => m.model);
    if (allModels.length === 0 && ollamaModelsCache.length > 0) {
      allModels = ollamaModelsCache.map(m => m.name);
    }
    // Also include models already in the preset draft that may not be in catalog
    const presetModels = Object.values(presetDraft.profiles).flatMap(p => p.models || []);
    const allModelSet = new Set([...allModels, ...presetModels]);
    const modelOptions = [...allModelSet].sort().map(m => `<option value="${m}">${m}</option>`).join('');
    const emptyNotice = allModelSet.size === 0
      ? '<div style="font-size:11px; color:var(--amber); padding:6px 0">⚠ Aucun modèle disponible. Chargez le catalogue ou ajoutez des providers dans la configuration.</div>'
      : '';

    editor.innerHTML = emptyNotice + ['coding','reasoning','chat','long','vision','audio','translate'].map(p => {
      const items = presetDraft.profiles[p].models.map((m, i) => `
        <div class="drag-item" draggable="true" ondragstart="onDragStart('${p}', ${i})" ondrop="onDrop('${p}', ${i})" ondragover="event.preventDefault()">
          <span class="drag-handle">⠿</span>
          <span style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono)">${i+1}.</span>
          <span class="drag-model">${m}</span>
          <button onclick="removeModel('${p}', ${i})" class="ghost" style="padding:3px 6px; font-size:11px">✕</button>
        </div>`).join('');
      return `
        <div style="margin-bottom:14px">
          <div style="font-size:10px; font-weight:700; color:var(--text-dim); text-transform:uppercase; letter-spacing:.8px; margin-bottom:6px">${profileEmojis[p]||'⚡'} ${p}</div>
          ${items || '<div style="font-size:11px; color:var(--text-muted); padding:8px 0">Aucun modèle ajouté</div>'}
          <div class="flex-row" style="margin-top:6px">
            <select id="add-${p}" style="flex:1; font-size:12px; width:auto">${modelOptions}</select>
            <button onclick="addModel('${p}')" style="font-size:12px">+ Ajouter</button>
            <label style="font-size:11px; color:var(--text-dim); display:flex; align-items:center; gap:5px; cursor:pointer; white-space:nowrap"><input type="checkbox" ${presetDraft.profiles[p].lock_top?'checked':''} onchange="toggleLock('${p}', this.checked)" style="width:auto"/> Lock top</label>
          </div>
        </div>`;
    }).join('');
  }

  async function loadPresets() {
    const data = await api('/api/presets');
    document.getElementById('presetList').innerHTML = data.items.map(p => `
      <div class="preset-card">
        <div style="display:flex; justify-content:space-between; align-items:flex-start">
          <div>
            <div class="preset-title">${p.name}</div>
            <div class="preset-desc">${p.description || ''}</div>
          </div>
          <div class="flex-row" style="gap:4px; flex-shrink:0">
            <button onclick="applyPreset(${p.id})" class="primary" style="font-size:11px; padding:5px 10px">▶ Appliquer</button>
            <button onclick="editPreset(${p.id})" class="ghost" style="font-size:11px; padding:5px 8px">✏️</button>
            <button onclick="deletePreset(${p.id})" class="danger" style="font-size:11px; padding:5px 8px">🗑</button>
          </div>
        </div>
      </div>`).join('') || '<div style="color:var(--text-muted); font-size:12px; padding:12px 0">Aucun preset sauvegardé. Créez-en un !</div>';
    if (data.items.length) {
      buildPresetDraft(data.items[0].data);
      document.getElementById('presetName').value = data.items[0].name;
      document.getElementById('presetDesc').value = data.items[0].description || '';
      renderPresetEditor();
    }
  }

  function onDragStart(profile, index) { event.dataTransfer.setData('text/plain', `${profile}:${index}`); }
  function onDrop(profile, index) {
    const [p, i] = event.dataTransfer.getData('text/plain').split(':');
    if (p !== profile) return;
    const list = presetDraft.profiles[profile].models;
    const item = list.splice(parseInt(i, 10), 1)[0];
    list.splice(index, 0, item);
    renderPresetEditor();
  }
  function addModel(profile) { const sel = document.getElementById(`add-${profile}`); presetDraft.profiles[profile].models.push(sel.value); renderPresetEditor(); }
  function removeModel(profile, index) { presetDraft.profiles[profile].models.splice(index, 1); renderPresetEditor(); }
  function toggleLock(profile, value) { presetDraft.profiles[profile].lock_top = value; }

  async function editPreset(id) {
    const data = await api('/api/presets'); const preset = data.items.find(p => p.id === id); if (!preset) return;
    document.getElementById('presetName').value = preset.name;
    document.getElementById('presetDesc').value = preset.description || '';
    buildPresetDraft(preset.data); renderPresetEditor();
  }

  /* ─── CONFIG ─── */
  async function loadConfig() {
    const data = await api('/api/config');
    document.getElementById('configEditor').value = data.content || '';
    if (configEditorMode === 'locked') setConfigStatus('Configuration chargée. Zone YAML verrouillée.', 'info');
  }

  async function saveConfig() {
    if (configEditorMode !== 'edit') { setConfigStatus('Déverrouillez en mode Modifier pour sauvegarder.', 'error'); return; }
    await api('/api/config', 'POST', { content: document.getElementById('configEditor').value });
    await refreshRouting();
    setConfigStatus('Configuration sauvegardée et rechargée.', 'success');
  }

  async function applyQuickConfig() { await saveConfig(); }

  async function loadReadme(force = false) {
    if (readmeLoaded && !force) return;
    const boxes = Array.from(document.querySelectorAll('#readmeContent, .readme-box, .doc-readme-raw'));
    boxes.forEach(b => { if (b) b.textContent = 'Chargement du README...'; });
    try {
      const data = await api('/api/readme');
      if (!data.exists) { boxes.forEach(b => { if (b) b.textContent = 'README.md introuvable dans le projet.'; }); return; }
      const content = data.content || 'README vide.';
      boxes.forEach(b => { if (b) b.textContent = content; });
      readmeLoaded = true;
    } catch (err) { boxes.forEach(b => { if (b) b.textContent = `Erreur de chargement README: ${err.message}`; }); }
  }

  function openReadmeFromDrawer() {
    showTab('docs');
    showDocsSection('readme');
    loadReadme();
  }

  /* ─── BACKUPS / MAINTENANCE ─── */
  function formatBackupSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  async function loadMaintenanceSettings() {
    try {
      const data = await api('/api/maintenance/settings');
      const settings = data.settings || {};
      const autoBackup = document.getElementById('autoBackupOnShutdown');
      const autoRestore = document.getElementById('autoRestoreLatestOnStartup');
      if (autoBackup) autoBackup.checked = !!settings.auto_backup_on_shutdown;
      if (autoRestore) autoRestore.checked = !!settings.auto_restore_latest_on_startup;
    } catch (err) {
      setMaintenanceStatus(`Chargement options maintenance impossible: ${err.message}`, 'error');
    }
  }

  async function saveMaintenanceSettings() {
    const autoBackup = !!document.getElementById('autoBackupOnShutdown')?.checked;
    const autoRestore = !!document.getElementById('autoRestoreLatestOnStartup')?.checked;
    setMaintenanceStatus('Enregistrement des options maintenance...');
    try {
      await api('/api/maintenance/settings', 'POST', {
        auto_backup_on_shutdown: autoBackup,
        auto_restore_latest_on_startup: autoRestore,
      });
      setMaintenanceStatus('✅ Options maintenance enregistrées.', 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Enregistrement options impossible: ${err.message}`, 'error');
    }
  }

  async function loadBackups() {
    const box = document.getElementById('backupList');
    if (!box) return;
    await loadMaintenanceSettings();
    box.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Chargement des snapshots...</div>';
    try {
      const data = await api('/api/maintenance/backups');
      const items = data.items || [];
      const pendingRestore = data.pending_restore || null;
      if (!items.length) {
        box.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Aucun snapshot trouvé.</div>';
        if (pendingRestore) {
          const target = pendingRestore === '__LATEST__' ? 'dernier backup disponible' : pendingRestore;
          setMaintenanceStatus(`Restauration planifiée au prochain démarrage: ${target}`, 'warn');
        } else {
          setMaintenanceStatus('Aucun snapshot disponible.', 'info');
        }
        return;
      }
      box.innerHTML = items.map(item => `
        <div style="display:grid; grid-template-columns:1fr auto auto auto auto; gap:8px; align-items:center; background:var(--surface2); border:1px solid var(--border); border-radius:var(--r-sm); padding:9px 12px">
          <div>
            <div style="font-family:var(--font-mono); font-size:12px; font-weight:500; color:#fff">${escapeHtml(item.name || '')}</div>
            <div style="font-size:11px; color:var(--text-dim); margin-top:2px">${escapeHtml(item.created_at || '')} · ${formatBackupSize(item.size_bytes || 0)}</div>
          </div>
          <button onclick="restoreBackupByName('${escapeHtml(item.name || '')}')" style="font-size:11px; padding:6px 10px">♻ Restaurer</button>
          <button onclick="scheduleRestoreBackupByName('${escapeHtml(item.name || '')}')" style="font-size:11px; padding:6px 10px">⏭ Au démarrage</button>
          <button onclick="copyText('${escapeHtml(item.path || '')}', this)" style="font-size:11px; padding:6px 10px">📋 Chemin</button>
          <button class="danger" onclick="deleteBackupByName('${escapeHtml(item.name || '')}')" style="font-size:11px; padding:6px 10px">🗑 Supprimer</button>
        </div>`).join('');
      if (pendingRestore) {
        const target = pendingRestore === '__LATEST__' ? 'dernier backup disponible' : pendingRestore;
        setMaintenanceStatus(`${items.length} snapshot(s) · restauration planifiée: ${target}`, 'warn');
      } else {
        setMaintenanceStatus(`${items.length} snapshot(s) disponible(s).`, 'success');
      }
    } catch (err) {
      box.innerHTML = `<div style="font-size:12px; color:var(--red)">Erreur backups: ${escapeHtml(err.message || '')}</div>`;
      setMaintenanceStatus(`Chargement backups impossible: ${err.message}`, 'error');
    }
  }

  async function createBackupNow() {
    setMaintenanceStatus('Création du snapshot en cours...');
    try {
      const res = await api('/api/maintenance/backup', 'POST', {});
      await loadBackups();
      setMaintenanceStatus(`✅ Snapshot créé: ${res.backup?.name || 'ok'}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Backup impossible: ${err.message}`, 'error');
    }
  }

  async function restoreLatestBackup() {
    if (!confirm('Restaurer le dernier backup disponible ?')) return;
    setMaintenanceStatus('Restauration du dernier backup...');
    try {
      const res = await api('/api/maintenance/restore', 'POST', {});
      await loadBackups();
      await loadProjects();
      await loadPresets();
      await loadSchedules();
      await refreshRouting();
      await refreshLogs();
      await refreshStats();
      setMaintenanceStatus(`✅ Backup restauré: ${res.restored?.name || 'ok'}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Restauration impossible: ${err.message}`, 'error');
    }
  }

  async function scheduleRestoreLatestBackup() {
    if (!confirm('Planifier la restauration du dernier backup au prochain démarrage ?')) return;
    setMaintenanceStatus('Planification en cours...');
    try {
      const res = await api('/api/maintenance/restore-next', 'POST', {});
      await loadBackups();
      setMaintenanceStatus(`✅ ${res.message || 'Restauration planifiée.'}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Planification impossible: ${err.message}`, 'error');
    }
  }

  async function restoreBackupByName(name) {
    if (!name) return;
    if (!confirm(`Restaurer ce backup ?\n${name}`)) return;
    setMaintenanceStatus(`Restauration en cours: ${name}...`);
    try {
      const res = await api('/api/maintenance/restore', 'POST', { name });
      await loadBackups();
      await loadProjects();
      await loadPresets();
      await loadSchedules();
      await refreshRouting();
      await refreshLogs();
      await refreshStats();
      setMaintenanceStatus(`✅ Backup restauré: ${res.restored?.name || name}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Restauration impossible: ${err.message}`, 'error');
    }
  }

  async function scheduleRestoreBackupByName(name) {
    if (!name) return;
    if (!confirm(`Planifier ce backup au prochain démarrage ?\n${name}`)) return;
    setMaintenanceStatus(`Planification en cours: ${name}...`);
    try {
      const res = await api('/api/maintenance/restore-next', 'POST', { name });
      await loadBackups();
      setMaintenanceStatus(`✅ ${res.message || 'Restauration planifiée.'}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Planification impossible: ${err.message}`, 'error');
    }
  }

  async function deleteBackupByName(name) {
    if (!name) return;
    if (!confirm(`Supprimer définitivement ce backup ?\n${name}`)) return;
    setMaintenanceStatus(`Suppression en cours: ${name}...`);
    try {
      await api(`/api/maintenance/backups/${encodeURIComponent(name)}`, 'DELETE');
      await loadBackups();
      setMaintenanceStatus(`✅ Backup supprimé: ${name}`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Suppression impossible: ${err.message}`, 'error');
    }
  }

  async function purgeDataBeforeDate() {
    const beforeDate = document.getElementById('purgeBeforeDate')?.value || '';
    if (!beforeDate) { setMaintenanceStatus('Sélectionnez une date avant purge.', 'warn'); return; }
    if (!confirm(`Purger les données historiques avant ${beforeDate} ?`)) return;
    const createBackup = !!document.getElementById('maintenanceAutoBackup')?.checked;
    setMaintenanceStatus('Purge en cours...');
    try {
      const res = await api('/api/maintenance/purge-before', 'POST', { before_date: beforeDate, create_backup: createBackup });
      await loadBackups();
      await refreshStats();
      await refreshRouting();
      setMaintenanceStatus(`✅ Purge terminée (${res.deleted?.total || 0} lignes supprimées).`, 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Purge impossible: ${err.message}`, 'error');
    }
  }

  async function resetAllData() {
    const confirmed = confirm('⚠️ Cette action va réinitialiser toutes les données DB (quotas, stats, presets, projets, historiques). Continuer ?');
    if (!confirmed) return;
    const createBackup = !!document.getElementById('maintenanceAutoBackup')?.checked;
    setMaintenanceStatus('Réinitialisation totale en cours...');
    try {
      await api('/api/maintenance/reset-all', 'POST', { create_backup: createBackup });
      await loadBackups();
      await loadProjects();
      await loadPresets();
      await loadSchedules();
      await refreshRouting();
      await refreshLogs();
      await refreshStats();
      setMaintenanceStatus('✅ Réinitialisation terminée.', 'success');
    } catch (err) {
      setMaintenanceStatus(`❌ Réinitialisation impossible: ${err.message}`, 'error');
    }
  }

  /* ─── SCHEDULES ─── */
  async function addSchedule() {
    await api('/api/schedules', 'POST', {
      name: document.getElementById('schedName').value,
      action: document.getElementById('schedAction').value,
      target: document.getElementById('schedTarget').value,
      value: document.getElementById('schedValue').value,
      time_start: document.getElementById('schedStart').value,
      time_end: document.getElementById('schedEnd').value,
      days_of_week: document.getElementById('schedDays').value,
      active: true,
    });
    await loadSchedules();
  }

  async function loadSchedules() {
    const data = await api('/api/schedules');
    document.getElementById('scheduleList').innerHTML = data.items.map(s => `
      <div class="schedule-item">
        <span style="font-size:14px">🕐</span>
        <div style="flex:1">
          <div class="schedule-name">${s.name}</div>
          <div class="schedule-meta">${s.action} → ${s.target} · ${s.time_start}–${s.time_end} (${s.days_of_week})</div>
        </div>
        <span class="badge ${s.active ? 'green' : ''}">${s.active ? 'Actif' : 'Inactif'}</span>
      </div>`).join('') || '<div style="font-size:12px; color:var(--text-muted)">Aucune planification configurée</div>';
  }

  /* ─── TESTS ─── */
  function renderTests(items) {
    document.getElementById('testsList').innerHTML = items.map(t => {
      const icon = t.status === 'pass' ? '✅' : t.status === 'fail' ? '❌' : t.status === 'skip' ? '⏭️' : '⬜';
      return `
        <div class="test-item">
          <span class="test-icon">${icon}</span>
          <div style="flex:1">
            <div class="test-name">${t.name}</div>
            <div class="test-desc">${t.description || ''}</div>
          </div>
          <span class="test-status ${t.status||'ready'}">${t.status === 'pass' ? 'PASS' : t.status === 'fail' ? 'FAIL' : t.status === 'skip' ? 'SKIP' : 'READY'}</span>
          ${t.duration ? `<span style="font-size:11px; color:var(--text-muted); margin-left:8px; font-family:var(--font-mono)">${t.duration}ms</span>` : ''}
        </div>`;
    }).join('');
  }

  /* ─── LOCK MODAL ─── */
  async function openLockModal(profile) {
    lockProfile = profile;
    document.getElementById('lockTitle').innerText = `Verrouiller un modèle — ${profile.toUpperCase()}`;
    document.getElementById('lockModal').classList.add('active');
    renderLockList();
  }
  function closeLockModal() { document.getElementById('lockModal').classList.remove('active'); }
  async function unlockProfile() { await api(`/api/lock/${lockProfile}`, 'DELETE'); closeLockModal(); refreshRouting(); }

  function renderLockList() {
    const q = (document.getElementById('lockSearch')?.value || '').toLowerCase();
    const list = [];
    Object.entries(modelsCatalog).forEach(([provider, models]) => {
      models.forEach(m => {
        if (!q || m.model.toLowerCase().includes(q)) {
          list.push(`
            <div style="display:flex; align-items:center; gap:10px; padding:10px 12px; background:var(--surface2); border:1px solid var(--border); border-radius:var(--r)">
              <span style="font-size:12px">${providerEmoji(provider)}</span>
              <div style="flex:1">
                <div style="font-family:var(--font-mono); font-size:12px; font-weight:600; color:#fff">${m.model}</div>
                <div style="font-size:11px; color:var(--text-muted)">${provider} · ${m.context || '—'}</div>
              </div>
              <button class="primary" onclick="lockModel('${m.model}')" style="font-size:11px; padding:5px 10px">🔒 Verrouiller</button>
            </div>`);
        }
      });
    });
    document.getElementById('lockList').innerHTML = list.join('') || '<div style="color:var(--text-muted); font-size:12px; padding:12px 0">Aucun modèle trouvé</div>';
  }

  async function lockModel(model) { await api('/api/lock', 'POST', { profile: lockProfile, model }); closeLockModal(); refreshRouting(); }

  /* ─── ACTIONS ─── */
  async function forceProfile(profile, provider) { await api('/api/override/force', 'POST', { profile, provider }); await refreshRouting(); }
  async function suspendProvider(provider)        { await api('/api/suspend', 'POST', { provider, duration_minutes: 60 }); await refreshRouting(); }
  async function resumeProvider(provider)         { await api('/api/resume', 'POST', { provider }); await refreshRouting(); }
  async function skipProvider(provider)           { await api('/api/skip', 'POST', { profile: 'chat' }); }
  async function pauseAll()                       { await api('/api/pause', 'POST'); if (window.showToast) showToast('Proxy en pause', 'warning'); }
  async function resumeAll()                      { await api('/api/resume', 'POST'); if (window.showToast) showToast('Proxy repris', 'success'); }
  async function reloadConfig()                   { await api('/api/reload-config', 'POST'); await refreshRouting(); if (window.showToast) showToast('Config rechargée', 'success'); }
  async function applyPreset(id)                  { await api(`/api/presets/${id}/apply`, 'POST'); await refreshRouting(); }
  async function deletePreset(id)                 { await api(`/api/presets/${id}`, 'DELETE'); await loadPresets(); }
  async function newPreset()                      { document.getElementById('presetName').value = ''; document.getElementById('presetDesc').value = ''; buildPresetDraft(null); renderPresetEditor(); }
  async function savePreset()                     { await api('/api/presets', 'POST', { name: document.getElementById('presetName').value, description: document.getElementById('presetDesc').value, data: presetDraft }); await loadPresets(); }
  async function applyPresetTemp() {
    // Save as temp preset and apply it
    const name = document.getElementById('presetName').value || 'Temp';
    const desc = document.getElementById('presetDesc').value || 'Appliqué sans sauvegarde';
    const res = await api('/api/presets', 'POST', { name, description: desc, data: presetDraft });
    if (res.id) await api(`/api/presets/${res.id}/apply`, 'POST');
    await loadPresets();
    await refreshRouting();
  }
  async function applySuggestion(i)               { await api(`/api/suggestions/${i}/apply`, 'POST'); refreshRouting(); }
  async function dismissSuggestion(i)             { await api(`/api/suggestions/${i}/dismiss`, 'POST'); refreshRouting(); }
  async function runAllTests()                    { const res = await api('/api/tests/run', 'POST'); renderTests(res.results); }
  async function exportTestResults()              { const res = await api('/api/tests/results'); const blob = new Blob([JSON.stringify(res,null,2)]); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='tests.json'; a.click(); }
  async function startBenchmark()                 { await api('/api/benchmark/start', 'POST', {}); }
  async function stopBenchmark()                  { await api('/api/benchmark/stop', 'POST'); }
  async function exportStats()                    { const res = await fetch('/api/stats/export'); const csv = await res.text(); const blob = new Blob([csv], {type:'text/csv'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='stats.csv'; a.click(); }
  async function exportLogs()                     { const data = await api('/api/logs/export'); const blob = new Blob([JSON.stringify(data.items,null,2)], {type:'application/json'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='rotator-logs.json'; a.click(); }
  function clearLogs()                            { logsCache = []; renderLogs(); }

  async function runCompare() {
    const prompt = document.getElementById('comparePrompt').value;
    const models = [document.getElementById('compareM1').value, document.getElementById('compareM2').value, document.getElementById('compareM3').value].filter(Boolean);
    const res = await api('/api/compare', 'POST', { prompt, models });
    document.getElementById('compareResults').innerHTML = res.results.map(r => `
      <div class="card">
        <div style="font-family:var(--font-mono); font-size:12px; font-weight:600; color:#fff; margin-bottom:4px">${r.model}</div>
        <div style="font-size:11px; color:var(--text-muted); margin-bottom:10px; font-family:var(--font-mono)">${r.elapsed_ms||'—'}ms</div>
        <div style="font-size:12px; color:var(--text); line-height:1.5; max-height:200px; overflow:auto">${JSON.stringify(r.response||r.error||'').slice(0,400)}</div>
        <button class="primary" style="margin-top:10px; width:100%" onclick="voteModel('${r.model}')">👍 Préférer ce modèle</button>
      </div>`).join('');
  }

  async function voteModel(model) {
    const models = [document.getElementById('compareM1').value, document.getElementById('compareM2').value];
    await api('/api/compare/vote', 'POST', { profile: 'chat', model_a: models[0], model_b: models[1], winner: model });
  }
