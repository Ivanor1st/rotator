/* ═══════════════════════════════════════════════════════════════
   OPENCLAW.JS v2.0 — Full gateway management
   Tabs: connect · agents · skills · channels · cron · sessions
         tools · config · doctor · memory · chat · hooks
   ═══════════════════════════════════════════════════════════════ */

'use strict';

/* ─── Module state ─── */
let _ocConfig    = null;
let _ocPoller    = null;
let _ocMemFiles  = [];
let _ocChatHistory = [];
let _ocActiveSessions = [];

/* ═══════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════ */

function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function _badge(ok, yes='Oui', no='Non') {
  return ok
    ? `<span style="color:var(--green)">✅ ${yes}</span>`
    : `<span style="color:var(--text-dim)">⚪ ${no}</span>`;
}
function _err(msg) {
  return `<span style="color:var(--red)">❌ ${msg}</span>`;
}
function _dim(s)  { return `<span style="color:var(--text-dim)">${s}</span>`; }
function _mono(s) { return `<code style="font-size:11px;background:var(--surface2);padding:1px 5px;border-radius:4px;color:var(--blue)">${_esc(s)}</code>`; }

function _card(title, body, mt = 0) {
  return `<div class="card"${mt ? ` style="margin-top:${mt}px"` : ''}>
    ${title ? `<div class="card-title">${title}</div>` : ''}
    <div style="font-size:12.5px;line-height:1.8;margin-top:${title ? 8 : 0}px">${body}</div>
  </div>`;
}

function _btn(label, onclick, extra = '') {
  return `<button onclick="${onclick}" ${extra}>${label}</button>`;
}

function _btnDanger(label, onclick) {
  return `<button onclick="${onclick}" style="background:var(--red-dim);border-color:var(--red-bdr);color:var(--red)">${label}</button>`;
}

function _pill(text, color = 'accent') {
  const map = { accent:'var(--accent-dim),var(--accent-bdr),var(--accent)', green:'var(--green-dim),var(--green-bdr),var(--green)', red:'var(--red-dim),var(--red-bdr),var(--red)', blue:'var(--blue-dim),var(--blue-bdr),var(--blue)' };
  const [bg,bdr,col] = (map[color]||map.accent).split(',');
  return `<span style="display:inline-block;background:${bg};border:1px solid ${bdr};color:${col};padding:2px 8px;border-radius:999px;font-size:10.5px;font-weight:600">${_esc(text)}</span>`;
}

function _input(id, placeholder, value='', type='text') {
  return `<input id="${id}" type="${type}" placeholder="${_esc(placeholder)}" value="${_esc(value)}" style="width:100%;margin-top:2px">`;
}

function _select(id, options, selected='') {
  const opts = options.map(([v,l]) => `<option value="${_esc(v)}"${v===selected?' selected':''}>${_esc(l)}</option>`).join('');
  return `<select id="${id}" style="width:100%;margin-top:2px">${opts}</select>`;
}

function _label(text) {
  return `<label style="font-size:11px;color:var(--text-dim);font-weight:600;display:block;margin-bottom:2px">${text}</label>`;
}

function _field(label, content) {
  return `<div>${_label(label)}${content}</div>`;
}

function _codeblock(code, lang = '') {
  return `<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;margin-top:6px">
    ${lang ? `<div style="padding:5px 12px;background:var(--surface2);border-bottom:1px solid var(--border);font-size:10px;color:var(--text-muted);font-family:var(--font-mono);text-transform:uppercase;letter-spacing:.6px">${lang}</div>` : ''}
    <pre style="font-family:var(--font-mono);font-size:11.5px;padding:12px;white-space:pre-wrap;word-break:break-all;margin:0;color:var(--blue);line-height:1.65;max-height:350px;overflow:auto">${_esc(code)}</pre>
  </div>`;
}

function _empty(icon, msg) {
  return `<div style="text-align:center;padding:40px 20px;color:var(--text-dim)">
    <div style="font-size:32px;margin-bottom:10px">${icon}</div>
    <div style="font-size:13px">${msg}</div>
  </div>`;
}

function _spinner() {
  return `<div style="display:flex;align-items:center;gap:8px;color:var(--text-dim);padding:24px 0">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="animation:spin 1s linear infinite">
      <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2.5" stroke-dasharray="40" stroke-dashoffset="10"/>
    </svg>
    Chargement…
  </div>`;
}

async function _ocFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function _ocPost(url, body = {}) {
  return _ocFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

async function _ocGetConfig() {
  if (_ocConfig) return _ocConfig;
  try {
    const d = await _ocFetch('/api/openclaw/config');
    if (d.ok) { _ocConfig = d.config; return _ocConfig; }
  } catch(e) {}
  return {};
}

function _ocInvalidateConfig() { _ocConfig = null; }

function _ocSet(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════
   TAB MANAGEMENT
   ═══════════════════════════════════════════════════════════════ */

const _OC_LOADERS = {
  connect:  ocLoadConnect,
  agents:   ocLoadAgents,
  skills:   ocLoadSkills,
  channels: ocLoadChannels,
  cron:     ocLoadCron,
  sessions: ocLoadSessions,
  tools:    ocLoadTools,
  config:   ocLoadConfig,
  doctor:   ocLoadDoctor,
  memory:   ocLoadMemory,
  chat:     ocLoadChat,
  hooks:    ocLoadHooks,
  guide:    () => {}  // static content
};

function showOCTab(name) {
  document.querySelectorAll('.oc-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.oc-section').forEach(s => s.style.display = 'none');

  const tab = document.querySelector(`.oc-tab[onclick="showOCTab('${name}')"]`);
  if (tab) tab.classList.add('active');

  const sec = document.getElementById(`oc-${name}`);
  if (sec) sec.style.display = 'block';

  if (_OC_LOADERS[name]) _OC_LOADERS[name]();
}

/* Hook into global showTab to auto-load openclaw */
(function() {
  const _orig = window.showTab;
  window.showTab = function(name) {
    if (_orig) _orig(name);
    if (name === 'openclaw') {
      setTimeout(() => {
        _stopStatusPoller();
        showOCTab('connect');
        _startStatusPoller();
      }, 50);
    } else {
      _stopStatusPoller();
    }
  };
})();

/* ─── Status polling ─── */
function _startStatusPoller() {
  _stopStatusPoller();
  _ocPoller = setInterval(_ocPollStatus, 10000);
}
function _stopStatusPoller() {
  if (_ocPoller) { clearInterval(_ocPoller); _ocPoller = null; }
}
async function _ocPollStatus() {
  try {
    const d = await _ocFetch('/api/openclaw/status');
    _updateGatewayDot(d.gateway_running);
  } catch(e) {}
}
function _updateGatewayDot(running) {
  const dot = document.getElementById('ocGatewayDot');
  if (!dot) return;
  dot.style.background = running ? 'var(--green)' : 'var(--text-dim)';
  dot.style.boxShadow  = running ? '0 0 6px var(--green-glow)' : 'none';
}

/* ═══════════════════════════════════════════════════════════════
   1. CONNEXION
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadConnect() {
  const el = document.getElementById('ocConnectContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/status');
    _updateGatewayDot(d.gateway_running);

    let h = '';

    /* ── Prérequis ── */
    h += _card('📦 Prérequis',
      `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 20px">
        <div>Node.js : ${d.node_installed
          ? `<span style="color:var(--green)">✅ ${_esc(d.node_version||'')}</span>`
          : _err('Non installé (Node 22+ requis)')}</div>
        <div>OpenClaw CLI : ${d.openclaw_installed
          ? `<span style="color:var(--green)">✅ ${_esc(d.openclaw_version||'')}</span>`
          : _err('Non installé')}</div>
        <div>Config : ${d.config_exists ? _badge(true,'Trouvée') : _dim('⚪ Absente')}</div>
        <div>Daemon : ${d.daemon_enabled ? _badge(true,'Actif') : _dim('⚪ Désactivé')}</div>
      </div>`);

    /* ── Gateway ── */
    const gwRunning = d.gateway_running;
    h += _card('🌐 Gateway',
      `<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span id="ocGatewayDot" style="width:10px;height:10px;border-radius:50%;flex-shrink:0;transition:all .3s;background:${gwRunning?'var(--green)':'var(--text-dim)'};box-shadow:${gwRunning?'0 0 6px var(--green-glow)':'none'}"></span>
        <span style="font-size:13px;font-weight:600;color:#fff">${gwRunning ? `En cours · Port ${d.gateway_port||18789}` : 'Arrêté'}</span>
        ${gwRunning && d.gateway_uptime ? `<span style="font-size:11px;color:var(--text-dim)">uptime ${_esc(d.gateway_uptime)}</span>` : ''}
      </div>
      ${d.gateway_url ? `<div style="margin-bottom:4px">Control UI : <a href="${_esc(d.gateway_url)}" target="_blank" style="color:var(--accent)">${_esc(d.gateway_url)}</a></div>` : ''}
      ${d.gateway_pid ? `<div style="font-size:11px;color:var(--text-dim)">PID : ${d.gateway_pid}</div>` : ''}`, 12);

    /* ── Provider Rotator ── */
    h += _card('🔗 Intégration Rotator',
      `<div>${d.rotator_configured
        ? `<span style="color:var(--green)">✅ Configuré</span> — 4 modèles : ${['coding','reasoning','chat','long'].map(m=>_pill(m)).join(' ')}`
        : _dim('⚪ Non configuré — cliquez "Injecter Rotator" pour l\'activer')}</div>
       <div style="margin-top:8px">Channels actifs : ${
         d.channels?.length
           ? d.channels.map(c => _pill(c,'blue')).join(' ')
           : _dim('aucun')}</div>`, 12);

    /* ── Actions ── */
    let btns = '';
    if (!d.openclaw_installed)   btns += _btn('📥 Installer OpenClaw', 'ocInstall()', 'id="ocInstallBtn"');
    if (d.openclaw_installed && !d.gateway_running) btns += _btn('▶ Démarrer Gateway', 'ocStartGateway()');
    if (d.gateway_running) {
      btns += _btn('🔄 Restart', 'ocRestartGateway()');
      btns += _btnDanger('⏹ Arrêter', 'ocStopGateway()');
      if (d.gateway_url) btns += _btn('🌐 Control UI', `window.open('${_esc(d.gateway_url)}','_blank')`);
    }
    if (d.openclaw_installed && !d.rotator_configured) btns += _btn('🔧 Injecter Rotator', 'ocConfigureRotator()');
    if (d.openclaw_installed) {
      btns += _btn('🧙 Wizard Onboard', 'ocOnboard()');
      btns += _btn('📋 Copier config curl', 'ocCopyCurlConfig()');
    }
    btns += _btn('🔃 Rafraîchir', 'ocLoadConnect()');

    h += _card('⚡ Actions', `<div style="display:flex;gap:8px;flex-wrap:wrap">${btns}</div>`, 12);

    /* ── Info système ── */
    if (d.system) {
      h += _card('💻 Système', `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 20px;font-size:11.5px">
          ${d.system.os ? `<div>OS : ${_mono(d.system.os)}</div>` : ''}
          ${d.system.arch ? `<div>Arch : ${_mono(d.system.arch)}</div>` : ''}
          ${d.system.memory ? `<div>RAM libre : ${_mono(d.system.memory)}</div>` : ''}
          ${d.system.disk ? `<div>Disque : ${_mono(d.system.disk)}</div>` : ''}
        </div>`, 12);
    }

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur connexion au serveur : ${_esc(e.message)}</div>
      <div style="margin-top:8px">${_btn('🔃 Réessayer','ocLoadConnect()')}</div>`);
  }
}

async function ocInstall() {
  const btn = document.getElementById('ocInstallBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Installation…'; }
  try {
    const d = await _ocPost('/api/openclaw/install');
    if (typeof showToast === 'function') showToast(d.ok ? 'OpenClaw installé !' : 'Erreur: '+(d.error||''), d.ok?'success':'error');
  } catch(e) { if (typeof showToast === 'function') showToast('Erreur: '+e.message,'error'); }
  ocLoadConnect();
}

async function ocStartGateway() {
  try {
    const d = await _ocPost('/api/openclaw/gateway/start');
    if (typeof showToast === 'function') showToast(d.ok ? 'Gateway démarré !' : 'Erreur: '+(d.error||''), d.ok?'success':'error');
  } catch(e) { if (typeof showToast === 'function') showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 2500);
}

async function ocStopGateway() {
  if (!confirm('Arrêter le Gateway OpenClaw ?')) return;
  try {
    const d = await _ocPost('/api/openclaw/gateway/stop');
    if (typeof showToast === 'function') showToast(d.ok ? 'Gateway arrêté.' : 'Erreur: '+(d.error||''), d.ok?'success':'error');
  } catch(e) { if (typeof showToast === 'function') showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 1500);
}

async function ocRestartGateway() {
  try {
    const d = await _ocPost('/api/openclaw/gateway/restart');
    if (typeof showToast === 'function') showToast(d.ok ? 'Gateway redémarré.' : 'Erreur: '+(d.error||''), d.ok?'success':'error');
  } catch(e) { if (typeof showToast === 'function') showToast(e.message,'error'); }
  setTimeout(ocLoadConnect, 3000);
}

async function ocConfigureRotator() {
  try {
    const d = await _ocPost('/api/openclaw/configure-rotator');
    if (d.ok) {
      if (typeof showToast === 'function') showToast('Rotator injecté dans openclaw.json !','success');
      _ocInvalidateConfig();
      ocLoadConnect();
    } else {
      if (typeof showToast === 'function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast === 'function') showToast(e.message,'error'); }
}

async function ocOnboard() {
  try {
    const d = await _ocPost('/api/openclaw/onboard');
    if (typeof showToast === 'function') showToast(d.ok ? 'Wizard lancé dans un terminal.' : 'Erreur','success');
  } catch(e) { if (typeof showToast === 'function') showToast(e.message,'error'); }
}

function ocCopyCurlConfig() {
  const port = document.getElementById('sidebarPort')?.textContent || '47822';
  const cmd = `curl http://localhost:${port}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer rotator" \\
  -d '{"model":"chat","messages":[{"role":"user","content":"Hello!"}]}'`;
  navigator.clipboard.writeText(cmd).then(() => {
    if (typeof showToast === 'function') showToast('Config curl copiée !','success');
  });
}

/* ═══════════════════════════════════════════════════════════════
   2. AGENTS — Read + Create + Edit + Delete
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadAgents() {
  const el = document.getElementById('ocAgentsContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/agents');
    const def = d.defaults || {};
    const agents = d.list || [];
    let h = '';

    /* ── Defaults ── */
    const model = def.model || {};
    h += _card('🎯 Paramètres par défaut', `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 20px">
        <div>Modèle principal : ${model.primary ? _mono(model.primary) : _dim('non défini')}</div>
        <div>Max concurrent : ${def.maxConcurrent||1}</div>
        <div>Fallbacks : ${(model.fallbacks||[]).length ? model.fallbacks.map(_mono).join(', ') : _dim('aucun')}</div>
        <div>Timeout : ${def.timeoutSeconds||600}s</div>
        <div>Workspace : ${_mono(def.workspace||'~/.openclaw/workspace')}</div>
        <div>Thinking : ${_mono(def.thinkingDefault||'off')}</div>
        <div>Context tokens : ${(def.contextTokens||200000).toLocaleString()}</div>
      </div>`);

    /* ── Heartbeat ── */
    const hb = def.heartbeat || {};
    if (Object.keys(hb).length) {
      h += _card('💓 Heartbeat', `
        <div>Intervalle : ${_mono(hb.every||'30m')}</div>
        <div>Session : ${_mono(hb.session||'main')}</div>
        <div>Modèle : ${hb.model ? _mono(hb.model) : _dim('default')}</div>
        <div>Target : ${_mono(hb.target||'last')}</div>`, 12);
    }

    /* ── Compaction ── */
    const comp = def.compaction || {};
    if (Object.keys(comp).length) {
      h += _card('📦 Compaction mémoire', `
        <div>Mode : ${_mono(comp.mode||'default')}</div>
        <div>Reserve tokens : ${comp.reserveTokensFloor||24000}</div>
        <div>Memory flush : ${comp.memoryFlush?.enabled ? '✅ Actif' : '❌ Inactif'}</div>`, 12);
    }

    /* ── Agents list ── */
    if (agents.length) {
      h += `<div style="margin-top:16px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:13.5px;font-weight:700;color:#fff">🤖 Agents configurés</div>
          ${_btn('➕ Nouvel agent','ocShowAgentForm()')}
        </div>`;
      for (const ag of agents) {
        const id = ag.identity || {};
        h += `<div class="card" style="margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <span style="font-size:20px">${id.emoji||'🤖'}</span>
            <div style="flex:1">
              <div style="font-weight:700;color:#fff">${_esc(ag.id)}${ag.default ? ' '+_pill('default','green') : ''}</div>
              ${id.name ? `<div style="font-size:11.5px;color:var(--text-dim)">${_esc(id.name)}</div>` : ''}
            </div>
            <div style="display:flex;gap:6px">
              ${_btn('✏️','ocShowAgentForm('+JSON.stringify(_esc(ag.id))+')')}
              ${_btnDanger('🗑','ocDeleteAgent('+JSON.stringify(_esc(ag.id))+')')}
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 16px;font-size:11.5px;color:var(--text-dim)">
            <div>Workspace : ${ag.workspace ? _mono(ag.workspace) : _dim('default')}</div>
            <div>Modèle : ${ag.model ? _mono(typeof ag.model==='string'?ag.model:ag.model.primary) : _dim('default')}</div>
            ${ag.tools?.profile ? `<div>Tool profile : ${_mono(ag.tools.profile)}</div>` : ''}
            ${(ag.groupChat?.mentionPatterns||[]).length ? `<div>Mention : ${ag.groupChat.mentionPatterns.map(_mono).join(', ')}</div>` : ''}
          </div>
        </div>`;
      }
      h += '</div>';
    } else {
      h += _card('🤖 Agents', `
        <div>${_dim('Aucun agent configuré — l\'agent par défaut utilise les paramètres ci-dessus.')}</div>
        <div style="margin-top:8px">${_btn('➕ Créer mon premier agent','ocShowAgentForm()')}</div>`, 12);
    }

    /* ── Inline form (hidden) ── */
    h += `<div id="ocAgentForm" style="display:none;margin-top:16px">
      <div class="card" style="border-color:var(--accent-bdr)">
        <div class="card-title" id="ocAgentFormTitle">➕ Nouvel agent</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px">
          ${_field('ID (slug unique)', _input('ocAgentId','mon-agent'))}
          ${_field('Emoji', _input('ocAgentEmoji','🤖'))}
          ${_field('Nom affiché', _input('ocAgentName','Mon agent'))}
          ${_field('Workspace path', _input('ocAgentWorkspace','~/.openclaw/workspace'))}
          ${_field('Modèle principal', _input('ocAgentModel','coding'))}
          ${_field('Tool profile', _select('ocAgentToolProfile',[['full','full'],['coding','coding'],['read-only','read-only'],['safe','safe']]))}
          <div style="grid-column:1/-1">${_field('Mention patterns (séparés par virgule)', _input('ocAgentMentions','@agent'))}</div>
          <div style="grid-column:1/-1;display:flex;gap:8px">
            ${_btn('💾 Sauvegarder','ocSaveAgent()')}
            ${_btn('Annuler','ocHideAgentForm()')}
          </div>
        </div>
      </div>
    </div>`;

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadAgents()')}`);
  }
}

function ocShowAgentForm(agentId) {
  const form = document.getElementById('ocAgentForm');
  if (!form) return;
  document.getElementById('ocAgentFormTitle').textContent = agentId ? `✏️ Modifier ${agentId}` : '➕ Nouvel agent';
  document.getElementById('ocAgentId').value  = agentId || '';
  document.getElementById('ocAgentId').disabled = !!agentId;
  form.style.display = 'block';
  form.scrollIntoView({ behavior:'smooth', block:'center' });
}

function ocHideAgentForm() {
  const form = document.getElementById('ocAgentForm');
  if (form) form.style.display = 'none';
}

async function ocSaveAgent() {
  const id       = document.getElementById('ocAgentId')?.value?.trim();
  const emoji    = document.getElementById('ocAgentEmoji')?.value?.trim() || '🤖';
  const name     = document.getElementById('ocAgentName')?.value?.trim();
  const workspace= document.getElementById('ocAgentWorkspace')?.value?.trim();
  const model    = document.getElementById('ocAgentModel')?.value?.trim();
  const profile  = document.getElementById('ocAgentToolProfile')?.value;
  const mentions = document.getElementById('ocAgentMentions')?.value?.split(',').map(s=>s.trim()).filter(Boolean);

  if (!id) { if (typeof showToast==='function') showToast('ID requis','error'); return; }

  const payload = { id, identity:{ emoji, name }, workspace, model, tools:{ profile }, groupChat:{ mentionPatterns: mentions } };
  try {
    const d = await _ocPost('/api/openclaw/agents/save', payload);
    if (d.ok) {
      if (typeof showToast==='function') showToast('Agent sauvegardé !','success');
      _ocInvalidateConfig();
      ocHideAgentForm();
      ocLoadAgents();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocDeleteAgent(agentId) {
  if (!confirm(`Supprimer l'agent "${agentId}" ?`)) return;
  try {
    const d = await _ocPost('/api/openclaw/agents/delete', { id: agentId });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Agent supprimé.','success');
      _ocInvalidateConfig();
      ocLoadAgents();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   3. SKILLS — Runtime + Config + Install from ClawHub
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadSkills() {
  const el = document.getElementById('ocSkillsContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/skills/list');
    let h = '';

    /* ── Runtime output ── */
    if (d.cli_output) {
      h += _card('🧩 Skills actifs (runtime)', _codeblock(d.cli_output));
    } else {
      h += _card('🧩 Skills', `
        ${_dim('CLI non disponible.')}
        ${d.cli_error ? `<div style="color:var(--red);font-size:11.5px;margin-top:4px">${_esc(d.cli_error)}</div>` : ''}`);
    }

    /* ── Config entries ── */
    const entries = d.config_entries || {};
    const keys = Object.keys(entries);
    if (keys.length) {
      let rows = keys.map(name => {
        const e = entries[name];
        const enabled = e.enabled !== false;
        return `<tr>
          <td style="padding:6px 10px">${_mono(name)}</td>
          <td style="padding:6px 10px;text-align:center">${enabled ? '✅' : '❌'}</td>
          <td style="padding:6px 10px;text-align:center">${e.apiKey||e.env ? '🔑' : _dim('—')}</td>
          <td style="padding:6px 10px">
            <button onclick="ocToggleSkill('${name}',${!enabled})" style="font-size:11px">
              ${enabled ? '⏸ Désactiver' : '▶ Activer'}
            </button>
          </td>
        </tr>`;
      }).join('');

      h += _card('⚙️ Config skills (openclaw.json)', `
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:6px">
          <thead><tr style="border-bottom:1px solid var(--border);color:var(--text-muted);font-size:10.5px;text-transform:uppercase">
            <th style="text-align:left;padding:5px 10px">Skill</th>
            <th style="padding:5px 10px">Actif</th>
            <th style="padding:5px 10px">Clé</th>
            <th style="padding:5px 10px">Action</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>`, 12);
    }

    /* ── ClawHub install ── */
    h += _card('🦞 Installer depuis ClawHub', `
      <div style="display:flex;gap:8px;margin-top:4px">
        <input id="ocSkillSlug" placeholder="ex: calendar, github, notion…" style="flex:1">
        ${_btn('🔍 Rechercher','ocSearchSkill()')}
        ${_btn('📥 Installer','ocInstallSkill()')}
      </div>
      <div id="ocSkillSearchResult" style="margin-top:10px"></div>
      <div style="font-size:11.5px;color:var(--text-dim);margin-top:8px">
        Browse → <a href="https://clawhub.ai" target="_blank" style="color:var(--accent)">clawhub.ai</a>
      </div>`, 12);

    /* ── Emplacements ── */
    h += _card('📁 Ordre de résolution des skills', `
      <div style="font-size:11.5px;color:var(--text-dim);line-height:1.9">
        <div><span style="color:#fff;font-weight:600">1.</span> Workspace : ${_mono('<workspace>/skills')} (priorité max)</div>
        <div><span style="color:#fff;font-weight:600">2.</span> Managed : ${_mono('~/.openclaw/skills')}</div>
        <div><span style="color:#fff;font-weight:600">3.</span> Bundled : inclus dans le package npm</div>
      </div>`, 12);

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadSkills()')}`);
  }
}

async function ocToggleSkill(name, enable) {
  try {
    const d = await _ocPost('/api/openclaw/skills/toggle', { name, enabled: enable });
    if (d.ok) {
      if (typeof showToast==='function') showToast(`Skill ${name} ${enable?'activé':'désactivé'}.`,'success');
      _ocInvalidateConfig();
      ocLoadSkills();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocSearchSkill() {
  const slug = document.getElementById('ocSkillSlug')?.value?.trim();
  const out  = document.getElementById('ocSkillSearchResult');
  if (!slug || !out) return;
  out.innerHTML = _dim('Recherche…');
  try {
    const d = await _ocFetch(`/api/openclaw/skills/search?q=${encodeURIComponent(slug)}`);
    if (d.results?.length) {
      out.innerHTML = d.results.map(r => `
        <div style="padding:8px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--r);margin-bottom:6px">
          <div style="font-weight:600;color:#fff">${_esc(r.name)} ${_pill(r.slug,'blue')}</div>
          <div style="font-size:11.5px;color:var(--text-dim);margin-top:3px">${_esc(r.description||'')}</div>
          <button onclick="ocInstallSkillById('${_esc(r.slug)}')" style="margin-top:6px;font-size:11px">📥 Installer</button>
        </div>`).join('');
    } else {
      out.innerHTML = _dim('Aucun résultat pour "'+_esc(slug)+'"');
    }
  } catch(e) { out.innerHTML = _err('Erreur : '+_esc(e.message)); }
}

async function ocInstallSkill() {
  const slug = document.getElementById('ocSkillSlug')?.value?.trim();
  if (!slug) { if (typeof showToast==='function') showToast('Entrez un slug','error'); return; }
  await ocInstallSkillById(slug);
}

async function ocInstallSkillById(slug) {
  try {
    const d = await _ocPost('/api/openclaw/cli', { args: ['skills','install',slug], timeout: 60 });
    if (d.ok || d.exit_code === 0) {
      if (typeof showToast==='function') showToast(`Skill "${slug}" installé !`,'success');
      _ocInvalidateConfig();
      ocLoadSkills();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.stderr||d.stdout||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   4. CHANNELS — Status + Login + QR + Model overrides
   ═══════════════════════════════════════════════════════════════ */

const _OC_CH_ICONS  = {whatsapp:'💬',telegram:'✈️',discord:'🎮',slack:'💼',imessage:'📱',signal:'🔒',mattermost:'💬',googlechat:'📧',msteams:'👔',line:'💚',matrix:'🟦'};
const _OC_CH_LABELS = {whatsapp:'WhatsApp',telegram:'Telegram',discord:'Discord',slack:'Slack',imessage:'iMessage',signal:'Signal',mattermost:'Mattermost',googlechat:'Google Chat',msteams:'MS Teams',line:'LINE',matrix:'Matrix'};

async function ocLoadChannels() {
  const el = document.getElementById('ocChannelsContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/channels/details');
    const channels = d.channels || {};
    const names = Object.keys(channels);
    let h = '';

    if (names.length) {
      for (const name of names) {
        const ch = channels[name];
        const icon  = _OC_CH_ICONS[name]  || '📡';
        const label = _OC_CH_LABELS[name] || name;
        const enabled = ch.enabled !== false;
        const connected = !!ch.connected;

        h += `<div class="card" style="margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <span style="font-size:20px">${icon}</span>
            <div style="flex:1">
              <div style="font-weight:700;color:#fff">${label}</div>
              <div style="font-size:11px;color:var(--text-dim)">${name}</div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              ${connected ? _pill('Connecté','green') : (enabled ? _pill('Configuré','blue') : _pill('Désactivé','red'))}
              ${_btn(`🔗 Login`, `ocChannelLogin('${name}')`)}
              ${_btn('⚙️', `ocShowChannelConfig('${name}')`)}
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:4px 16px;font-size:11.5px">
            <div>DM Policy : ${_mono(ch.dmPolicy||'pairing')}</div>
            <div>Group Policy : ${_mono(ch.groupPolicy||'allowlist')}</div>
            <div>Token : ${ch.hasToken ? '🔑 Présent' : _dim('absent')}</div>
            <div>Streaming : ${ch.streaming!==false ? '✅' : '❌'}</div>
            ${ch.historyLimit ? `<div>History limit : ${ch.historyLimit}</div>` : ''}
          </div>
          ${ch.allowFrom?.length ? `<div style="margin-top:6px;font-size:11.5px">Allow from : ${ch.allowFrom.map(_mono).join(', ')}</div>` : ''}
        </div>`;
      }
    } else {
      h += _empty('📱', 'Aucun channel configuré dans openclaw.json');
    }

    /* ── Model overrides ── */
    const mbc = d.modelByChannel || {};
    if (Object.keys(mbc).length) {
      let rows = '';
      for (const [ch, map] of Object.entries(mbc)) {
        if (typeof map === 'object') {
          for (const [id, model] of Object.entries(map)) {
            rows += `<tr>
              <td style="padding:5px 10px">${_OC_CH_ICONS[ch]||'📡'} ${ch}</td>
              <td style="padding:5px 10px">${_mono(id)}</td>
              <td style="padding:5px 10px">${_mono(model)}</td>
            </tr>`;
          }
        }
      }
      if (rows) {
        h += _card('🎯 Model overrides', `
          <table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px">
            <thead><tr style="border-bottom:1px solid var(--border);font-size:10.5px;text-transform:uppercase;color:var(--text-muted)">
              <th style="text-align:left;padding:5px 10px">Channel</th>
              <th style="text-align:left;padding:5px 10px">User ID</th>
              <th style="text-align:left;padding:5px 10px">Modèle</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>`, 12);
      }
    }

    /* ── Add guide ── */
    h += _card('📖 Ajouter un channel', _codeblock(
`# WhatsApp (QR code)
openclaw channels login --channel whatsapp

# Telegram
openclaw channels add --channel telegram --token BOT_TOKEN

# Discord
openclaw channels add --channel discord --token DISCORD_TOKEN

# Slack
openclaw channels add --channel slack --token BOT_TOKEN --app-token APP_TOKEN

# Signal (via signal-cli)
openclaw channels add --channel signal --number +33600000000`, 'bash'), 12);

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadChannels()')}`);
  }
}

async function ocChannelLogin(channel) {
  try {
    const d = await _ocPost('/api/openclaw/channels/login', { channel });
    if (d.ok) {
      if (typeof showToast==='function') showToast(`Login ${channel} ouvert dans un terminal.`,'success');
      if (d.qr_url) {
        window.open(d.qr_url, '_blank');
      }
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocShowChannelConfig(channel) {
  try {
    const cfg = await _ocGetConfig();
    const ch = cfg?.channels?.[channel] || {};
    const json = JSON.stringify(ch, null, 2);
    const modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    modal.innerHTML = `
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);width:min(600px,100%);max-height:80vh;display:flex;flex-direction:column">
        <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
          <div style="font-weight:700;color:#fff">${_OC_CH_ICONS[channel]||'📡'} Config ${channel}</div>
          <button onclick="this.closest('.oc-modal').remove()" style="padding:4px 8px">✕</button>
        </div>
        <div style="padding:16px;overflow:auto;flex:1">
          <textarea style="width:100%;min-height:300px;font-family:var(--font-mono);font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;color:#fff;resize:vertical">${_esc(json)}</textarea>
        </div>
      </div>`;
    modal.classList.add('oc-modal');
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  } catch(e) {}
}

/* ═══════════════════════════════════════════════════════════════
   5. CRON — List + Add + Edit + Run + Remove
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadCron() {
  const el = document.getElementById('ocCronContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/cron/list');
    const jobs = d.jobs || [];
    let h = '';

    /* ── Jobs ── */
    if (jobs.length) {
      let rows = jobs.map(j => {
        const sched = j.schedule || {};
        const schedStr = sched.kind==='cron' ? sched.expr
          : sched.kind==='every' ? `every ${sched.everyMs}ms`
          : sched.kind==='at' ? `at ${sched.at}` : JSON.stringify(sched);
        const jid = _esc(j.jobId||j.id||j.name||'');
        const jname = _esc(j.name||j.jobId||'—');
        return `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:7px 10px;font-weight:600;color:#fff">${jname}</td>
          <td style="padding:7px 10px;font-family:var(--font-mono);font-size:11px">${_esc(schedStr)}</td>
          <td style="padding:7px 10px">${_mono(j.sessionTarget||'main')}</td>
          <td style="padding:7px 10px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px;color:var(--text-dim)">${_esc((j.message||'').substring(0,60))}</td>
          <td style="padding:7px 10px;text-align:center">${j.enabled!==false?'✅':'❌'}</td>
          <td style="padding:7px 10px;white-space:nowrap">
            ${_btn('▶','ocCronRun(\''+jid+'\')')}
            ${_btn('✏️','ocShowCronEdit(\''+jid+'\')')}
            ${_btnDanger('🗑','ocCronRemove(\''+jid+'\')')}
          </td>
        </tr>`;
      }).join('');

      h += _card('⏰ Cron Jobs', `
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:6px">
          <thead><tr style="border-bottom:2px solid var(--border);font-size:10.5px;text-transform:uppercase;color:var(--text-muted)">
            <th style="text-align:left;padding:5px 10px">Nom</th>
            <th style="text-align:left;padding:5px 10px">Schedule</th>
            <th style="padding:5px 10px">Session</th>
            <th style="text-align:left;padding:5px 10px">Message</th>
            <th style="padding:5px 10px">Actif</th>
            <th style="padding:5px 10px">Actions</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>`);
    } else {
      h += _empty('⏰', 'Aucun cron job configuré.');
    }

    /* ── Add / Edit form ── */
    h += `<div class="card" style="margin-top:12px">
      <div class="card-title" id="ocCronFormTitle">➕ Ajouter un cron job</div>
      <input type="hidden" id="ocCronEditId">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px">
        ${_field('Nom', _input('ocCronName','Morning brief'))}
        ${_field('Expression cron', _input('ocCronExpr','0 7 * * *'))}
        ${_field('Timezone', _input('ocCronTz','Europe/Paris','Europe/Paris'))}
        ${_field('Session', _select('ocCronSession',[['isolated','isolated'],['main','main']]))}
        <div style="grid-column:1/-1">${_field('Message / Prompt', _input('ocCronMsg','Summarize overnight updates.'))}</div>
        <div style="grid-column:1/-1">${_field('Channel de livraison',
          _select('ocCronChannel',[
            ['','Aucun (announce)'],
            ['whatsapp','WhatsApp'],
            ['telegram','Telegram'],
            ['discord','Discord'],
            ['slack','Slack']]))}</div>
        <div style="grid-column:1/-1;display:flex;gap:8px">
          ${_btn('💾 Créer / Sauvegarder','ocCronSave()')}
          <button onclick="ocCronResetForm()" id="ocCronCancelEdit" style="display:none">Annuler</button>
        </div>
      </div>
    </div>`;

    /* ── CLI ref ── */
    h += _card('📖 Référence CLI', _codeblock(
`openclaw cron list
openclaw cron add --name "Test" --cron "0 7 * * *" --session isolated --message "Hello"
openclaw cron run <jobId>
openclaw cron edit <jobId> --message "Updated message"
openclaw cron remove <jobId>
openclaw cron runs --id <jobId> --limit 10`, 'bash'), 12);

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadCron()')}`);
  }
}

function ocShowCronEdit(jobId) {
  document.getElementById('ocCronFormTitle').textContent = `✏️ Modifier le job`;
  document.getElementById('ocCronEditId').value = jobId;
  document.getElementById('ocCronCancelEdit').style.display = 'inline-flex';
  const form = document.querySelector('#oc-cron .card:last-child');
  form?.scrollIntoView({ behavior:'smooth', block:'center' });
}

function ocCronResetForm() {
  document.getElementById('ocCronFormTitle').textContent = '➕ Ajouter un cron job';
  document.getElementById('ocCronEditId').value = '';
  document.getElementById('ocCronName').value = '';
  document.getElementById('ocCronExpr').value = '';
  document.getElementById('ocCronMsg').value = '';
  document.getElementById('ocCronCancelEdit').style.display = 'none';
}

async function ocCronSave() {
  const editId  = document.getElementById('ocCronEditId')?.value;
  const name    = document.getElementById('ocCronName')?.value;
  const expr    = document.getElementById('ocCronExpr')?.value;
  const tz      = document.getElementById('ocCronTz')?.value || 'UTC';
  const session = document.getElementById('ocCronSession')?.value || 'isolated';
  const msg     = document.getElementById('ocCronMsg')?.value;
  const channel = document.getElementById('ocCronChannel')?.value;

  if (!name || !expr || !msg) { if (typeof showToast==='function') showToast('Nom, expression et message requis.','error'); return; }

  let args;
  if (editId) {
    args = ['cron','edit',editId,'--message',msg];
    if (channel) args.push('--channel',channel);
  } else {
    args = ['cron','add','--name',name,'--cron',expr,'--tz',tz,'--session',session,'--message',msg];
    if (channel) args.push('--announce','--channel',channel);
  }

  try {
    const d = await _ocPost('/api/openclaw/cli', { args, timeout:30 });
    if (typeof showToast==='function') showToast(d.ok ? (editId?'Job mis à jour !':'Job créé !') : 'Erreur: '+(d.stderr||d.stdout||''), d.ok?'success':'error');
    if (d.ok) { ocCronResetForm(); ocLoadCron(); }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocCronRun(jobId) {
  try {
    const d = await _ocPost('/api/openclaw/cli', { args:['cron','run',jobId], timeout:60 });
    if (typeof showToast==='function') showToast(d.ok?'Job exécuté !':'Erreur: '+(d.stderr||''), d.ok?'success':'error');
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocCronRemove(jobId) {
  if (!confirm(`Supprimer le job "${jobId}" ?`)) return;
  try {
    const d = await _ocPost('/api/openclaw/cli', { args:['cron','remove',jobId], timeout:15 });
    if (typeof showToast==='function') showToast(d.ok?'Job supprimé.':'Erreur: '+(d.stderr||''), d.ok?'success':'error');
    if (d.ok) ocLoadCron();
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   6. SESSIONS — Live list + Config + Reset + Send message
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadSessions() {
  const el = document.getElementById('ocSessionsContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const [configData, liveData] = await Promise.allSettled([
      _ocFetch('/api/openclaw/sessions/config'),
      _ocFetch('/api/openclaw/sessions/live')
    ]);

    const dc = configData.status === 'fulfilled' ? configData.value : {};
    const dl = liveData.status  === 'fulfilled' ? liveData.value  : {};
    const sess = dc.session || {};
    const msgs  = dc.messages || {};
    const live  = dl.sessions || [];
    let h = '';

    /* ── Live sessions ── */
    h += `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <div style="font-size:13.5px;font-weight:700;color:#fff">💬 Sessions actives</div>
      ${_btn('🔃 Rafraîchir','ocLoadSessions()')}
    </div>`;

    if (live.length) {
      live.forEach((s, i) => {
        const lastMsg = s.last_message?.substring(0,80) || '—';
        h += `<div class="card" style="margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:10px">
            <div style="width:8px;height:8px;border-radius:50%;background:${s.active?'var(--green)':'var(--text-dim)'};flex-shrink:0"></div>
            <div style="flex:1">
              <div style="font-weight:600;color:#fff">${_mono(s.session_id||s.id||'session-'+i)}</div>
              <div style="font-size:11px;color:var(--text-dim)">${_esc(s.channel||'')} ${s.sender?'· '+_esc(s.sender):''} ${s.last_active?'· '+_esc(s.last_active):''}</div>
            </div>
            <div style="display:flex;gap:6px">
              ${_btn('💬 Envoyer','ocShowSendMessage(\''+_esc(s.session_id||s.id||'main')+'\')')}
              ${_btnDanger('↺ Reset','ocResetSession(\''+_esc(s.session_id||s.id||'main')+'\')')}
            </div>
          </div>
          ${s.last_message ? `<div style="font-size:11px;color:var(--text-dim);margin-top:6px;padding:6px 8px;background:var(--surface2);border-radius:6px">… ${_esc(lastMsg)}${s.last_message.length>80?'…':''}</div>` : ''}
        </div>`;
      });
    } else {
      h += _empty('💬','Aucune session active') + `<div style="text-align:center;margin-top:-16px">${_btn('💬 Envoyer vers main','ocShowSendMessage(\'main\')')}</div>`;
    }

    /* ── Send message form ── */
    h += `<div id="ocSendMsgPanel" style="display:none;margin-top:12px">
      <div class="card" style="border-color:var(--accent-bdr)">
        <div class="card-title">📨 Envoyer un message — <span id="ocSendMsgTarget" style="color:var(--accent)">main</span></div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <textarea id="ocSendMsgText" placeholder="Écrivez votre message…" style="flex:1;min-height:80px;font-family:var(--font-ui);font-size:13px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;color:#fff;resize:vertical"></textarea>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px">
          ${_btn('📨 Envoyer','ocSendMessage()')}
          ${_btn('Annuler','ocHideSendMessage()')}
        </div>
      </div>
    </div>`;

    /* ── Config ── */
    h += _card('⚙️ Configuration sessions', `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 20px">
        <div>Scope : ${_mono(sess.scope||'per-sender')}</div>
        <div>DM scope : ${_mono(sess.dmScope||'main')}</div>
        <div>Reset mode : ${_mono(sess.reset?.mode||'daily')}</div>
        ${sess.reset?.atHour!==undefined ? `<div>Reset à : ${sess.reset.atHour}h</div>` : ''}
        ${sess.reset?.idleMinutes ? `<div>Idle : ${sess.reset.idleMinutes}min</div>` : ''}
        <div>Triggers : ${(sess.resetTriggers||['/new','/reset']).map(_mono).join(', ')}</div>
      </div>`, 12);

    /* ── Message queue ── */
    const queue = msgs.queue || {};
    h += _card('📨 File de messages', `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 20px">
        <div>Mode : ${_mono(queue.mode||'collect')}</div>
        <div>Debounce : ${queue.debounceMs||1000}ms</div>
        <div>Cap : ${queue.cap||20}</div>
        <div>Ack : ${msgs.ackReaction||'👀'}</div>
        <div>Prefix : ${msgs.responsePrefix ? _mono(msgs.responsePrefix) : _dim('—')}</div>
      </div>`, 12);

    /* ── TTS ── */
    const tts = msgs.tts || {};
    if (Object.keys(tts).length) {
      h += _card('🔊 TTS', `
        <div>Auto : ${_mono(tts.auto||'off')}</div>
        <div>Mode : ${_mono(tts.mode||'final')}</div>
        <div>Provider : ${_mono(tts.provider||'elevenlabs')}</div>
        <div>Max chars : ${tts.maxTextLength||4000}</div>`, 12);
    }

    /* ── Identity links ── */
    if (sess.identityLinks && Object.keys(sess.identityLinks).length) {
      let links = Object.entries(sess.identityLinks)
        .map(([name,ids]) => `<div><strong style="color:#fff">${_esc(name)}</strong> : ${ids.map(_mono).join(', ')}</div>`)
        .join('');
      h += _card('🔗 Identity Links', links, 12);
    }

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadSessions()')}`);
  }
}

function ocShowSendMessage(sessionId) {
  const panel = document.getElementById('ocSendMsgPanel');
  const target = document.getElementById('ocSendMsgTarget');
  if (!panel || !target) return;
  target.textContent = sessionId;
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior:'smooth', block:'center' });
  document.getElementById('ocSendMsgText')?.focus();
}

function ocHideSendMessage() {
  const panel = document.getElementById('ocSendMsgPanel');
  if (panel) panel.style.display = 'none';
}

async function ocSendMessage() {
  const target = document.getElementById('ocSendMsgTarget')?.textContent || 'main';
  const text   = document.getElementById('ocSendMsgText')?.value?.trim();
  if (!text) { if (typeof showToast==='function') showToast('Message vide','error'); return; }
  try {
    const d = await _ocPost('/api/openclaw/sessions/send', { session_id: target, message: text });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Message envoyé !','success');
      document.getElementById('ocSendMsgText').value = '';
      ocHideSendMessage();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocResetSession(sessionId) {
  if (!confirm(`Reset la session "${sessionId}" ? L'historique sera effacé.`)) return;
  try {
    const d = await _ocPost('/api/openclaw/sessions/reset', { session_id: sessionId });
    if (typeof showToast==='function') showToast(d.ok?'Session réinitialisée.':'Erreur: '+(d.error||''), d.ok?'success':'error');
    if (d.ok) ocLoadSessions();
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   7. TOOLS
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadTools() {
  const el = document.getElementById('ocToolsContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/tools/config');
    const tools   = d.tools   || {};
    const browser = d.browser || {};
    let h = '';

    /* ── Profile ── */
    h += _card('🔧 Profil & accès', `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 20px">
        <div>Profile : ${_mono(tools.profile||'full')}</div>
        <div>Allow : ${(tools.allow||[]).length ? tools.allow.map(_mono).join(', ') : _dim('tout')}</div>
        <div>Deny : ${(tools.deny||[]).length ? tools.deny.map(_mono).join(', ') : _dim('aucun')}</div>
        <div>Elevated : ${tools.elevated?.enabled ? '✅ Actif' : '❌ Inactif'}</div>
      </div>`);

    /* ── Groups ── */
    h += _card('📦 Tool Groups', `
      <table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:4px">
        ${[
          ['group:runtime','exec, bash, process'],
          ['group:fs','read, write, edit, apply_patch'],
          ['group:sessions','sessions_list, sessions_history, sessions_send, sessions_spawn'],
          ['group:memory','memory_search, memory_get'],
          ['group:web','web_search, web_fetch'],
          ['group:ui','browser, canvas'],
          ['group:automation','cron, gateway'],
          ['group:messaging','message']
        ].map(([g,d]) => `<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:5px 10px">${_mono(g)}</td>
          <td style="padding:5px 10px;color:var(--text-dim)">${d}</td>
        </tr>`).join('')}
      </table>`, 12);

    /* ── Exec ── */
    const exec = tools.exec || {};
    h += _card('⚙️ Exec', `
      <div>Background timeout : ${exec.backgroundMs||10000}ms</div>
      <div>Max timeout : ${exec.timeoutSec||1800}s</div>
      <div>Notify on exit : ${exec.notifyOnExit!==false?'✅':'❌'}</div>
      <div>apply_patch : ${exec.applyPatch?.enabled?'✅ Actif':'❌ Inactif'}</div>`, 12);

    /* ── Web ── */
    const web = tools.web || {};
    h += _card('🌐 Web tools', `
      <div>Search : ${web.search?.enabled!==false?'✅':'❌'} ${web.search?.apiKey?'(clé Brave configurée)':_dim('(no Brave key)')}</div>
      <div>Fetch : ${web.fetch?.enabled!==false?'✅':'❌'} · max ${web.fetch?.maxChars||50000} chars</div>`, 12);

    /* ── Browser ── */
    h += _card('🌍 Browser CDP', `
      <div>Enabled : ${browser.enabled!==false?'✅':'❌'}</div>
      <div>Default profile : ${_mono(browser.defaultProfile||'chrome')}</div>
      ${browser.profiles?`<div>Profiles : ${Object.keys(browser.profiles).map(_mono).join(', ')}</div>`:''}
      <div>JS evaluate : ${browser.evaluateEnabled!==false?'✅':'❌'}</div>`, 12);

    /* ── Loop detection ── */
    const loop = tools.loopDetection || {};
    if (Object.keys(loop).length) {
      h += _card('🔄 Loop detection', `
        <div>Enabled : ${loop.enabled?'✅':'❌'}</div>
        <div>Warning : ${loop.warningThreshold||10}</div>
        <div>Critical : ${loop.criticalThreshold||20}</div>
        <div>Circuit breaker : ${loop.globalCircuitBreakerThreshold||30}</div>`, 12);
    }

    /* ── Sub-agents ── */
    const sub = tools.subagents || {};
    if (Object.keys(sub).length) {
      h += _card('🧬 Sub-agents', `
        ${sub.model?`<div>Modèle : ${_mono(sub.model)}</div>`:''}
        <div>Max concurrent : ${sub.maxConcurrent||1}</div>
        ${tools.sessions?.visibility?`<div>Session visibility : ${_mono(tools.sessions.visibility)}</div>`:''}`, 12);
    }

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadTools()')}`);
  }
}

/* ═══════════════════════════════════════════════════════════════
   8. CONFIG — JSON editor full + validation + save
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadConfig() {
  const el = document.getElementById('ocConfigContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/config');
    if (d.ok && d.config) {
      _ocConfig = d.config;
      el.innerHTML = `
        <div class="card">
          <div class="card-title">📄 ${_esc(d.path||'~/.openclaw/openclaw.json')}</div>
          <div style="margin-top:10px;position:relative">
            <textarea id="ocConfigEditor"
              style="width:100%;min-height:520px;font-family:var(--font-mono);font-size:11.5px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;color:#c5d4ec;resize:vertical;line-height:1.65;outline:none;transition:border-color .15s"
              onfocus="this.style.borderColor='var(--accent-bdr)'"
              onblur="this.style.borderColor='var(--border)'"
              spellcheck="false">${_esc(JSON.stringify(d.config, null, 2))}</textarea>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center">
            ${_btn('💾 Sauvegarder','ocSaveConfig()')}
            ${_btn('🔧 Injecter Rotator','ocConfigureRotator()')}
            ${_btn('📋 Formater','ocFormatConfig()')}
            ${_btn('✅ Valider JSON','ocValidateConfig()')}
            ${_btn('🔃 Recharger','ocLoadConfig()')}
            ${_btn('⬇ Télécharger','ocDownloadConfig()')}
            <span id="ocConfigStatus" style="font-size:11.5px;color:var(--text-dim)"></span>
          </div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="card-title">📖 Sections clés</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11.5px;margin-top:8px">
            ${[
              ['channels','WhatsApp, Telegram, Discord, Slack, iMessage, Signal…'],
              ['agents.defaults','Modèles, workspace, heartbeat, compaction'],
              ['agents.list','Agents multi-agent avec identité et isolation'],
              ['tools','Profils, allow/deny, exec, browser, web'],
              ['skills','Skills config, entries, allowBundled'],
              ['session','Scope, reset, identity links'],
              ['messages','Queue, prefix, ack, TTS'],
              ['cron','Scheduler enabled, max concurrent'],
              ['gateway','Port, bind, auth, tailscale, Control UI'],
              ['hooks','Gmail, webhooks, mappings'],
              ['models.providers','Custom providers (ex: rotator)'],
              ['browser','Profils CDP, auto-detect'],
              ['plugins','Extensions additionnelles'],
              ['env','Variables d\'environnement inline'],
            ].map(([k,v]) => `<div style="padding:5px 8px;background:var(--surface2);border-radius:6px">
              ${_mono(k)} <span style="color:var(--text-dim)">— ${v}</span>
            </div>`).join('')}
          </div>
        </div>`;
    } else {
      el.innerHTML = _card('📄 Config', `
        <div>${_dim('Aucune config trouvée.')}</div>
        <div style="margin-top:10px;display:flex;gap:8px">
          ${_btn('🧙 Lancer le wizard','ocOnboard()')}
          ${_btn('🔧 Créer config Rotator','ocConfigureRotator()')}
        </div>`);
    }
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadConfig()')}`);
  }
}

async function ocSaveConfig() {
  const ta = document.getElementById('ocConfigEditor');
  const st = document.getElementById('ocConfigStatus');
  if (!ta) return;
  let cfg;
  try { cfg = JSON.parse(ta.value); } catch(e) {
    if (typeof showToast==='function') showToast('JSON invalide : '+e.message,'error');
    if (st) st.innerHTML = `<span style="color:var(--red)">JSON invalide</span>`;
    return;
  }
  if (st) st.textContent = '⏳ Sauvegarde…';
  try {
    const d = await _ocPost('/api/openclaw/config/save', { config: cfg });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Config sauvegardée !','success');
      _ocConfig = cfg;
      if (st) st.innerHTML = `<span style="color:var(--green)">✅ Sauvegardé</span>`;
      setTimeout(() => { if (st) st.textContent=''; }, 3000);
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
      if (st) st.innerHTML = `<span style="color:var(--red)">Erreur sauvegarde</span>`;
    }
  } catch(e) {
    if (typeof showToast==='function') showToast(e.message,'error');
    if (st) st.innerHTML = `<span style="color:var(--red)">${_esc(e.message)}</span>`;
  }
}

function ocFormatConfig() {
  const ta = document.getElementById('ocConfigEditor');
  if (!ta) return;
  try {
    ta.value = JSON.stringify(JSON.parse(ta.value), null, 2);
    if (typeof showToast==='function') showToast('Formaté !','success');
  } catch(e) { if (typeof showToast==='function') showToast('JSON invalide: '+e.message,'error'); }
}

function ocValidateConfig() {
  const ta = document.getElementById('ocConfigEditor');
  const st = document.getElementById('ocConfigStatus');
  if (!ta) return;
  try {
    JSON.parse(ta.value);
    if (typeof showToast==='function') showToast('JSON valide ✅','success');
    if (st) st.innerHTML = `<span style="color:var(--green)">✅ JSON valide</span>`;
    setTimeout(() => { if (st) st.textContent=''; }, 2500);
  } catch(e) {
    if (typeof showToast==='function') showToast('JSON invalide: '+e.message,'error');
    if (st) st.innerHTML = `<span style="color:var(--red)">❌ ${_esc(e.message)}</span>`;
  }
}

function ocDownloadConfig() {
  const ta = document.getElementById('ocConfigEditor');
  if (!ta) return;
  const blob = new Blob([ta.value], { type:'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'openclaw.json';
  a.click();
}

/* ═══════════════════════════════════════════════════════════════
   9. DOCTOR — Diagnostics streaming + Repair
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadDoctor() {
  const el = document.getElementById('ocDoctorContent');
  if (!el) return;
  el.innerHTML = `
    <div class="card">
      <div class="card-title">🩺 Diagnostics OpenClaw</div>
      <div style="font-size:12.5px;color:var(--text-dim);line-height:1.7;margin-top:6px">
        La commande <strong style="color:#fff">openclaw doctor</strong> effectue jusqu'à <strong style="color:#fff">19 vérifications</strong> :
        config normalization, state integrity, skills status, auth health, sandbox images, gateway service, security warnings, et plus.
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
        ${_btn('🩺 Lancer Doctor','ocRunDoctor()')}
        ${_btn('🔧 Doctor --repair','ocRunDoctorRepair()')}
        ${_btn('📋 Résumé rapide','ocDoctorQuick()')}
      </div>
    </div>
    <div id="ocDoctorOutput" style="margin-top:12px"></div>`;
}

async function ocRunDoctor() {
  const out = document.getElementById('ocDoctorOutput');
  if (out) out.innerHTML = `<div class="card">${_spinner()}</div>`;
  try {
    const d = await _ocPost('/api/openclaw/doctor');
    if (out) {
      const ok = d.ok && !d.errors;
      out.innerHTML = `
        <div class="card" style="border-color:${ok?'var(--green-bdr)':'var(--accent-bdr)'}">
          <div class="card-title">${ok ? '✅ Doctor : tout va bien' : '⚠️ Doctor : points à vérifier'}</div>
          ${d.output ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;max-height:500px;overflow:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;margin-top:10px;color:var(--text)">${_esc(d.output)}</pre>` : ''}
          ${d.errors ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;color:var(--red);background:var(--bg);border:1px solid var(--red-bdr);border-radius:var(--r);padding:12px;margin-top:8px">${_esc(d.errors)}</pre>` : ''}
        </div>`;
    }
  } catch(e) {
    if (out) out.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>`);
  }
}

async function ocRunDoctorRepair() {
  const out = document.getElementById('ocDoctorOutput');
  if (out) out.innerHTML = `<div class="card">${_dim('⏳ Repair en cours… (peut prendre 1-2 min)')}</div>`;
  try {
    const d = await _ocPost('/api/openclaw/cli', { args:['doctor','--repair'], timeout:120 });
    if (out) {
      out.innerHTML = `
        <div class="card">
          <div class="card-title">${d.ok ? '✅ Repair terminé' : '⚠️ Repair terminé avec des erreurs'}</div>
          ${d.stdout ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;max-height:500px;overflow:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;margin-top:10px;color:var(--text)">${_esc(d.stdout)}</pre>` : ''}
          ${d.stderr ? `<pre style="font-family:var(--font-mono);font-size:11px;white-space:pre-wrap;color:var(--red);background:var(--bg);border:1px solid var(--red-bdr);border-radius:var(--r);padding:12px;margin-top:8px">${_esc(d.stderr)}</pre>` : ''}
        </div>`;
    }
  } catch(e) {
    if (out) out.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>`);
  }
}

async function ocDoctorQuick() {
  const out = document.getElementById('ocDoctorOutput');
  if (out) out.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/status');
    if (out) {
      const checks = [
        ['Node.js 22+',        d.node_installed],
        ['OpenClaw CLI',       d.openclaw_installed],
        ['Config présente',    d.config_exists],
        ['Gateway actif',      d.gateway_running],
        ['Rotator configuré',  d.rotator_configured],
        ['Daemon installé',    d.daemon_enabled],
      ];
      out.innerHTML = _card('📋 Résumé rapide', `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px">
          ${checks.map(([label, ok]) => `
            <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--surface2);border-radius:6px">
              <span style="font-size:14px">${ok?'✅':'⚪'}</span>
              <span style="font-size:12px;color:${ok?'#fff':'var(--text-dim)'}">${label}</span>
            </div>`).join('')}
        </div>`);
    }
  } catch(e) {
    if (out) out.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>`);
  }
}

/* ═══════════════════════════════════════════════════════════════
   10. MEMORY — Fichiers mémoire (Markdown) + CRUD
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadMemory() {
  const el = document.getElementById('ocMemoryContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/memory/list');
    const files = d.files || [];
    _ocMemFiles = files;
    let h = '';

    /* ── Header ── */
    h += `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div>
        <div style="font-size:13.5px;font-weight:700;color:#fff">🧠 Fichiers mémoire</div>
        <div style="font-size:11.5px;color:var(--text-dim);margin-top:2px">
          ${_mono(d.base_path||'~/.openclaw/workspace')} · ${files.length} fichier${files.length!==1?'s':''}
        </div>
      </div>
      <div style="display:flex;gap:8px">
        ${_btn('➕ Nouveau','ocNewMemFile()')}
        ${_btn('🔃 Rafraîchir','ocLoadMemory()')}
      </div>
    </div>`;

    /* ── Search ── */
    h += `<div style="display:flex;gap:8px;margin-bottom:12px">
      <input id="ocMemSearch" placeholder="Rechercher dans les fichiers mémoire…"
        oninput="ocMemFilter(this.value)"
        style="flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:var(--r);padding:8px 12px;color:#fff;font-family:var(--font-ui)">
    </div>`;

    /* ── Files list ── */
    if (files.length) {
      h += `<div id="ocMemFileList">`;
      h += files.map(f => `
        <div class="oc-mem-item" data-path="${_esc(f.path)}" data-name="${_esc((f.name||f.path).toLowerCase())}"
          style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);margin-bottom:6px;cursor:pointer;transition:border-color .15s"
          onmouseover="this.style.borderColor='var(--border-hi)'"
          onmouseout="this.style.borderColor='var(--border)'"
          onclick="ocOpenMemFile('${_esc(f.path)}')">
          <span style="font-size:18px">📄</span>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(f.name||f.path)}</div>
            <div style="font-size:11px;color:var(--text-dim)">${f.size ? f.size + ' · ' : ''}${f.modified||''}</div>
          </div>
          <div style="display:flex;gap:6px" onclick="event.stopPropagation()">
            ${_btn('✏️',`ocOpenMemFile('${_esc(f.path)}')`)}
            ${_btnDanger('🗑',`ocDeleteMemFile('${_esc(f.path)}')`)}
          </div>
        </div>`).join('');
      h += `</div>`;
    } else {
      h += _empty('🧠', 'Aucun fichier mémoire trouvé.');
    }

    /* ── Editor panel (hidden) ── */
    h += `<div id="ocMemEditor" style="display:none;margin-top:16px">
      <div class="card" style="border-color:var(--accent-bdr)">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div class="card-title" id="ocMemEditorTitle">📄 Nouveau fichier</div>
          <button onclick="ocCloseMemEditor()">✕ Fermer</button>
        </div>
        <input id="ocMemFileName" placeholder="nom-du-fichier.md"
          style="width:100%;margin-bottom:8px;font-family:var(--font-mono)">
        <textarea id="ocMemFileContent"
          style="width:100%;min-height:380px;font-family:var(--font-mono);font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;color:#c5d4ec;resize:vertical;line-height:1.6"
          placeholder="# Mémoire&#10;&#10;Écrivez vos notes ici…"></textarea>
        <div style="display:flex;gap:8px;margin-top:10px">
          ${_btn('💾 Sauvegarder','ocSaveMemFile()')}
          ${_btn('Annuler','ocCloseMemEditor()')}
        </div>
      </div>
    </div>`;

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadMemory()')}`);
  }
}

function ocMemFilter(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('.oc-mem-item').forEach(item => {
    const name = item.dataset.name || '';
    item.style.display = name.includes(q) ? 'flex' : 'none';
  });
}

function ocNewMemFile() {
  const ed = document.getElementById('ocMemEditor');
  if (!ed) return;
  document.getElementById('ocMemEditorTitle').textContent = '📄 Nouveau fichier';
  document.getElementById('ocMemFileName').value = '';
  document.getElementById('ocMemFileContent').value = '';
  document.getElementById('ocMemFileName').dataset.originalPath = '';
  ed.style.display = 'block';
  ed.scrollIntoView({ behavior:'smooth', block:'center' });
  document.getElementById('ocMemFileName')?.focus();
}

async function ocOpenMemFile(path) {
  const ed = document.getElementById('ocMemEditor');
  if (!ed) return;
  try {
    const d = await _ocFetch(`/api/openclaw/memory/get?path=${encodeURIComponent(path)}`);
    document.getElementById('ocMemEditorTitle').textContent = '✏️ ' + (d.name||path);
    document.getElementById('ocMemFileName').value = d.name || path.split('/').pop() || '';
    document.getElementById('ocMemFileName').dataset.originalPath = path;
    document.getElementById('ocMemFileContent').value = d.content || '';
    ed.style.display = 'block';
    ed.scrollIntoView({ behavior:'smooth', block:'center' });
  } catch(e) {
    if (typeof showToast==='function') showToast('Erreur lecture: '+e.message,'error');
  }
}

async function ocSaveMemFile() {
  const name    = document.getElementById('ocMemFileName')?.value?.trim();
  const content = document.getElementById('ocMemFileContent')?.value || '';
  const origPath= document.getElementById('ocMemFileName')?.dataset?.originalPath;
  if (!name) { if (typeof showToast==='function') showToast('Nom de fichier requis','error'); return; }
  try {
    const d = await _ocPost('/api/openclaw/memory/save', { name, content, original_path: origPath || null });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Fichier mémoire sauvegardé !','success');
      ocCloseMemEditor();
      ocLoadMemory();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocDeleteMemFile(path) {
  if (!confirm(`Supprimer le fichier "${path.split('/').pop()}" ?`)) return;
  try {
    const d = await _ocPost('/api/openclaw/memory/delete', { path });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Fichier supprimé.','success');
      ocLoadMemory();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

function ocCloseMemEditor() {
  const ed = document.getElementById('ocMemEditor');
  if (ed) ed.style.display = 'none';
}

/* ═══════════════════════════════════════════════════════════════
   11. CHAT — Send messages to any session directly
   ═══════════════════════════════════════════════════════════════ */
let _ocChatSession = 'main';
let _ocChatMsgs    = [];

async function ocLoadChat() {
  const el = document.getElementById('ocChatContent');
  if (!el) return;

  /* ── Fetch available sessions ── */
  let sessOptions = `<option value="main">main (défaut)</option>`;
  try {
    const d = await _ocFetch('/api/openclaw/sessions/live');
    (d.sessions||[]).forEach(s => {
      const id = s.session_id||s.id||'';
      if (id && id !== 'main') {
        sessOptions += `<option value="${_esc(id)}">${_esc(id)} ${s.channel?'('+_esc(s.channel)+')':''}</option>`;
      }
    });
  } catch(e) {}

  el.innerHTML = `
    <div class="card" style="height:100%;display:flex;flex-direction:column">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-shrink:0">
        <div style="font-weight:700;color:#fff;flex:1">💬 Chat direct — Gateway OpenClaw</div>
        <select id="ocChatSessionSelect" onchange="ocChatSetSession(this.value)"
          style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--r-sm);padding:5px 10px;color:#fff;font-family:var(--font-ui);font-size:12px">
          ${sessOptions}
        </select>
        ${_btn('🗑 Vider','ocChatClear()')}
      </div>

      <div id="ocChatMessages" style="flex:1;min-height:300px;max-height:400px;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:12px;margin-bottom:10px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth">
        <div style="text-align:center;color:var(--text-dim);font-size:12px;padding:20px 0">
          Envoyez un message à la session Gateway OpenClaw.<br>
          <span style="font-size:11px">La réponse arrive via le channel configuré (WhatsApp, Telegram…)</span>
        </div>
      </div>

      <div style="display:flex;gap:8px;align-items:flex-end;flex-shrink:0">
        <textarea id="ocChatInput" placeholder="Écrivez votre message… (Entrée pour envoyer)"
          style="flex:1;min-height:64px;max-height:120px;font-family:var(--font-ui);font-size:13px;background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:10px;color:#fff;resize:vertical;line-height:1.5;transition:border-color .15s"
          onfocus="this.style.borderColor='var(--accent-bdr)'"
          onblur="this.style.borderColor='var(--border)'"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ocChatSend()}"
        ></textarea>
        <button onclick="ocChatSend()"
          style="padding:10px 18px;background:var(--accent);color:#000;font-weight:700;border:none;border-radius:var(--r);cursor:pointer;height:64px;font-size:13px;flex-shrink:0">
          ➤ Send
        </button>
      </div>
      <div style="font-size:10.5px;color:var(--text-muted);margin-top:6px">
        Session active : <span id="ocChatSessionLabel" style="color:var(--accent)">${_esc(_ocChatSession)}</span>
        · Shift+Enter pour saut de ligne
      </div>
    </div>`;

  _ocChatMsgs = [];
  ocChatRender();
}

function ocChatSetSession(id) {
  _ocChatSession = id || 'main';
  const lbl = document.getElementById('ocChatSessionLabel');
  if (lbl) lbl.textContent = _ocChatSession;
}

async function ocChatSend() {
  const inp = document.getElementById('ocChatInput');
  const text = inp?.value?.trim();
  if (!text) return;
  inp.value = '';

  /* Push user message */
  _ocChatMsgs.push({ role:'user', text, ts: new Date().toLocaleTimeString() });
  ocChatRender();

  /* Send to gateway */
  try {
    const d = await _ocPost('/api/openclaw/sessions/send', {
      session_id: _ocChatSession,
      message: text
    });
    if (d.ok) {
      const reply = d.response || d.message || '✅ Message envoyé au Gateway. La réponse sera livrée via le channel configuré.';
      _ocChatMsgs.push({ role:'agent', text: reply, ts: new Date().toLocaleTimeString() });
    } else {
      _ocChatMsgs.push({ role:'error', text: 'Erreur: '+(d.error||'envoi échoué'), ts: new Date().toLocaleTimeString() });
    }
  } catch(e) {
    _ocChatMsgs.push({ role:'error', text: e.message, ts: new Date().toLocaleTimeString() });
  }
  ocChatRender();
}

function ocChatClear() {
  _ocChatMsgs = [];
  ocChatRender();
}

function ocChatRender() {
  const box = document.getElementById('ocChatMessages');
  if (!box) return;
  if (!_ocChatMsgs.length) {
    box.innerHTML = `<div style="text-align:center;color:var(--text-dim);font-size:12px;padding:20px 0">Envoyez un message à la session Gateway OpenClaw.</div>`;
    return;
  }
  box.innerHTML = _ocChatMsgs.map(m => {
    const isUser  = m.role === 'user';
    const isError = m.role === 'error';
    const bg    = isUser ? 'var(--accent-dim)' : isError ? 'var(--red-dim)'  : 'var(--surface2)';
    const bdr   = isUser ? 'var(--accent-bdr)' : isError ? 'var(--red-bdr)' : 'var(--border)';
    const align = isUser ? 'flex-end' : 'flex-start';
    const maxW  = '80%';
    return `<div style="display:flex;justify-content:${align}">
      <div style="background:${bg};border:1px solid ${bdr};border-radius:var(--r);padding:10px 14px;max-width:${maxW}">
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">${isUser?'Vous':'Agent'} · ${_esc(m.ts)}</div>
        <div style="font-size:13px;color:${isError?'var(--red)':'#fff'};white-space:pre-wrap;word-break:break-word">${_esc(m.text)}</div>
      </div>
    </div>`;
  }).join('');
  box.scrollTop = box.scrollHeight;
}

/* ═══════════════════════════════════════════════════════════════
   12. HOOKS — Gmail, webhooks entrants/sortants
   ═══════════════════════════════════════════════════════════════ */
async function ocLoadHooks() {
  const el = document.getElementById('ocHooksContent');
  if (!el) return;
  el.innerHTML = _spinner();
  try {
    const d = await _ocFetch('/api/openclaw/hooks/config');
    const hooks = d.hooks || {};
    let h = '';

    /* ── Gmail ── */
    const gmail = hooks.gmail || {};
    h += _card('📧 Hook Gmail', `
      <div>Enabled : ${gmail.enabled ? '✅' : '❌'}</div>
      ${gmail.label ? `<div>Label : ${_mono(gmail.label)}</div>` : ''}
      ${gmail.session ? `<div>Session : ${_mono(gmail.session)}</div>` : ''}
      ${gmail.pollIntervalSec ? `<div>Poll interval : ${gmail.pollIntervalSec}s</div>` : ''}
      <div style="margin-top:8px">
        ${gmail.enabled
          ? _btnDanger('⏸ Désactiver Gmail hook', 'ocToggleHook(\'gmail\',false)')
          : _btn('▶ Activer Gmail hook', 'ocToggleHook(\'gmail\',true)')}
      </div>`);

    /* ── Webhooks entrants ── */
    const inbound = hooks.webhooks?.inbound || [];
    h += _card('📥 Webhooks entrants', `
      ${inbound.length ? `<div style="font-size:11.5px">
        ${inbound.map(w => `
          <div style="padding:8px 10px;background:var(--surface2);border-radius:6px;margin-bottom:6px">
            <div style="font-weight:600;color:#fff">${_mono(w.path||w.name||'—')}</div>
            ${w.secret ? `<div>Secret : ${_mono('***')}</div>` : ''}
            ${w.session ? `<div>→ Session : ${_mono(w.session)}</div>` : ''}
            ${w.template ? `<div>Template : ${_mono(w.template)}</div>` : ''}
          </div>`).join('')}
      </div>` : _dim('Aucun webhook entrant configuré.')}
      <div style="margin-top:10px">
        <div class="card-title" style="font-size:12px;margin-bottom:8px">➕ Ajouter un webhook entrant</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          ${_field('Path', _input('ocWebhookPath','/hooks/myapp'))}
          ${_field('Session cible', _input('ocWebhookSession','main'))}
          <div style="grid-column:1/-1">${_field('Template message', _input('ocWebhookTemplate','Nouveau webhook: {{body}}'))}</div>
          <div style="grid-column:1/-1">${_btn('➕ Ajouter', 'ocAddWebhook()')}</div>
        </div>
      </div>`, 12);

    /* ── Webhooks sortants ── */
    const outbound = hooks.webhooks?.outbound || [];
    h += _card('📤 Webhooks sortants', `
      ${outbound.length ? `<div style="font-size:11.5px">
        ${outbound.map(w => `
          <div style="padding:8px 10px;background:var(--surface2);border-radius:6px;margin-bottom:6px">
            <div style="font-weight:600;color:#fff">${_mono(w.url||'—')}</div>
            ${w.event ? `<div>Événement : ${_mono(w.event)}</div>` : ''}
            ${w.filter ? `<div>Filtre : ${_mono(w.filter)}</div>` : ''}
          </div>`).join('')}
      </div>` : _dim('Aucun webhook sortant configuré.')}`, 12);

    /* ── Mappings ── */
    const mappings = hooks.mappings || {};
    if (Object.keys(mappings).length) {
      h += _card('🔀 Mappings', `
        <div style="font-size:11.5px">
          ${Object.entries(mappings).map(([from,to]) =>
            `<div>${_mono(from)} → ${_mono(to)}</div>`
          ).join('')}
        </div>`, 12);
    }

    el.innerHTML = h;
  } catch(e) {
    el.innerHTML = _card('', `<div style="color:var(--red)">Erreur : ${_esc(e.message)}</div>
      ${_btn('🔃 Réessayer','ocLoadHooks()')}`);
  }
}

async function ocToggleHook(type, enable) {
  try {
    const d = await _ocPost('/api/openclaw/hooks/toggle', { type, enabled: enable });
    if (d.ok) {
      if (typeof showToast==='function') showToast(`Hook ${type} ${enable?'activé':'désactivé'}.`,'success');
      _ocInvalidateConfig();
      ocLoadHooks();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

async function ocAddWebhook() {
  const path    = document.getElementById('ocWebhookPath')?.value?.trim();
  const session = document.getElementById('ocWebhookSession')?.value?.trim() || 'main';
  const tpl     = document.getElementById('ocWebhookTemplate')?.value?.trim();
  if (!path) { if (typeof showToast==='function') showToast('Path requis','error'); return; }
  try {
    const d = await _ocPost('/api/openclaw/hooks/add-webhook', { path, session, template: tpl });
    if (d.ok) {
      if (typeof showToast==='function') showToast('Webhook ajouté !','success');
      _ocInvalidateConfig();
      ocLoadHooks();
    } else {
      if (typeof showToast==='function') showToast('Erreur: '+(d.error||''),'error');
    }
  } catch(e) { if (typeof showToast==='function') showToast(e.message,'error'); }
}

/* ═══════════════════════════════════════════════════════════════
   CSS INJECTION (styles spécifiques OpenClaw)
   ═══════════════════════════════════════════════════════════════ */
(function injectOCStyles() {
  if (document.getElementById('oc-styles')) return;
  const style = document.createElement('style');
  style.id = 'oc-styles';
  style.textContent = `
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .oc-section { animation: ocFadeIn .18s ease; }
    @keyframes ocFadeIn {
      from { opacity:0; transform:translateY(4px); }
      to   { opacity:1; transform:translateY(0); }
    }
    #ocChatMessages::-webkit-scrollbar { width:4px; }
    #ocChatMessages::-webkit-scrollbar-thumb { background:rgba(56,189,248,.15); border-radius:999px; }
    #ocMemFileList .oc-mem-item:hover { border-color:var(--border-hi) !important; background:var(--surface2); }
  `;
  document.head.appendChild(style);
})();