  /* ─── CLAUDE CODE ─── */
  let ccSessionsCache = [];
  let ccBrowseCache = [];
  let ccBrowseProfiles = {};

  function showCCTab(name) {
    document.querySelectorAll('.cc-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.cc-section').forEach(s => s.style.display = 'none');
    document.querySelector(`.cc-tab[onclick="showCCTab('${name}')"]`).classList.add('active');
    document.getElementById(`cc-${name}`).style.display = 'block';

    if (name === 'connect') ccLoadConnect();
    if (name === 'browse') ccLoadBrowse();
    if (name === 'models') ccLoadModels();
    if (name === 'sessions') ccLoadSessions();
  }

  async function ccLoadConnect() {
    try {
      const cfg = await api('/api/config');
      const port = cfg.settings?.port || 47822;
      document.getElementById('ccPort').innerText = port;
    } catch {}

    try {
      const data = await api('/api/projects');
      const sel = document.getElementById('ccExistingToken');
      sel.innerHTML = '<option value="">— Choisir un token —</option>';
      (data.items || []).filter(p => p.active).forEach(p => {
        sel.innerHTML += `<option value="${p.token}">${p.name} (${p.policy})</option>`;
      });

      const claude = (data.items || []).filter(p => p.active && p.policy === 'coding_only');
      const list = document.getElementById('ccActiveList');
      if (claude.length === 0) {
        list.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center">Aucune session Claude active. Créez-en une ci-dessus.</div>';
      } else {
        list.innerHTML = claude.map(p => `
          <div style="display:flex; align-items:center; gap:12px; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:var(--r); margin-bottom:6px">
            <div style="flex:1">
              <div style="font-weight:700; font-size:13px; color:#fff">${p.name}</div>
              <div style="font-size:11px; color:var(--text-dim); margin-top:2px; font-family:var(--font-mono)">
                Token: ${p.token.slice(0,16)}... · Quota: ${p.daily_limit || '∞'}/jour · Utilisé: ${p.used_today || 0}
              </div>
            </div>
            <button onclick="ccLaunchExisting('${p.token}')" style="font-size:11px; padding:5px 10px">▶ Lancer</button>
            <button class="danger" onclick="ccRevoke(${p.id})" style="font-size:11px; padding:5px 10px">✕</button>
          </div>
        `).join('');
      }
    } catch {}
  }

  let _ccPendingLaunch = null;

  async function ccLaunchSession() {
    const st = document.getElementById('ccLaunchStatus');
    st.className = 'status-line';

    // -- If no work dir, prompt for one --
    let workDir = document.getElementById('ccWorkDir').value.trim();
    if (!workDir) {
      workDir = prompt('📁 Dans quel dossier voulez-vous lancer Claude Code ?\n\nExemple : D:\\Projects\\myapp\n\n(Laissez vide pour le dossier du rotator)');
      if (workDir === null) { st.innerText = '❌ Annulé.'; return; }
      workDir = workDir.trim();
      if (workDir) document.getElementById('ccWorkDir').value = workDir;
    }

    st.innerText = '⏳ Création du token...';

    try {
      const name = document.getElementById('ccProjectName').value.trim() || undefined;
      const daily_limit = document.getElementById('ccDailyLimit').value || undefined;
      const res = await api('/api/projects/claude-onboarding', 'POST', { name, daily_limit });
      if (!res.ok) throw new Error(res.detail || 'Erreur');

      st.innerText = '✅ Token créé : ' + res.project.token.slice(0, 20) + '...';
      st.className = 'status-line ok';

      // -- Show model choice modal --
      _ccPendingLaunch = { token: res.project.token, workDir };
      ccShowModelModal();

    } catch (err) {
      st.innerText = '❌ ' + err.message;
      st.className = 'status-line err';
    }
  }

  async function ccShowModelModal() {
    const sel = document.getElementById('ccModelModalSelect');
    sel.innerHTML = '<option value="">⏳ Chargement...</option>';
    document.getElementById('ccModelModal').classList.add('active');

    try {
      const data = await api('/v1/models');
      const models = (data.data || []).filter(m => (m.profiles || []).includes('coding') || m.owned_by === 'profile');
      sel.innerHTML = '<option value="">— Choisir un modèle —</option>';
      models.forEach(m => {
        if (m.id === 'coding') return; // skip the profile itself since there's a dedicated button
        const prov = m.owned_by || '';
        sel.innerHTML += `<option value="${m.id}">${m.id}${prov && prov !== 'profile' ? ' (' + prov + ')' : ''}</option>`;
      });
    } catch {
      sel.innerHTML = '<option value="">Erreur de chargement</option>';
    }
  }

  function ccCloseModelModal() {
    document.getElementById('ccModelModal').classList.remove('active');
  }

  // --- Confirmation modal helper ---
  function closeConfirmModal() {
    const m = document.getElementById('confirmModal');
    if (m) m.classList.remove('active');
    const ok = document.getElementById('confirmModalOkBtn');
    if (ok) ok.onclick = null;
  }

  function showConfirm(title, message, confirmLabel, onConfirm) {
    const modal = document.getElementById('confirmModal');
    if (!modal) {
      // Fallback to native confirm if modal missing
      if (window.confirm(message)) onConfirm();
      return;
    }
    document.getElementById('confirmModalTitle').innerText = title || 'Confirmer';
    document.getElementById('confirmModalBody').innerText = message || '';
    const ok = document.getElementById('confirmModalOkBtn');
    ok.innerText = confirmLabel || 'Confirmer';
    ok.onclick = async () => { closeConfirmModal(); try { await onConfirm(); } catch (err) { alert('❌ ' + err.message); } };
    modal.classList.add('active');
  }

  async function ccPickModel(model) {
    if (!model) { alert('Selectionnez un modele.'); return; }
    ccCloseModelModal();

    const st = document.getElementById('ccLaunchStatus');
    if (!_ccPendingLaunch) return;

    const { token, workDir } = _ccPendingLaunch;
    _ccPendingLaunch = null;

    try {
      const install = document.getElementById('ccInstallClaude').checked;
      await ccInitSkills();
      const skills = Array.from(_skillsSel);
      const installSkills = skills.length > 0;
      await api('/api/projects/claude-onboarding/launch', 'POST', {
        token,
        install_claude: install,
        install_skills: installSkills,
        skills: skills.length ? skills : undefined,
        work_dir: workDir || undefined,
        model,
      });

      st.innerText += ` — Terminal lance ! (modele: ${model}, ${skills.length} skills)`;
      ccLoadConnect();
    } catch (err) {
      st.innerText = '❌ ' + err.message;
      st.className = 'status-line err';
    }
  }

  // ═══════════════════════════════════════════════════
  //  CREATE PROJECT ONLY (sans lancer) — copier la commande
  // ═══════════════════════════════════════════════════

  let _lastGeneratedCmd = { ps: '', bash: '' };

  async function ccCreateProjectOnly() {
    const st = document.getElementById('ccLaunchStatus');
    st.className = 'status-line';
    st.innerText = '⏳ Création du projet...';

    try {
      const name = document.getElementById('ccProjectName').value.trim() || undefined;
      const daily_limit = document.getElementById('ccDailyLimit').value || undefined;
      const res = await api('/api/projects/claude-onboarding', 'POST', { name, daily_limit });
      if (!res.ok) throw new Error(res.detail || 'Erreur');

      const token = res.project.token;
      const port = res.env?.ANTHROPIC_BASE_URL?.match(/:([0-9]+)$/)?.[1] || '47822';
      const workDir = document.getElementById('ccWorkDir').value.trim();

      // Récupérer les skills sélectionnées
      await ccInitSkills();
      const skills = Array.from(_skillsSel);

      // Construire la commande PowerShell
      const rotPath = (res.rotator_path || _getRotatorPath()).replace(/\\/g, '\\');
      let ps = '';
      if (workDir) ps += `cd '${workDir.replace(/'/g, "''")}'\n`;
      ps += `$env:ANTHROPIC_BASE_URL='http://localhost:${port}'\n`;
      ps += `$env:ANTHROPIC_AUTH_TOKEN='${token}'\n`;

      if (skills.length > 0) {
        const skillsJson = JSON.stringify(skills).replace(/'/g, "''");
        ps += `\n# --- Avec ${skills.length} skill(s) ---\n`;
        ps += `powershell -ExecutionPolicy Bypass -File '${rotPath}\\connect_claude.ps1' -Token '${token}'`;
        if (workDir) ps += ` -WorkDir '${workDir.replace(/'/g, "''")}'`;
        ps += ` -InstallSkills -SkillsJson '${skillsJson}' -Model coding`;
        ps += `\n\n# --- OU sans skills (lancement direct) ---\n`;
        ps += `# claude --model coding`;
      } else {
        ps += `claude --model coding`;
      }

      // Version Bash
      let bash = '';
      if (workDir) bash += `cd '${workDir}' && `;
      bash += `export ANTHROPIC_BASE_URL='http://localhost:${port}' && `;
      bash += `export ANTHROPIC_AUTH_TOKEN='${token}' && `;
      bash += `claude --model coding`;

      _lastGeneratedCmd = { ps, bash };

      // Afficher
      const box = document.getElementById('ccGeneratedCmdBox');
      document.getElementById('ccGeneratedCmd').textContent = ps;
      const note = document.getElementById('ccGeneratedCmdNote');
      note.innerHTML = `✅ Projet créé : <strong>${res.project.name}</strong> · Token : <code>${token.slice(0,20)}...</code>`;
      if (skills.length > 0) {
        note.innerHTML += `<br>🧩 ${skills.length} skill(s) incluse(s) dans la commande`;
      }
      box.style.display = 'block';
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

      st.innerText = '✅ Projet créé ! Commande prête ci-dessous.';
      st.className = 'status-line ok';
      ccLoadConnect();
    } catch (err) {
      st.innerText = '❌ ' + err.message;
      st.className = 'status-line err';
    }
  }

  function _getRotatorPath() {
    // Best-effort: extract from current page URL or fallback
    return window.__rotatorPath || 'D:\\Project\\rotator';
  }

  function ccCopyGeneratedCmd() {
    navigator.clipboard.writeText(_lastGeneratedCmd.ps).then(() => {
      const btn = document.getElementById('ccCopyGenBtn');
      btn.innerText = '✅ Copié !';
      setTimeout(() => btn.innerText = '📋 Copier la commande', 2000);
    });
  }

  function ccCopyGeneratedCmdBash() {
    navigator.clipboard.writeText(_lastGeneratedCmd.bash).then(() => {
      const btn = document.getElementById('ccCopyGenBashBtn');
      btn.innerText = '✅ Copié (Bash) !';
      setTimeout(() => btn.innerText = '🐧 Bash / Linux / Mac', 2000);
      alert('⚠️ Cette commande est pour Bash (Linux / Mac).\n\nSous Windows PowerShell, utilisez le bouton "📋 Copier la commande".');
    });
  }

  async function ccLaunchExisting(token) {
    const workDir = prompt('📁 Dossier de travail ?\n(Laissez vide pour le dossier du rotator)') || '';
    try {
      await api('/api/projects/claude-onboarding/launch', 'POST', {
        token,
        work_dir: workDir.trim() || undefined,
      });
    } catch (err) {
      alert('❌ ' + err.message);
    }
  }

  async function ccRevoke(projectId) {
    showConfirm('Révoquer token Claude', 'Révoquer ce token Claude ?', 'Révoquer', async () => {
      await api(`/api/projects/${projectId}/revoke`, 'POST');
      ccLoadConnect();
    });
  }

  function ccCopyEnv() {
    const token = document.getElementById('ccExistingToken').value;
    const port = document.getElementById('ccPort').innerText;
    if (!token) { alert('Sélectionnez d\'abord un token.'); return; }
    const text = `$env:ANTHROPIC_BASE_URL="http://localhost:${port}"\n$env:ANTHROPIC_AUTH_TOKEN="${token}"\nclaude --model coding`;
    navigator.clipboard.writeText(text).then(() => alert('✅ Copié !'));
  }

  // ═══════════════════════════════════════════════
  //  SKILLS STORE — Dynamic catalog from /api/skills
  // ═══════════════════════════════════════════════

  let SKILLS_CATALOG = { defaults: [], packs: [], individual: [], excluded: [] };
  let _skillsCatalogLoaded = false;

  async function ccLoadSkillsCatalog() {
    if (_skillsCatalogLoaded) return;
    try {
      const data = await api('/api/skills');
      // Migrate icon field to emoji for rendering compatibility
      const migrateIcon = (s) => { if (s.icon && !s.emoji) s.emoji = s.icon; return s; };
      SKILLS_CATALOG.defaults = (data.defaults || []).map(migrateIcon);
      SKILLS_CATALOG.packs = (data.packs || []).map(p => { p.emoji = p.icon || p.emoji || '📦'; return p; });
      SKILLS_CATALOG.individual = (data.individual || []).map(migrateIcon);
      SKILLS_CATALOG.excluded = data.excluded || [];
      _skillsCatalogLoaded = true;
    } catch (err) {
      console.error('Failed to load skills catalog:', err);
    }
  }

  // ── State ──
  const _skillsSel = new Set();
  let _skillsInited = false;

  function _allSkillIds() {
    const ids = [];
    SKILLS_CATALOG.defaults.forEach(s => ids.push(s.id));
    SKILLS_CATALOG.packs.forEach(p => p.skills.forEach(s => ids.push(s.id)));
    SKILLS_CATALOG.individual.forEach(s => ids.push(s.id));
    return ids;
  }
  function _totalSkillCount() { return _allSkillIds().length; }

  async function ccInitSkills() {
    await ccLoadSkillsCatalog();
    if (_skillsInited) return;
    SKILLS_CATALOG.defaults.forEach(s => { if (s.enabled !== false) _skillsSel.add(s.id); });
    _skillsInited = true;
    ccUpdateSkillsPreview();
  }

  // ── Rendering ──
  async function ccRenderSkillsStore() {
    await ccInitSkills();
    const box = document.getElementById('ccSkillsStoreBody');
    if (!box) return;
    const total = _totalSkillCount();
    let h = '';

    // Search bar + counter
    h += '<div class="skills-topbar">';
    h += '<input class="skills-search" type="text" placeholder="\u{1F50D} Rechercher une skill..." oninput="ccFilterSkills(this.value)" id="ccSkillsSearchInput"/>';
    h += '<div class="skills-counter-badge" id="ccSkillsCounterBadge"><b>' + _skillsSel.size + '</b> / ' + total + '</div>';
    h += '</div>';

    // DEFAULTS
    h += '<div class="skills-section" data-section="defaults">';
    h += '<div class="skills-section-title">\u2705 Recommandees <span class="sdim">activees par defaut</span></div>';
    h += '<div class="skills-defaults">';
    SKILLS_CATALOG.defaults.forEach(s => {
      const on = _skillsSel.has(s.id);
      h += '<div class="skill-pill' + (on ? ' selected' : '') + '" data-sid="' + s.id + '" onclick="ccToggleSkill(\'' + s.id + '\')">';
      h += '<span class="pcheck">' + (on ? '\u2713' : '') + '</span>';
      h += '<span>' + s.emoji + ' ' + s.name + '</span>';
      h += '</div>';
    });
    h += '</div></div>';

    // PACKS
    h += '<div class="skills-section" data-section="packs">';
    h += '<div class="skills-section-title">\u{1F4E6} Packs <span class="sdim">1 clic = plusieurs skills</span></div>';
    h += '<div class="skills-packs-grid">';
    SKILLS_CATALOG.packs.forEach(pack => {
      const cnt = pack.skills.filter(s => _skillsSel.has(s.id)).length;
      const allOn = cnt === pack.skills.length;
      let cls = 'skill-pack';
      if (allOn) cls += ' pack-on';
      else if (cnt > 0) cls += ' pack-partial';
      if (cnt > 0) cls += ' pack-open';

      h += '<div class="' + cls + '" id="pack-' + pack.id + '" data-packid="' + pack.id + '">';
      h += '<div class="skill-pack-head">';
      h += '<div class="skill-pack-info" onclick="ccExpandPack(\'' + pack.id + '\', event)">';
      h += '<span class="skill-pack-emoji">' + pack.emoji + '</span>';
      h += '<div class="skill-pack-label"><div class="pack-name">' + pack.name + '</div>';
      h += '<div class="pack-desc">' + (pack.description || pack.desc || '') + '</div></div>';
      h += '</div>';
      h += '<div class="skill-pack-actions">';
      h += '<span class="pack-count-badge">' + cnt + '/' + pack.skills.length + '</span>';
      h += '<div class="pack-sw" onclick="ccTogglePack(\'' + pack.id + '\')"></div>';
      h += '<span class="pack-expand-arrow" onclick="ccExpandPack(\'' + pack.id + '\', event)">\u25BC</span>';
      h += '</div></div>';

      h += '<div class="skill-pack-body"><div class="skill-pack-skills">';
      pack.skills.forEach(s => {
        const son = _skillsSel.has(s.id);
        h += '<span class="pack-skill-tag' + (son ? ' ssel' : '') + '" data-sid="' + s.id + '" onclick="ccToggleSkill(\'' + s.id + '\')">' + s.id + '</span>';
      });
      h += '</div></div></div>';
    });
    h += '</div></div>';

    // INDIVIDUAL
    h += '<div class="skills-section" data-section="individual">';
    h += '<div class="skills-section-title">\u{1F535} Options individuelles</div>';
    h += '<div class="skills-ind-grid">';
    SKILLS_CATALOG.individual.forEach(s => {
      const on = _skillsSel.has(s.id);
      h += '<div class="skill-card' + (on ? ' selected' : '') + '" data-sid="' + s.id + '" onclick="ccToggleSkill(\'' + s.id + '\')">';
      h += '<span class="skill-card-emoji">' + s.emoji + '</span>';
      h += '<div class="skill-card-body"><div class="skill-card-name">' + s.name + '</div>';
      h += '<div class="skill-card-repo">' + s.repo + '</div></div>';
      if (s.installs) h += '<span class="skill-card-inst">\u2B07 ' + s.installs + '</span>';
      h += '<span class="skill-card-chk">' + (on ? '\u2713' : '') + '</span>';
      h += '</div>';
    });
    h += '</div></div>';

    // EXCLUDED
    h += '<div class="skills-excluded">';
    h += '<div class="skills-excluded-title">\u26A0\uFE0F Non inclus (securite)</div>';
    SKILLS_CATALOG.excluded.forEach(s => {
      h += '<div class="skills-excluded-item">\u274C <b>' + s.id + '</b> \u2014 ' + s.reason + '</div>';
    });
    h += '</div>';

    box.innerHTML = h;
    ccUpdateCounters();
  }

  // ── Interactions ──
  function ccToggleSkill(sid) {
    if (_skillsSel.has(sid)) _skillsSel.delete(sid);
    else _skillsSel.add(sid);

    const on = _skillsSel.has(sid);
    document.querySelectorAll('[data-sid="' + sid + '"]').forEach(el => {
      el.classList.toggle('selected', on);
      el.classList.toggle('ssel', on);
      const chk = el.querySelector('.pcheck, .skill-card-chk');
      if (chk) chk.textContent = on ? '\u2713' : '';
    });

    SKILLS_CATALOG.packs.forEach(pack => {
      const el = document.getElementById('pack-' + pack.id);
      if (!el) return;
      const cnt = pack.skills.filter(s => _skillsSel.has(s.id)).length;
      const allOn = cnt === pack.skills.length;
      el.classList.toggle('pack-on', allOn);
      el.classList.toggle('pack-partial', cnt > 0 && !allOn);
      const badge = el.querySelector('.pack-count-badge');
      if (badge) badge.textContent = cnt + '/' + pack.skills.length;
    });
    ccUpdateCounters();
  }

  function ccTogglePack(packId) {
    const pack = SKILLS_CATALOG.packs.find(p => p.id === packId);
    if (!pack) return;
    const allOn = pack.skills.every(s => _skillsSel.has(s.id));

    pack.skills.forEach(s => {
      if (allOn) _skillsSel.delete(s.id);
      else _skillsSel.add(s.id);
    });

    pack.skills.forEach(s => {
      const on = _skillsSel.has(s.id);
      document.querySelectorAll('[data-sid="' + s.id + '"]').forEach(el => {
        el.classList.toggle('selected', on);
        el.classList.toggle('ssel', on);
      });
    });

    const el = document.getElementById('pack-' + packId);
    if (el) {
      el.classList.toggle('pack-on', !allOn);
      el.classList.remove('pack-partial');
      if (!allOn) el.classList.add('pack-open');
      const badge = el.querySelector('.pack-count-badge');
      if (badge) badge.textContent = (!allOn ? pack.skills.length : 0) + '/' + pack.skills.length;
    }
    ccUpdateCounters();
  }

  function ccExpandPack(packId, ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('pack-' + packId);
    if (el) el.classList.toggle('pack-open');
  }

  function ccFilterSkills(query) {
    const q = (query || '').toLowerCase().trim();
    SKILLS_CATALOG.defaults.forEach(s => {
      const el = document.querySelector('.skill-pill[data-sid="' + s.id + '"]');
      if (el) el.classList.toggle('skill-hidden', q && !s.id.includes(q) && !s.name.toLowerCase().includes(q) && !(s.description || '').toLowerCase().includes(q));
    });
    SKILLS_CATALOG.packs.forEach(pack => {
      const el = document.getElementById('pack-' + pack.id);
      if (!el) return;
      const packDesc = (pack.description || pack.desc || '').toLowerCase();
      const matchPack = !q || pack.name.toLowerCase().includes(q) || packDesc.includes(q);
      const matchSkill = pack.skills.some(s => s.id.includes(q));
      el.classList.toggle('skill-hidden', q && !matchPack && !matchSkill);
    });
    SKILLS_CATALOG.individual.forEach(s => {
      const el = document.querySelector('.skill-card[data-sid="' + s.id + '"]');
      if (el) el.classList.toggle('skill-hidden', q && !s.id.includes(q) && !s.name.toLowerCase().includes(q) && !(s.description || '').toLowerCase().includes(q) && !(s.tags || []).some(t => t.includes(q)));
    });
  }

  // ── Counters & preview ──
  function ccUpdateCounters() {
    const total = _totalSkillCount();
    const badge = document.getElementById('ccSkillsCounterBadge');
    if (badge) badge.innerHTML = '<b>' + _skillsSel.size + '</b> / ' + total;
    const summary = document.getElementById('ccSkillsSummary');
    if (summary) summary.innerHTML = '<b>' + _skillsSel.size + '</b> skill(s) sur ' + total;
    ccUpdateSkillsPreview();
  }

  function ccUpdateSkillsPreview() {
    const countEl = document.getElementById('ccSkillsCountInline');
    const pillsEl = document.getElementById('ccSkillsPreviewPills');
    if (countEl) countEl.textContent = _skillsSel.size + ' skill' + (_skillsSel.size !== 1 ? 's' : '');
    if (pillsEl) {
      const arr = Array.from(_skillsSel);
      const MAX = 8;
      let ph = '';
      arr.slice(0, MAX).forEach(id => { ph += '<span class="skills-preview-pill">' + id + '</span>'; });
      if (arr.length > MAX) ph += '<span class="skills-preview-more">+' + (arr.length - MAX) + '</span>';
      if (!arr.length) ph = '<span class="skills-preview-more">Aucune skill selectionnee</span>';
      pillsEl.innerHTML = ph;
    }
  }

  // ── Bulk selection ──
  function ccSelectAllSkills() {
    _allSkillIds().forEach(id => _skillsSel.add(id));
    ccRenderSkillsStore();
  }
  function ccSelectNoneSkills() {
    _skillsSel.clear();
    ccRenderSkillsStore();
  }
  function ccSelectDefaultsOnly() {
    _skillsSel.clear();
    SKILLS_CATALOG.defaults.forEach(s => _skillsSel.add(s.id));
    ccRenderSkillsStore();
  }

  // ── Modal controls ──
  async function ccShowSkillsModal() {
    await ccRenderSkillsStore();
    document.getElementById('ccSkillsModal').classList.add('active');
  }

  function ccCloseSkillsModal() {
    document.getElementById('ccSkillsModal').classList.remove('active');
    ccUpdateSkillsPreview();
  }

  function ccApplySkillsSelection() {
    ccCloseSkillsModal();
  }

  async function ccStandaloneInstall() {
    await ccInitSkills();
    if (!_skillsSel.size) { alert('Aucune skill selectionnee.'); return; }
    if (!confirm('Installer ' + _skillsSel.size + ' skill(s) maintenant ?\nUn terminal Claude sera lance.')) return;
    let token = _ccPendingLaunch?.token || document.getElementById('ccExistingToken')?.value;
    if (!token) {
      token = prompt('Token projet pour lier l\'installation :');
      if (!token) return;
    }
    try {
      await api('/api/projects/claude-onboarding/launch', 'POST', {
        token,
        install_claude: false,
        install_skills: true,
        skills: Array.from(_skillsSel),
      });
      alert('\u2705 Installation lancee \u2014 verifiez le terminal.');
      ccCloseSkillsModal();
    } catch (err) {
      alert('\u274C ' + err.message);
    }
  }

  // ─── BROWSE MODELS ───
  async function ccLoadBrowse() {
    try {
      const [modelsRes, statusRes] = await Promise.all([
        api('/v1/models'),
        api('/api/status'),
      ]);

      const models = modelsRes.data || [];
      const profiles = statusRes.profiles || [];

      // Build model→profiles map from the new profiles field
      ccBrowseCache = models.map(m => {
        const mp = m.profiles || [];
        const isCoding = mp.includes('coding') || m.owned_by === 'profile';
        return { ...m, modelProfiles: mp, isCoding };
      });

      // Populate provider filter from actual owned_by (excluding 'profile')
      const provSet = new Set();
      ccBrowseCache.forEach(m => {
        let prov = m.owned_by || '';
        if (prov && prov !== 'profile' && !prov.startsWith('alias:')) provSet.add(prov);
      });
      const provSel = document.getElementById('ccBrowseProvider');
      const curProv = provSel.value;
      provSel.innerHTML = '<option value="">Tous les providers</option>';
      const provEmojis = { ollama_cloud: '☁️', nvidia: '🟩', openrouter: '🧭', google: '🟡', local: '🏠' };
      [...provSet].sort().forEach(p => {
        provSel.innerHTML += `<option value="${p}" ${p === curProv ? 'selected' : ''}>${provEmojis[p] || ''} ${p}</option>`;
      });

      ccFilterBrowse();
    } catch (err) {
      document.getElementById('ccBrowseGrid').innerHTML =
        `<div style="color:var(--text-muted); padding:20px; grid-column:1/-1">❌ Erreur : ${err.message}</div>`;
    }
  }

  function ccFilterBrowse() {
    const q = (document.getElementById('ccBrowseSearch').value || '').toLowerCase();
    const profileFilter = document.getElementById('ccBrowseFilter').value;
    const provFilter = document.getElementById('ccBrowseProvider').value;
    const codingOnly = document.getElementById('ccBrowseCodingOnly').checked;

    const filtered = ccBrowseCache.filter(m => {
      if (q && !m.id.toLowerCase().includes(q) && !(m.owned_by || '').toLowerCase().includes(q)) return false;
      // Profile filter: check if model belongs to this profile
      if (profileFilter && !(m.modelProfiles || []).includes(profileFilter) && m.id !== profileFilter) return false;
      // Provider filter: match owned_by (provider name)
      if (provFilter) {
        const ob = m.owned_by || '';
        if (ob !== provFilter && !ob.endsWith(':' + provFilter)) return false;
      }
      // Coding-only filter: hide models not usable with coding_only policy
      if (codingOnly && !m.isCoding) return false;
      return true;
    });

    const grid = document.getElementById('ccBrowseGrid');
    const empty = document.getElementById('ccBrowseEmpty');

    if (filtered.length === 0) {
      grid.innerHTML = '';
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';

    const profileEmojis = {
      coding: '🔧', reasoning: '🧠', chat: '💬', long: '📄',
      vision: '👁️', audio: '🎤', translate: '🌐',
    };
    const provEmojis = { ollama_cloud: '☁️', nvidia: '🟩', openrouter: '🧭', google: '🟡', local: '🏠', profile: '📂', 'api-rotator': '🔄' };

    // Group by provider for display
    const groups = {};
    const groupOrder = ['profile', 'ollama_cloud', 'nvidia', 'openrouter', 'google', 'local'];
    filtered.forEach(m => {
      let group = m.owned_by || 'autre';
      if (group.startsWith('alias:')) group = 'alias';
      if (!groups[group]) groups[group] = [];
      groups[group].push(m);
    });

    const sortedGroups = Object.keys(groups).sort((a, b) => {
      const ia = groupOrder.indexOf(a), ib = groupOrder.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    const groupLabels = {
      profile: '📂 Profils (rotation auto)',
      ollama_cloud: '☁️ Ollama Cloud',
      nvidia: '🟩 NVIDIA',
      openrouter: '🧭 OpenRouter',
      google: '🟡 Google',
      local: '🏠 Local (Ollama)',
      alias: '🔗 Alias',
    };

    let html = '';
    for (const group of sortedGroups) {
      const items = groups[group];
      const label = groupLabels[group] || `📦 ${group}`;
      html += `<div style="grid-column:1/-1; margin-top:16px; margin-bottom:6px; font-size:14px; font-weight:800; color:#fff; display:flex; align-items:center; gap:8px">${label} <span style="font-size:11px; font-weight:400; color:var(--text-dim)">(${items.length})</span></div>`;
      items.forEach(m => {
        const mp = m.modelProfiles || [];
        const isCoding = m.isCoding;
        const profileBadges = mp.map(p => `<span style="font-size:9.5px; padding:1px 5px; border-radius:4px; background:${p === 'coding' ? 'rgba(52,211,153,.15); color:var(--green)' : 'var(--surface2); color:var(--text-dim)'}">${profileEmojis[p] || ''} ${p}</span>`).join(' ');
        const borderColor = isCoding ? 'var(--border)' : 'rgba(239,68,68,.3)';
        const opacity = isCoding ? '1' : '0.55';
        const incompatNote = isCoding ? '' : '<div style="font-size:10px; color:var(--red); margin-top:2px">⚠️ Incompatible avec les tokens coding_only</div>';

        html += `
          <div style="background:var(--surface); border:1px solid ${borderColor}; border-radius:var(--r-lg); padding:14px; display:flex; flex-direction:column; gap:8px; opacity:${opacity}; transition:opacity .2s" onmouseenter="this.style.opacity='1'" onmouseleave="this.style.opacity='${opacity}'">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px">
              <div style="font-family:var(--font-mono); font-size:12.5px; font-weight:600; color:#fff; word-break:break-all">${m.id}</div>
              <span style="font-size:9.5px; padding:2px 6px; border-radius:4px; background:var(--surface2); color:var(--text-dim); flex-shrink:0; white-space:nowrap">${(provEmojis[m.owned_by] || '') + ' ' + (m.owned_by || '?')}</span>
            </div>
            <div style="display:flex; gap:4px; flex-wrap:wrap">${profileBadges || '<span style="font-size:9.5px; color:var(--text-dim)">—</span>'}</div>
            ${incompatNote}
            <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:2px">
              <button onclick="navigator.clipboard.writeText('${m.id}').then(()=>{this.innerText='✅ Copié';setTimeout(()=>this.innerText='📋 Copier ID',1500)})" style="font-size:10.5px; padding:4px 8px">📋 Copier ID</button>
              <button onclick="navigator.clipboard.writeText('claude --model ${m.id}').then(()=>{this.innerText='✅ Copié';setTimeout(()=>this.innerText='🚀 Commande',1500)})" style="font-size:10.5px; padding:4px 8px">🚀 Commande</button>
            </div>
          </div>`;
      });
    }
    grid.innerHTML = html;
  }

  // ─── PINNED MODEL ───
  async function ccLoadModels() {
    try {
      const data = await api('/v1/models');
      const sel = document.getElementById('ccModelSelect');
      sel.innerHTML = '<option value="">— auto (rotation) —</option>';
      (data.data || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.id + (m.owned_by ? ` (${m.owned_by})` : '');
        sel.appendChild(opt);
      });
    } catch {}

    // Load current coding profil from /api/status
    try {
      const data = await api('/api/status');
      const codingProfile = (data.profiles || []).find(p => p.name === 'coding');
      const overrides = data.overrides || {};
      const codingOverride = (overrides.profiles || {}).coding || 'auto';
      const lock = (data.locks || {}).coding;

      let html = '<div style="display:grid; grid-template-columns:auto 1fr; gap:4px 12px; line-height:1.8">';
      html += `<span style="color:var(--text-dim)">Mode :</span><strong style="color:var(--accent)">${codingOverride}</strong>`;
      if (codingProfile) {
        html += `<span style="color:var(--text-dim)">Provider actuel :</span><span style="color:#fff">${codingProfile.provider}</span>`;
        html += `<span style="color:var(--text-dim)">Modèle actuel :</span><span style="color:#fff">${codingProfile.model}</span>`;
        html += `<span style="color:var(--text-dim)">Requêtes aujourd'hui :</span><span>${codingProfile.requests_today}</span>`;
      }
      if (lock) {
        html += `<span style="color:var(--text-dim)">Verrou :</span><span style="color:var(--amber)">🔒 ${lock.model}</span>`;
      }
      html += '</div>';
      html += `<div style="margin-top:8px; font-size:11px; color:var(--text-dim)">
        ${codingOverride === 'auto'
          ? '✅ Le routeur choisit automatiquement le meilleur modèle parmi tous vos providers.'
          : `📌 Forcé sur : <strong style="color:#fff">${codingOverride}</strong>. Cliquez "🔓 Remettre en auto" pour réactiver la rotation.`
        }
      </div>`;
      document.getElementById('ccCodingProfile').innerHTML = html;

      if (codingOverride !== 'auto') {
        document.getElementById('ccModelSelect').value = codingOverride;
      }
    } catch {}

    // Load aliases
    try {
      const data = await api('/api/config');
      const aliases = data.compat_aliases || {};
      const html = Object.entries(aliases).map(([alias, target]) =>
        `<div style="margin-bottom:4px"><span style="color:#fff">${alias}</span> <span style="color:var(--text-dim)">→</span> <span style="color:var(--accent)">${target}</span>
          <span style="color:var(--text-dim); font-size:11px; margin-left:8px">(utiliser <span style="color:#fff">claude --model ${alias}</span>)</span>
        </div>`
      ).join('') || '<div style="color:var(--text-dim)">Aucun alias configuré</div>';
      document.getElementById('ccAliasesList').innerHTML = html;
    } catch {}
  }

  async function ccPinModel() {
    const model = document.getElementById('ccModelSelect').value;
    const st = document.getElementById('ccModelStatus');
    if (!model) { st.innerText = '❌ Sélectionnez un modèle'; return; }

    try {
      await api('/api/override/force', 'POST', { profile: 'coding', provider: 'auto' });
      await api('/api/lock', 'POST', { profile: 'coding', model });
      st.innerText = `✅ Modèle "${model}" épinglé pour le profil coding`;
      st.className = 'status-line ok';
      ccLoadModels();
    } catch (err) {
      st.innerText = '❌ ' + err.message;
      st.className = 'status-line err';
    }
  }

  async function ccUnpinModel() {
    const st = document.getElementById('ccModelStatus');
    try {
      await api('/api/lock/coding', 'DELETE');
      await api('/api/override/force', 'POST', { profile: 'coding', provider: 'auto' });
      st.innerText = '✅ Profil coding remis en rotation automatique';
      st.className = 'status-line ok';
      ccLoadModels();
    } catch (err) {
      st.innerText = '❌ ' + err.message;
      st.className = 'status-line err';
    }
  }

  // ─── SESSIONS ───
  async function ccLoadSessions() {
    const project = document.getElementById('ccSessionProject').value;
    try {
      const projData = await api('/api/projects');
      const projSel = document.getElementById('ccSessionProject');
      const currentVal = projSel.value;
      projSel.innerHTML = '<option value="">Tous les profils</option>';
      ['coding','reasoning','chat','long','vision','audio','translate'].forEach(p => {
        projSel.innerHTML += `<option value="${p}" ${p === currentVal ? 'selected' : ''}>${p}</option>`;
      });

      const profileFilter = projSel.value ? `&profile=${projSel.value}` : '';
      const sessions = await api(`/api/sessions?limit=200${profileFilter}`);
      ccSessionsCache = sessions.items || [];

      ccFilterSessions();
    } catch {
      document.getElementById('ccSessionList').innerHTML =
        '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center">Erreur de chargement.</div>';
    }
  }

  function ccFilterSessions() {
    const q = (document.getElementById('ccSessionSearch').value || '').toLowerCase();
    const filtered = ccSessionsCache.filter(l => {
      if (q && !(l.model || '').toLowerCase().includes(q) && !(l.provider || '').toLowerCase().includes(q) && !(l.profile || '').toLowerCase().includes(q)) return false;
      return true;
    });

    const list = document.getElementById('ccSessionList');
    if (filtered.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:20px; text-align:center">Aucune session trouvée.</div>';
      return;
    }

    list.innerHTML = filtered.slice(0, 50).map(l => {
      const statusColor = l.success ? 'var(--green)' : 'var(--red)';
      const statusText = l.success ? '✅' : '❌';
      const dt = new Date(l.timestamp).toLocaleString();
      const profileEmojis = { coding:'💻', reasoning:'🧠', chat:'💬', long:'📄', vision:'👁️', audio:'🎵', translate:'🌍' };
      const emoji = profileEmojis[l.profile] || '⚡';
      return `
        <div style="display:flex; align-items:center; gap:12px; padding:8px 14px; background:var(--surface); border:1px solid var(--border); border-radius:var(--r); margin-bottom:4px; font-size:12px">
          <span style="color:${statusColor}; font-weight:700; width:28px; text-align:center">${statusText}</span>
          <span style="font-size:12px; width:24px; text-align:center" title="${l.profile}">${emoji}</span>
          <span style="font-family:var(--font-mono); color:#fff; flex:1">${l.model || '—'}</span>
          <span style="color:var(--text-dim); font-size:11px; min-width:80px">${providerEmoji(l.provider)} ${l.provider || '—'}</span>
          <span style="color:var(--text-dim); font-size:11px">${dt}</span>
        </div>
      `;
    }).join('');
  }

  // ─── MEMORY ───
  async function ccLoadMemory() {
    const dir = document.getElementById('ccMemoryDir').value.trim();
    const st = document.getElementById('ccMemoryStatus');
    const content = document.getElementById('ccMemoryContent');

    if (!dir) {
      st.innerText = '❌ Entrez un chemin de dossier';
      content.style.display = 'none';
      return;
    }

    st.innerText = '🔍 Recherche de CLAUDE.md...';
    try {
      const res = await api('/api/claude-code/memory?' + new URLSearchParams({ dir }));
      if (res.found) {
        document.getElementById('ccMemoryEditor').value = res.content || '';
        content.style.display = 'block';
        st.innerText = '✅ Fichier trouvé : ' + res.path;
      } else {
        st.innerText = '⚠️ Aucun CLAUDE.md trouvé. Éditez ci-dessous pour en créer un.';
        document.getElementById('ccMemoryEditor').value = '# CLAUDE.md\n\n## Instructions pour Claude\n\n';
        content.style.display = 'block';
      }
    } catch (err) {
      st.innerText = '❌ ' + err.message;
      content.style.display = 'none';
    }
  }

  async function ccSaveMemory() {
    const dir = document.getElementById('ccMemoryDir').value.trim();
    const text = document.getElementById('ccMemoryEditor').value;
    const st = document.getElementById('ccMemoryStatus');

    try {
      await api('/api/claude-code/memory', 'POST', { dir, content: text });
      st.innerText = '✅ CLAUDE.md sauvegardé !';
    } catch (err) {
      st.innerText = '❌ ' + err.message;
    }
  }
