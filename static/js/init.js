  /* ─── INIT ─── */
  async function init() {
    // Show welcome toggle button (routing is default tab)
    const toggleBtn = document.getElementById('welcomeToggleBtn');
    if (toggleBtn) toggleBtn.style.display = 'flex';
    try { await checkOllama(); } catch {}
    try { await loadModels(); } catch {}
    try { await loadPresets(); } catch {}
    try { await loadConfig(); } catch {}
    applyConfigEditorMode('locked');
    try { await loadReadme(); } catch {}
    try { await loadMaintenanceSettings(); } catch {}
    try { await loadBackups(); } catch {}
    try { await loadKeysCenter(); } catch {}
    try { await loadKeyTestCenter(); } catch {}
    try { await loadProjects(); } catch {}
    try { await loadSchedules(); } catch {}
    try { ccInitSkills(); ccUpdateSkillsPreview(); } catch {}
    try { await refreshRouting(); } catch {}
    try { await refreshLogs(); } catch {}
    try { await refreshStats(); } catch {}
    try {
      const tests = await api('/api/tests');
      renderTests(tests.items.map(t => ({ ...t, status: 'ready' })));
    } catch {}
  }

  init();
  setInterval(refreshRouting, 15000);
  setInterval(refreshLogs, 5000);
  setInterval(refreshStats, 60000);