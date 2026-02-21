/* ═══════════════════════════════════════════════════════════════
   OPENCLAW DASHBOARD — Comprehensive gateway management
   ═══════════════════════════════════════════════════════════════ */

let _ocConfig = null; // cached full config

/* ─── Tab management ─── */
function showOCTab(name) {
  document.querySelectorAll('.oc-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.oc-section').forEach(s => s.style.display = 'none');
  const tab = document.querySelector(`.oc-tab[onclick="showOCTab('${name}')"]`);
  if (tab) tab.classList.add('active');
  const sec = document.getElementById(`oc-${name}`);
  if (sec) sec.style.display = 'block';
  const loaders = {
    connect: ocLoadConnect, agents: ocLoadAgents, skills: ocLoadSkills,
    channels: ocLoadChannels, cron: ocLoadCron, sessions: ocLoadSessions,
    tools: ocLoadTools, config: ocLoadConfig, doctor: ocLoadDoctor
  };
  if (loaders[name]) loaders[name]();
}

/* ─── Helpers ─── */
function _esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function _badge(ok, yes, no) { return ok ? `<span style="color:var(--ok)">✅ ${yes}</span>` : `<span style="color:var(--err)">❌ ${no||'Non'}</span>`; }
function _dim(s) { return `<span style="color:var(--text-dim)">${s}</span>`; }
function _mono(s) { return `<code style="font-size:11px">${_esc(s)}</code>`; }
function _card(title, body, mt) { return `<div class="card"${mt ? ` style="margin-top:${mt}px"`:''}>` + (title ? `<div class="card-title">${title}</div>`:'') + `<div style="font-size:12px;line-height:1.8;margin-top:6px">${body}</div></div>`; }
function _btn(label, onclick, id) { return `<button${id?` id="${id}"`:''} onclick="${onclick}">${label}</button>`; }
async function _ocFetch(url, opts) { const r = await fetch(url, opts); return r.json(); }
async function _ocPost(url, body) { return _ocFetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{}) }); }
async function _ocGetConfig() { if (_ocConfig) return _ocConfig; try { const d = await _ocFetch('/api/openclaw/config'); if (d.ok) { _ocConfig = d.config; return _ocConfig; } } catch(e) {} return {}; }
function _ocInvalidateConfig() { _ocConfig = null; }

/* ═══════════════════════════════════════════════════════════════
   1. CONNEXION — Status, install, gateway, rotator setup
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadConnect() {
  const el = document.getElementById('ocConnectContent');
  if (!el) return;
  el.innerHTML = _dim('Vérification…');
  try {
    const d = await _ocFetch('/api/openclaw/status');
    let h = '';

    // Prerequisites
    h += _card('📦 Prérequis',
      `<div>Node.js : ${d.node_installed ? _badge(true, d.node_version) : _badge(false, '', 'Non installé (Node 22+ requis)')}</div>
       <div>OpenClaw CLI : ${d.openclaw_installed ? _badge(true, d.openclaw_version) : _badge(false, '', 'Non installé')}</div>
       <div>Config : ${d.config_exists ? _badge(true, 'Trouvée') : _dim('⚪ Absente')}</div>`);

    // Gateway
    h += _card('🌐 Gateway',
      `<div>État : ${d.gateway_running ? `<span style="color:var(--ok)">✅ En cours (port ${d.gateway_port})</span>` : _dim('⚪ Arrêté')}</div>
       ${d.gateway_url ? `<div>Control UI : <a href="${d.gateway_url}" target="_blank" style="color:var(--accent)">${d.gateway_url}</a></div>` : ''}`, 12);

    // Rotator provider
    h += _card('🔗 Provider Rotator',
      `<div>${d.rotator_configured ? _badge(true, 'Configuré — 4 modèles (coding / reasoning / chat / long)') : _dim('⚪ Non configuré')}</div>
       <div style="margin-top:4px">Channels actifs : ${d.channels && d.channels.length ? d.channels.map(c => `<span style="display:inline-block;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:2px 8px;margin:2px;font-size:11px">${c}</span>`).join('') : _dim('aucun')}</div>`, 12);

    // Actions
    let btns = '';
    if (!d.openclaw_installed) btns += _btn('📥 Installer OpenClaw', 'ocInstall()', 'ocInstallBtn');
    if (d.openclaw_installed && !d.gateway_running) btns += _btn('▶ Démarrer le Gateway', 'ocStartGateway()');
    if (d.gateway_running) {
      btns += _btn('🔄 Restart Gateway', 'ocRestartGateway()');
      btns += _btn('⏹ Arrêter le Gateway', 'ocStopGateway()');
      if (d.gateway_url) btns += _btn('🌐 Control UI', `window.open('${d.gateway_url}','_blank')`);
    }
    if (d.openclaw_installed && !d.rotator_configured) btns += _btn('🔧 Configurer Rotator', 'ocConfigureRotator()');
    if (d.openclaw_installed) btns += _btn('🧙 Wizard d\'onboarding', 'ocOnboard()');
    btns += _btn('🔃 Rafraîchir', 'ocLoadConnect()');
    h += _card('⚡ Actions', `<div style="display:flex;gap:8px;flex-wrap:wrap">${btns}</div>`, 12);

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

async function ocInstall() {
  const btn = document.getElementById('ocInstallBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Installation…'; }
  try {
    const d = await _ocPost('/api/openclaw/install');
    showToast(d.ok ? 'OpenClaw installé !' : ('Erreur: ' + (d.error||'échec')), d.ok ? 'success' : 'error');
  } catch (e) { showToast('Erreur: ' + e.message, 'error'); }
  ocLoadConnect();
}
async function ocStartGateway() {
  try { const d = await _ocPost('/api/openclaw/gateway/start'); showToast(d.ok?'Gateway démarré.':'Erreur: '+(d.error||''), d.ok?'success':'error'); } catch(e) { showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 2500);
}
async function ocStopGateway() {
  try { const d = await _ocPost('/api/openclaw/gateway/stop'); showToast(d.ok?'Gateway arrêté.':'Erreur: '+(d.error||''), d.ok?'success':'error'); } catch(e) { showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 1500);
}
async function ocRestartGateway() {
  try { const d = await _ocPost('/api/openclaw/gateway/restart'); showToast(d.ok?'Gateway redémarré.':'Erreur: '+(d.error||''), d.ok?'success':'error'); } catch(e) { showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 3000);
}
async function ocConfigureRotator() {
  try {
    const d = await _ocPost('/api/openclaw/configure-rotator');
    if (d.ok) { showToast('Rotator configuré comme provider !', 'success'); _ocInvalidateConfig(); ocLoadConnect(); }
    else showToast('Erreur: ' + (d.error||''), 'error');
  } catch (e) { showToast(e.message, 'error'); }
}
async function ocOnboard() {
  try { const d = await _ocPost('/api/openclaw/onboard'); showToast(d.ok ? 'Wizard lancé dans un terminal.' : 'Erreur', d.ok?'success':'error'); } catch(e) { showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   2. AGENTS — Identity, models, workspace, heartbeat
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadAgents() {
  const el = document.getElementById('ocAgentsContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/agents');
    const defaults = d.defaults || {};
    const agents = d.list || [];
    let h = '';

    // Defaults
    const model = defaults.model || {};
    h += _card('🎯 Defaults agents', `
      <div>Modèle principal : ${model.primary ? _mono(model.primary) : _dim('non défini')}</div>
      <div>Fallbacks : ${(model.fallbacks||[]).length ? (model.fallbacks||[]).map(m=>_mono(m)).join(', ') : _dim('aucun')}</div>
      <div>Workspace : ${_mono(defaults.workspace || '~/.openclaw/workspace')}</div>
      <div>Max concurrent : ${defaults.maxConcurrent || 1}</div>
      <div>Timeout : ${defaults.timeoutSeconds || 600}s</div>
      <div>Thinking : ${_mono(defaults.thinkingDefault || 'off')}</div>
      <div>Context tokens : ${(defaults.contextTokens || 200000).toLocaleString()}</div>
    `);

    // Heartbeat
    const hb = defaults.heartbeat || {};
    if (Object.keys(hb).length) {
      h += _card('💓 Heartbeat', `
        <div>Intervalle : ${_mono(hb.every || '30m')}</div>
        <div>Session : ${_mono(hb.session || 'main')}</div>
        <div>Modèle : ${hb.model ? _mono(hb.model) : _dim('default')}</div>
        <div>Target : ${_mono(hb.target || 'last')}</div>
      `, 12);
    }

    // Compaction
    const comp = defaults.compaction || {};
    if (Object.keys(comp).length) {
      h += _card('📦 Compaction', `
        <div>Mode : ${_mono(comp.mode || 'default')}</div>
        <div>Reserve tokens : ${comp.reserveTokensFloor || 24000}</div>
        <div>Memory flush : ${comp.memoryFlush?.enabled ? '✅ Actif' : '❌ Inactif'}</div>
      `, 12);
    }

    // Agent list
    if (agents.length) {
      h += '<div style="margin-top:16px"><div style="font-size:13px;font-weight:600;color:#fff;margin-bottom:8px">🤖 Agents configurés</div>';
      for (const ag of agents) {
        const id = ag.identity || {};
        h += _card(
          `${id.emoji||'🤖'} ${ag.id}${ag.default ? ' <span style="color:var(--ok);font-size:10px">(default)</span>':''}`,
          `<div>Nom : ${id.name ? _mono(id.name) : _dim('—')}</div>
           <div>Thème : ${id.theme ? _mono(id.theme) : _dim('—')}</div>
           <div>Workspace : ${ag.workspace ? _mono(ag.workspace) : _dim('default')}</div>
           <div>Modèle : ${ag.model ? _mono(typeof ag.model === 'string' ? ag.model : ag.model.primary) : _dim('default')}</div>
           ${ag.tools?.profile ? `<div>Tool profile : ${_mono(ag.tools.profile)}</div>` : ''}
           ${(ag.groupChat?.mentionPatterns||[]).length ? `<div>Mention patterns : ${ag.groupChat.mentionPatterns.map(p=>_mono(p)).join(', ')}</div>` : ''}`,
          8);
      }
      h += '</div>';
    } else {
      h += _card('🤖 Agents', _dim('Aucun agent configuré. L\'agent par défaut utilise les settings ci-dessus.'), 12);
    }

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

/* ═══════════════════════════════════════════════════════════════
   3. SKILLS — Bundled, managed, workspace skills + ClawHub
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadSkills() {
  const el = document.getElementById('ocSkillsContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/skills/list');
    let h = '';

    // CLI output (runtime status)
    if (d.cli_output) {
      h += _card('🧩 Skills (runtime)', `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;max-height:400px;overflow:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:4px">${_esc(d.cli_output)}</pre>`);
    } else {
      h += _card('🧩 Skills', `${_dim('OpenClaw CLI non disponible.')} ${d.cli_error ? `<div style="margin-top:4px;color:var(--err);font-size:11px">${_esc(d.cli_error)}</div>` : ''}`);
    }

    // Config entries
    const entries = d.config_entries || {};
    const keys = Object.keys(entries);
    if (keys.length) {
      let rows = '';
      for (const name of keys) {
        const e = entries[name];
        const enabled = e.enabled !== false;
        const hasKey = !!e.apiKey || !!e.env;
        rows += `<tr>
          <td style="padding:4px 8px">${_mono(name)}</td>
          <td style="padding:4px 8px;text-align:center">${enabled ? '✅' : '❌'}</td>
          <td style="padding:4px 8px;text-align:center">${hasKey ? '🔑' : _dim('—')}</td>
        </tr>`;
      }
      h += _card('⚙️ Config entries (openclaw.json)', `
        <table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px">
          <thead><tr style="border-bottom:1px solid var(--border)"><th style="text-align:left;padding:4px 8px">Skill</th><th style="padding:4px 8px">Actif</th><th style="padding:4px 8px">Clé</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `, 12);
    }

    // Allow bundled
    if (d.allowBundled) {
      h += _card('🔒 Bundled allowlist', `<div>${d.allowBundled.map(s=>_mono(s)).join(', ')}</div>`, 12);
    }

    // ClawHub section
    h += _card('🦞 ClawHub — Registre de skills', `
      <div style="color:var(--text-dim);line-height:1.7">
        <strong style="color:#fff">ClawHub</strong> est le registre public de skills pour OpenClaw.<br>
        Parcourez et installez des skills depuis <a href="https://clawhub.ai" target="_blank" style="color:var(--accent)">clawhub.ai</a>
      </div>
      <div style="font-family:var(--font-mono);font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:8px;line-height:1.7">
        <div style="color:var(--text-dim)"># Rechercher un skill</div>
        <div>clawhub search "calendar"</div>
        <div style="color:var(--text-dim);margin-top:4px"># Installer</div>
        <div>clawhub install &lt;skill-slug&gt;</div>
        <div style="color:var(--text-dim);margin-top:4px"># Mettre à jour tous</div>
        <div>clawhub update --all</div>
      </div>
    `, 12);

    // Skill locations
    h += _card('📁 Emplacements des skills', `
      <div style="font-size:11px;line-height:1.8;color:var(--text-dim)">
        <div><span style="color:#fff">1.</span> Workspace : <code>&lt;workspace&gt;/skills</code> (priorité max)</div>
        <div><span style="color:#fff">2.</span> Managed : <code>~/.openclaw/skills</code></div>
        <div><span style="color:#fff">3.</span> Bundled : inclus dans le package npm</div>
      </div>
    `, 12);

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

/* ═══════════════════════════════════════════════════════════════
   4. CHANNELS — Per-channel status, config, login, model overrides
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadChannels() {
  const el = document.getElementById('ocChannelsContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/channels/details');
    const channels = d.channels || {};
    const names = Object.keys(channels);
    let h = '';

    const icons = {whatsapp:'💬',telegram:'✈️',discord:'🎮',slack:'💼',imessage:'📱',signal:'🔒',mattermost:'💬',googlechat:'📧',msteams:'👔'};
    const labels = {whatsapp:'WhatsApp',telegram:'Telegram',discord:'Discord',slack:'Slack',imessage:'iMessage',signal:'Signal',mattermost:'Mattermost',googlechat:'Google Chat',msteams:'MS Teams'};

    if (names.length) {
      for (const name of names) {
        const ch = channels[name];
        const icon = icons[name]||'📡';
        const label = labels[name]||name;
        const enabled = ch.enabled !== false;
        h += _card(`${icon} ${label}`, `
          <div style="display:flex;gap:16px;flex-wrap:wrap">
            <div>Activé : ${enabled ? '✅' : '❌'}</div>
            <div>DM Policy : ${_mono(ch.dmPolicy||'pairing')}</div>
            <div>Group Policy : ${_mono(ch.groupPolicy||'allowlist')}</div>
            <div>Token : ${ch.hasToken ? '🔑 Présent' : _dim('absent')}</div>
            <div>Streaming : ${ch.streaming !== false ? '✅' : '❌'}</div>
            ${ch.historyLimit ? `<div>History limit : ${ch.historyLimit}</div>` : ''}
          </div>
          ${ch.allowFrom?.length ? `<div style="margin-top:4px">Allow from : ${ch.allowFrom.map(s=>_mono(s)).join(', ')}</div>` : ''}
          ${ch.groups?.length ? `<div style="margin-top:4px">Groups : ${ch.groups.map(s=>_mono(s)).join(', ')}</div>` : ''}
          ${ch.customCommands?.length ? `<div style="margin-top:4px">Custom commands : ${ch.customCommands.map(c=>_mono(c.command||c)).join(', ')}</div>` : ''}
          <div style="margin-top:8px">
            ${_btn(`🔗 Login ${label}`, `ocChannelLogin('${name}')`)}
          </div>
        `, h ? 12 : 0);
      }
    } else {
      h += _card('📱 Channels', _dim('Aucun channel configuré dans openclaw.json'));
    }

    // Model overrides
    const mbc = d.modelByChannel || {};
    if (Object.keys(mbc).length) {
      let rows = '';
      for (const [ch, map] of Object.entries(mbc)) {
        if (typeof map === 'object') {
          for (const [id, model] of Object.entries(map)) {
            rows += `<tr><td style="padding:3px 8px">${icons[ch]||'📡'} ${ch}</td><td style="padding:3px 8px">${_mono(id)}</td><td style="padding:3px 8px">${_mono(model)}</td></tr>`;
          }
        }
      }
      if (rows) {
        h += _card('🎯 Model overrides par channel', `
          <table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px">
            <thead><tr style="border-bottom:1px solid var(--border)"><th style="text-align:left;padding:3px 8px">Channel</th><th style="text-align:left;padding:3px 8px">ID</th><th style="text-align:left;padding:3px 8px">Modèle</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        `, 12);
      }
    }

    // Quick add guide
    h += _card('📖 Ajouter un channel', `
      <div style="font-family:var(--font-mono);font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;line-height:1.7">
        <div style="color:var(--text-dim)"># WhatsApp — QR code</div>
        <div>openclaw channels login --channel whatsapp</div>
        <div style="color:var(--text-dim);margin-top:4px"># Telegram — avec bot token</div>
        <div>openclaw channels add --channel telegram --token BOT_TOKEN</div>
        <div style="color:var(--text-dim);margin-top:4px"># Discord — avec bot token</div>
        <div>openclaw channels add --channel discord --token DISCORD_TOKEN</div>
        <div style="color:var(--text-dim);margin-top:4px"># Slack — socket mode</div>
        <div>openclaw channels add --channel slack --token BOT_TOKEN --app-token APP_TOKEN</div>
      </div>
    `, 12);

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

async function ocChannelLogin(channel) {
  try {
    const d = await _ocPost('/api/openclaw/channels/login', { channel });
    showToast(d.ok ? `Terminal de login ${channel} ouvert.` : ('Erreur: '+(d.error||'')), d.ok?'success':'error');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   5. CRON — Jobs, schedules, add/run/remove
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadCron() {
  const el = document.getElementById('ocCronContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/cron/list');
    const jobs = d.jobs || [];
    let h = '';

    if (jobs.length) {
      let rows = '';
      for (const j of jobs) {
        const sched = j.schedule || {};
        let schedStr = sched.kind === 'cron' ? `cron: ${sched.expr}` : sched.kind === 'every' ? `every ${sched.everyMs}ms` : sched.kind === 'at' ? `at: ${sched.at}` : JSON.stringify(sched);
        rows += `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:6px 8px">${_mono(j.name||j.jobId||'—')}</td>
          <td style="padding:6px 8px;font-size:11px">${schedStr}</td>
          <td style="padding:6px 8px">${_mono(j.sessionTarget||'main')}</td>
          <td style="padding:6px 8px">${j.enabled !== false ? '✅' : '❌'}</td>
          <td style="padding:6px 8px">
            ${_btn('▶', `ocCronRun('${j.jobId||j.id}')`)}
            ${_btn('🗑', `ocCronRemove('${j.jobId||j.id}')`)}
          </td>
        </tr>`;
      }
      h += _card('⏰ Cron Jobs', `
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:4px">
          <thead><tr style="border-bottom:2px solid var(--border)"><th style="text-align:left;padding:6px 8px">Nom</th><th style="text-align:left;padding:6px 8px">Schedule</th><th style="padding:6px 8px">Session</th><th style="padding:6px 8px">Actif</th><th style="padding:6px 8px">Actions</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `);
    } else {
      h += _card('⏰ Cron Jobs', _dim('Aucun job cron configuré.'));
    }

    // Add job form
    h += _card('➕ Ajouter un cron job', `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:4px">
        <div><label style="font-size:11px;color:var(--text-dim)">Nom</label><input id="ocCronName" placeholder="Morning brief" style="width:100%;margin-top:2px"></div>
        <div><label style="font-size:11px;color:var(--text-dim)">Expression cron</label><input id="ocCronExpr" placeholder="0 7 * * *" style="width:100%;margin-top:2px"></div>
        <div><label style="font-size:11px;color:var(--text-dim)">Timezone</label><input id="ocCronTz" placeholder="Europe/Paris" value="Europe/Paris" style="width:100%;margin-top:2px"></div>
        <div><label style="font-size:11px;color:var(--text-dim)">Session</label>
          <select id="ocCronSession" style="width:100%;margin-top:2px"><option value="isolated">Isolated</option><option value="main">Main</option></select></div>
        <div style="grid-column:1/-1"><label style="font-size:11px;color:var(--text-dim)">Message / Prompt</label><input id="ocCronMsg" placeholder="Summarize overnight updates." style="width:100%;margin-top:2px"></div>
        <div style="grid-column:1/-1"><label style="font-size:11px;color:var(--text-dim)">Channel de livraison</label>
          <select id="ocCronChannel" style="margin-top:2px"><option value="">Aucun (announce)</option><option value="whatsapp">WhatsApp</option><option value="telegram">Telegram</option><option value="discord">Discord</option><option value="slack">Slack</option></select></div>
      </div>
      <div style="margin-top:8px">${_btn('➕ Créer le job', 'ocCronAdd()')}</div>
    `, 12);

    // CLI reference
    h += _card('📖 Commandes CLI cron', `
      <div style="font-family:var(--font-mono);font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;line-height:1.7">
        <div>openclaw cron list</div>
        <div>openclaw cron add --name "Test" --cron "0 7 * * *" --session isolated --message "Hello"</div>
        <div>openclaw cron run &lt;jobId&gt;</div>
        <div>openclaw cron edit &lt;jobId&gt; --message "Updated"</div>
        <div>openclaw cron runs --id &lt;jobId&gt; --limit 10</div>
      </div>
    `, 12);

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

async function ocCronAdd() {
  const name = document.getElementById('ocCronName')?.value;
  const expr = document.getElementById('ocCronExpr')?.value;
  const tz = document.getElementById('ocCronTz')?.value || 'UTC';
  const session = document.getElementById('ocCronSession')?.value || 'isolated';
  const msg = document.getElementById('ocCronMsg')?.value;
  const channel = document.getElementById('ocCronChannel')?.value;
  if (!name || !expr || !msg) { showToast('Remplissez nom, expression cron et message.', 'error'); return; }
  const args = ['cron','add','--name',name,'--cron',expr,'--tz',tz,'--session',session,'--message',msg];
  if (channel) { args.push('--announce','--channel',channel); }
  try {
    const d = await _ocPost('/api/openclaw/cli', { args, timeout: 30 });
    showToast(d.ok ? 'Job créé !' : ('Erreur: '+(d.stderr||d.stdout||'')), d.ok?'success':'error');
    if (d.ok) ocLoadCron();
  } catch(e) { showToast(e.message,'error'); }
}

async function ocCronRun(jobId) {
  try {
    const d = await _ocPost('/api/openclaw/cli', { args: ['cron','run',jobId], timeout: 60 });
    showToast(d.ok ? 'Job exécuté !' : ('Erreur: '+(d.stderr||'')), d.ok?'success':'error');
  } catch(e) { showToast(e.message,'error'); }
}

async function ocCronRemove(jobId) {
  if (!confirm(`Supprimer le job ${jobId} ?`)) return;
  try {
    const d = await _ocPost('/api/openclaw/cli', { args: ['cron','remove',jobId], timeout: 15 });
    showToast(d.ok ? 'Job supprimé.' : ('Erreur: '+(d.stderr||'')), d.ok?'success':'error');
    if (d.ok) ocLoadCron();
  } catch(e) { showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   6. SESSIONS — Scope, reset, identity links
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadSessions() {
  const el = document.getElementById('ocSessionsContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/sessions/config');
    const sess = d.session || {};
    const msgs = d.messages || {};
    let h = '';

    // Session config
    h += _card('💬 Configuration des sessions', `
      <div>Scope : ${_mono(sess.scope || 'per-sender')}</div>
      <div>DM scope : ${_mono(sess.dmScope || 'main')}</div>
      <div>Reset mode : ${_mono(sess.reset?.mode || 'daily')}</div>
      ${sess.reset?.atHour !== undefined ? `<div>Reset at hour : ${sess.reset.atHour}h</div>` : ''}
      ${sess.reset?.idleMinutes ? `<div>Idle minutes : ${sess.reset.idleMinutes}</div>` : ''}
      <div>Reset triggers : ${(sess.resetTriggers||['/new','/reset']).map(t=>_mono(t)).join(', ')}</div>
    `);

    // Reset by type
    if (sess.resetByType) {
      let rbt = '';
      for (const [type, conf] of Object.entries(sess.resetByType)) {
        rbt += `<div>${_mono(type)} : ${conf.mode || 'daily'}${conf.atHour !== undefined ? ` (${conf.atHour}h)` : ''}${conf.idleMinutes ? ` (${conf.idleMinutes}min idle)` : ''}</div>`;
      }
      h += _card('🔄 Reset par type', rbt, 12);
    }

    // Identity links
    if (sess.identityLinks && Object.keys(sess.identityLinks).length) {
      let links = '';
      for (const [name, ids] of Object.entries(sess.identityLinks)) {
        links += `<div><strong style="color:#fff">${name}</strong> : ${ids.map(id=>_mono(id)).join(', ')}</div>`;
      }
      h += _card('🔗 Identity Links', links, 12);
    }

    // Message queue
    const queue = msgs.queue || {};
    h += _card('📨 File de messages', `
      <div>Mode : ${_mono(queue.mode || 'collect')}</div>
      <div>Debounce : ${queue.debounceMs || 1000}ms</div>
      <div>Cap : ${queue.cap || 20}</div>
      <div>Response prefix : ${_mono(msgs.responsePrefix || '—')}</div>
      <div>Ack reaction : ${msgs.ackReaction || '👀'}</div>
    `, 12);

    // TTS
    const tts = msgs.tts || {};
    if (Object.keys(tts).length) {
      h += _card('🔊 TTS (Text-to-Speech)', `
        <div>Auto : ${_mono(tts.auto || 'off')}</div>
        <div>Mode : ${_mono(tts.mode || 'final')}</div>
        <div>Provider : ${_mono(tts.provider || 'elevenlabs')}</div>
        <div>Max text : ${tts.maxTextLength || 4000} chars</div>
      `, 12);
    }

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

/* ═══════════════════════════════════════════════════════════════
   7. TOOLS — Profiles, groups, allow/deny, web, browser, exec
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadTools() {
  const el = document.getElementById('ocToolsContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/tools/config');
    const tools = d.tools || {};
    const browser = d.browser || {};
    let h = '';

    // Profile & allow/deny
    h += _card('🔧 Profil & accès', `
      <div>Profile : ${_mono(tools.profile || 'full (défaut)')}</div>
      <div>Allow : ${(tools.allow||[]).length ? tools.allow.map(t=>_mono(t)).join(', ') : _dim('tout')}</div>
      <div>Deny : ${(tools.deny||[]).length ? tools.deny.map(t=>_mono(t)).join(', ') : _dim('aucun')}</div>
    `);

    // Tool groups reference
    h += _card('📦 Tool Groups', `
      <table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:4px">
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:runtime')}</td><td style="padding:3px 8px;color:var(--text-dim)">exec, bash, process</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:fs')}</td><td style="padding:3px 8px;color:var(--text-dim)">read, write, edit, apply_patch</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:sessions')}</td><td style="padding:3px 8px;color:var(--text-dim)">sessions_list, sessions_history, sessions_send, sessions_spawn</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:memory')}</td><td style="padding:3px 8px;color:var(--text-dim)">memory_search, memory_get</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:web')}</td><td style="padding:3px 8px;color:var(--text-dim)">web_search, web_fetch</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:ui')}</td><td style="padding:3px 8px;color:var(--text-dim)">browser, canvas</td></tr>
        <tr style="border-bottom:1px solid var(--border)"><td style="padding:3px 8px">${_mono('group:automation')}</td><td style="padding:3px 8px;color:var(--text-dim)">cron, gateway</td></tr>
        <tr><td style="padding:3px 8px">${_mono('group:messaging')}</td><td style="padding:3px 8px;color:var(--text-dim)">message</td></tr>
      </table>
    `, 12);

    // Exec config
    const exec = tools.exec || {};
    h += _card('⚙️ Exec', `
      <div>Background timeout : ${exec.backgroundMs || 10000}ms</div>
      <div>Max timeout : ${exec.timeoutSec || 1800}s</div>
      <div>Notify on exit : ${exec.notifyOnExit !== false ? '✅' : '❌'}</div>
      <div>apply_patch : ${exec.applyPatch?.enabled ? '✅ Actif' : '❌ Inactif'}</div>
    `, 12);

    // Elevated
    const elev = tools.elevated || {};
    h += _card('🔐 Elevated access', `
      <div>Enabled : ${elev.enabled ? '✅' : '❌'}</div>
      ${elev.allowFrom ? `<div>Allow from : ${JSON.stringify(elev.allowFrom)}</div>` : ''}
    `, 12);

    // Web tools
    const web = tools.web || {};
    h += _card('🌐 Web tools', `
      <div>Search : ${web.search?.enabled !== false ? '✅' : '❌'} ${web.search?.apiKey ? '(clé configurée)' : _dim('(pas de clé Brave)')}</div>
      <div>Fetch : ${web.fetch?.enabled !== false ? '✅' : '❌'} (max ${web.fetch?.maxChars || 50000} chars)</div>
    `, 12);

    // Browser
    h += _card('🌍 Browser', `
      <div>Enabled : ${browser.enabled !== false ? '✅' : '❌'}</div>
      <div>Default profile : ${_mono(browser.defaultProfile || 'chrome')}</div>
      ${browser.profiles ? `<div>Profiles : ${Object.keys(browser.profiles).map(p=>_mono(p)).join(', ')}</div>` : ''}
      <div>Evaluate : ${browser.evaluateEnabled !== false ? '✅' : '❌'}</div>
    `, 12);

    // Loop detection
    const loop = tools.loopDetection || {};
    if (Object.keys(loop).length) {
      h += _card('🔄 Loop detection', `
        <div>Enabled : ${loop.enabled ? '✅' : '❌'}</div>
        <div>Warning threshold : ${loop.warningThreshold || 10}</div>
        <div>Critical threshold : ${loop.criticalThreshold || 20}</div>
        <div>Circuit breaker : ${loop.globalCircuitBreakerThreshold || 30}</div>
      `, 12);
    }

    // Subagents
    const sub = tools.subagents || {};
    if (Object.keys(sub).length || tools.sessions) {
      h += _card('🧬 Sub-agents & Sessions', `
        ${sub.model ? `<div>Sub-agent model : ${_mono(sub.model)}</div>` : ''}
        <div>Max concurrent : ${sub.maxConcurrent || 1}</div>
        ${tools.sessions?.visibility ? `<div>Session visibility : ${_mono(tools.sessions.visibility)}</div>` : ''}
      `, 12);
    }

    el.innerHTML = h;
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

/* ═══════════════════════════════════════════════════════════════
   8. CONFIG — Full JSON editor with save
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadConfig() {
  const el = document.getElementById('ocConfigContent');
  if (!el) return;
  el.innerHTML = _dim('Chargement…');
  try {
    const d = await _ocFetch('/api/openclaw/config');
    if (d.ok && d.config) {
      _ocConfig = d.config;
      el.innerHTML = `
        <div class="card">
          <div class="card-title">📄 ${_esc(d.path)}</div>
          <textarea id="ocConfigEditor" style="width:100%;min-height:500px;font-family:var(--font-mono);font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;color:#fff;resize:vertical;margin-top:8px">${_esc(JSON.stringify(d.config, null, 2))}</textarea>
          <div style="display:flex;gap:8px;margin-top:10px">
            ${_btn('💾 Sauvegarder', 'ocSaveConfig()')}
            ${_btn('🔧 Injecter Rotator', 'ocConfigureRotator()')}
            ${_btn('📋 Formater', 'ocFormatConfig()')}
            ${_btn('🔃 Recharger', 'ocLoadConfig()')}
          </div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="card-title">📖 Sections de config</div>
          <div style="font-size:11px;line-height:1.8;color:var(--text-dim);margin-top:4px">
            <code>channels</code> — WhatsApp, Telegram, Discord, Slack, iMessage, Signal…<br>
            <code>agents.defaults</code> — Modèles, workspace, heartbeat, compaction<br>
            <code>agents.list</code> — Agents multi-agent avec identité et isolation<br>
            <code>tools</code> — Profils, allow/deny, exec, browser, web<br>
            <code>skills</code> — Skills config, entries, allowBundled<br>
            <code>session</code> — Scope, reset, identity links<br>
            <code>messages</code> — Queue, prefix, ack, TTS<br>
            <code>cron</code> — Scheduler enabled, max concurrent<br>
            <code>gateway</code> — Port, bind, auth, tailscale, Control UI<br>
            <code>hooks</code> — Gmail, webhooks, mappings<br>
            <code>models.providers</code> — Custom providers (ex: rotator)<br>
            <code>browser</code> — Profils CDP, auto-detect<br>
            <code>plugins</code> — Extensions additionnelles<br>
            <code>env</code> — Variables d'environnement inline<br>
          </div>
        </div>`;
    } else {
      el.innerHTML = _card('📄 Config', `
        <div>${_dim('Aucune config trouvée.')}</div>
        <div style="margin-top:8px">${_btn('🧙 Lancer le wizard', 'ocOnboard()')} ${_btn('🔧 Créer config Rotator', 'ocConfigureRotator()')}</div>
      `);
    }
  } catch (e) { el.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

async function ocSaveConfig() {
  const textarea = document.getElementById('ocConfigEditor');
  if (!textarea) return;
  let cfg;
  try { cfg = JSON.parse(textarea.value); } catch(e) { showToast('JSON invalide: ' + e.message, 'error'); return; }
  try {
    const d = await _ocPost('/api/openclaw/config/save', { config: cfg });
    if (d.ok) { showToast('Config sauvegardée !', 'success'); _ocConfig = cfg; }
    else showToast('Erreur: ' + (d.error||''), 'error');
  } catch(e) { showToast(e.message, 'error'); }
}

function ocFormatConfig() {
  const textarea = document.getElementById('ocConfigEditor');
  if (!textarea) return;
  try {
    const cfg = JSON.parse(textarea.value);
    textarea.value = JSON.stringify(cfg, null, 2);
    showToast('Formaté !', 'success');
  } catch(e) { showToast('JSON invalide: ' + e.message, 'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   9. DOCTOR — Diagnostics & repair
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadDoctor() {
  const el = document.getElementById('ocDoctorContent');
  if (!el) return;
  el.innerHTML = _card('🩺 Doctor', `
    <div style="color:var(--text-dim);line-height:1.7">
      <strong style="color:#fff">openclaw doctor</strong> vérifie et répare votre installation :<br>
      Config normalization, state integrity, skills status, auth health, sandbox images, gateway service, security warnings, et plus.
    </div>
    <div style="margin-top:10px;display:flex;gap:8px">
      ${_btn('🩺 Lancer Doctor', 'ocRunDoctor()')}
      ${_btn('🔧 Doctor --repair', 'ocRunDoctorRepair()')}
    </div>
    <div id="ocDoctorOutput" style="margin-top:12px"></div>
  `);
}

async function ocRunDoctor() {
  const out = document.getElementById('ocDoctorOutput');
  if (out) out.innerHTML = _dim('⏳ Doctor en cours… (peut prendre 1-2 min)');
  try {
    const d = await _ocPost('/api/openclaw/doctor');
    if (out) {
      out.innerHTML = `
        <div class="card">
          <div class="card-title">${d.ok ? '✅ Doctor terminé' : '⚠️ Doctor terminé avec des avertissements'}</div>
          ${d.output ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;max-height:500px;overflow:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:8px">${_esc(d.output)}</pre>` : ''}
          ${d.errors ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;color:var(--err);background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:8px">${_esc(d.errors)}</pre>` : ''}
        </div>`;
    }
  } catch(e) { if (out) out.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}

async function ocRunDoctorRepair() {
  const out = document.getElementById('ocDoctorOutput');
  if (out) out.innerHTML = _dim('⏳ Doctor --repair en cours…');
  try {
    const d = await _ocPost('/api/openclaw/cli', { args: ['doctor','--repair'], timeout: 120 });
    if (out) {
      out.innerHTML = `<div class="card">
        <div class="card-title">${d.ok ? '✅ Repair terminé' : '⚠️ Repair terminé avec des erreurs'}</div>
        ${d.stdout ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;max-height:500px;overflow:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:8px">${_esc(d.stdout)}</pre>` : ''}
        ${d.stderr ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;color:var(--err);background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-top:8px">${_esc(d.stderr)}</pre>` : ''}
      </div>`;
    }
  } catch(e) { if (out) out.innerHTML = _card('', `<div style="color:var(--err)">Erreur: ${e.message}</div>`); }
}
