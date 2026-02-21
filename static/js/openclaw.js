  /* ─── OPENCLAW INTEGRATION ─── */

  function showOCTab(name) {
    document.querySelectorAll('.oc-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.oc-section').forEach(s => s.style.display = 'none');
    const tab = document.querySelector(`.oc-tab[onclick="showOCTab('${name}')"]`);
    if (tab) tab.classList.add('active');
    const sec = document.getElementById(`oc-${name}`);
    if (sec) sec.style.display = 'block';
    if (name === 'connect') ocLoadStatus();
    if (name === 'config') ocLoadConfig();
    if (name === 'channels') ocLoadChannels();
  }

  /* ─── Status check ─── */
  async function ocLoadStatus() {
    const el = document.getElementById('ocStatusContent');
    if (!el) return;
    el.innerHTML = '<div style="color:var(--text-dim)">Vérification…</div>';
    try {
      const r = await fetch('/api/openclaw/status');
      const d = await r.json();
      let html = '';

      // Node.js check
      html += `<div class="card" style="margin-bottom:12px">
        <div class="card-title">📦 Prérequis</div>
        <div style="font-size:12px; line-height:1.8">
          <div>Node.js : ${d.node_installed ? `<span style="color:var(--ok)">✅ ${d.node_version}</span>` : '<span style="color:var(--err)">❌ Non installé (Node 22+ requis)</span>'}</div>
          <div>OpenClaw : ${d.openclaw_installed ? `<span style="color:var(--ok)">✅ ${d.openclaw_version}</span>` : '<span style="color:var(--err)">❌ Non installé</span>'}</div>
        </div>
      </div>`;

      // Gateway status
      html += `<div class="card" style="margin-bottom:12px">
        <div class="card-title">🌐 Gateway</div>
        <div style="font-size:12px; line-height:1.8">
          <div>État : ${d.gateway_running ? '<span style="color:var(--ok)">✅ En cours (port ' + d.gateway_port + ')</span>' : '<span style="color:var(--text-dim)">⚪ Non démarré</span>'}</div>
          ${d.gateway_running && d.gateway_url ? `<div>URL : <a href="${d.gateway_url}" target="_blank" style="color:var(--accent)">${d.gateway_url}</a></div>` : ''}
        </div>
      </div>`;

      // Rotator provider status
      html += `<div class="card" style="margin-bottom:12px">
        <div class="card-title">🔗 Connexion Rotator</div>
        <div style="font-size:12px; line-height:1.8">
          <div>Provider rotator : ${d.rotator_configured ? '<span style="color:var(--ok)">✅ Configuré</span>' : '<span style="color:var(--text-dim)">⚪ Non configuré</span>'}</div>
        </div>
      </div>`;

      // Actions
      html += `<div class="card">
        <div class="card-title">⚡ Actions</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px">`;
      if (!d.openclaw_installed) {
        html += `<button onclick="ocInstall()" id="ocInstallBtn">📥 Installer OpenClaw</button>`;
      }
      if (d.openclaw_installed && !d.gateway_running) {
        html += `<button onclick="ocStartGateway()">▶ Démarrer le Gateway</button>`;
      }
      if (d.openclaw_installed && !d.rotator_configured) {
        html += `<button onclick="ocConfigureRotator()">🔧 Configurer Rotator comme provider</button>`;
      }
      if (d.gateway_running) {
        html += `<button onclick="ocStopGateway()">⏹ Arrêter le Gateway</button>`;
        if (d.gateway_url) html += `<button onclick="window.open('${d.gateway_url}','_blank')">🌐 Ouvrir le Control UI</button>`;
      }
      if (d.openclaw_installed) {
        html += `<button onclick="ocOnboard()">🧙 Lancer l'assistant de config</button>`;
      }
      html += `</div></div>`;

      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = `<div class="card"><div style="color:var(--err)">Erreur: ${e.message}</div></div>`;
    }
  }

  /* ─── Install OpenClaw ─── */
  async function ocInstall() {
    const btn = document.getElementById('ocInstallBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Installation…'; }
    try {
      const r = await fetch('/api/openclaw/install', { method: 'POST' });
      const d = await r.json();
      if (d.ok) {
        showToast('OpenClaw installé avec succès !', 'success');
      } else {
        showToast('Erreur: ' + (d.error || 'échec'), 'error');
      }
    } catch (e) {
      showToast('Erreur réseau: ' + e.message, 'error');
    }
    ocLoadStatus();
  }

  /* ─── Start/Stop Gateway ─── */
  async function ocStartGateway() {
    try {
      const r = await fetch('/api/openclaw/gateway/start', { method: 'POST' });
      const d = await r.json();
      showToast(d.ok ? 'Gateway démarré !' : ('Erreur: ' + (d.error || 'échec')), d.ok ? 'success' : 'error');
    } catch (e) { showToast('Erreur: ' + e.message, 'error'); }
    setTimeout(ocLoadStatus, 2000);
  }

  async function ocStopGateway() {
    try {
      const r = await fetch('/api/openclaw/gateway/stop', { method: 'POST' });
      const d = await r.json();
      showToast(d.ok ? 'Gateway arrêté.' : ('Erreur: ' + (d.error || 'échec')), d.ok ? 'success' : 'error');
    } catch (e) { showToast('Erreur: ' + e.message, 'error'); }
    setTimeout(ocLoadStatus, 1500);
  }

  /* ─── Configure Rotator as provider ─── */
  async function ocConfigureRotator() {
    try {
      const r = await fetch('/api/openclaw/configure-rotator', { method: 'POST' });
      const d = await r.json();
      if (d.ok) {
        showToast('Rotator configuré comme provider OpenClaw !', 'success');
        ocLoadStatus();
        ocLoadConfig();
      } else {
        showToast('Erreur: ' + (d.error || 'échec'), 'error');
      }
    } catch (e) { showToast('Erreur: ' + e.message, 'error'); }
  }

  /* ─── Onboard wizard ─── */
  async function ocOnboard() {
    try {
      const r = await fetch('/api/openclaw/onboard', { method: 'POST' });
      const d = await r.json();
      showToast(d.ok ? 'Assistant lancé dans un terminal séparé.' : ('Erreur: ' + (d.error || 'échec')), d.ok ? 'success' : 'error');
    } catch (e) { showToast('Erreur: ' + e.message, 'error'); }
  }

  /* ─── Config viewer ─── */
  async function ocLoadConfig() {
    const el = document.getElementById('ocConfigContent');
    if (!el) return;
    el.innerHTML = '<div style="color:var(--text-dim)">Chargement…</div>';
    try {
      const r = await fetch('/api/openclaw/config');
      const d = await r.json();
      if (d.ok && d.config) {
        el.innerHTML = `<div class="card">
          <div class="card-title">📄 ~/.openclaw/openclaw.json</div>
          <pre style="font-family:var(--font-mono); font-size:11px; max-height:500px; overflow:auto; background:var(--bg); border:1px solid var(--border); border-radius:var(--r); padding:12px; white-space:pre-wrap">${escapeHtml(JSON.stringify(d.config, null, 2))}</pre>
          <div style="margin-top:10px; display:flex; gap:8px">
            <button onclick="ocConfigureRotator()">🔧 Injecter Rotator comme provider</button>
          </div>
        </div>`;
      } else {
        el.innerHTML = `<div class="card">
          <div style="color:var(--text-dim)">Aucune config trouvée. Lancez <code>openclaw onboard</code> pour créer une configuration.</div>
          <div style="margin-top:10px"><button onclick="ocOnboard()">🧙 Lancer le wizard</button></div>
        </div>`;
      }
    } catch (e) {
      el.innerHTML = `<div class="card"><div style="color:var(--err)">Erreur: ${e.message}</div></div>`;
    }
  }

  /* ─── Channels viewer ─── */
  async function ocLoadChannels() {
    const el = document.getElementById('ocChannelsContent');
    if (!el) return;
    el.innerHTML = '<div style="color:var(--text-dim)">Chargement…</div>';
    try {
      const r = await fetch('/api/openclaw/status');
      const d = await r.json();
      let html = '<div class="card"><div class="card-title">📱 Channels configurés</div>';
      if (d.channels && d.channels.length > 0) {
        html += '<div style="margin-top:8px">';
        for (const ch of d.channels) {
          const icon = { whatsapp:'💬', telegram:'✈️', discord:'🎮', slack:'💼', imessage:'📱', signal:'🔒', mattermost:'💬', googlechat:'📧' }[ch] || '📡';
          html += `<div style="display:inline-block; background:var(--bg); border:1px solid var(--border); border-radius:var(--r); padding:6px 12px; margin:4px; font-size:12px">${icon} ${ch}</div>`;
        }
        html += '</div>';
      } else {
        html += '<div style="color:var(--text-dim); font-size:12px; margin-top:8px">Aucun channel configuré. Utilisez <code>openclaw configure --section channels</code> pour en ajouter.</div>';
      }
      html += `<div style="margin-top:12px; font-size:11px; color:var(--text-dim)">
        <strong>Channels supportés :</strong> WhatsApp, Telegram, Discord, Slack, iMessage, Signal, Mattermost, Google Chat
      </div></div>`;

      // Quick setup guide
      html += `<div class="card" style="margin-top:12px">
        <div class="card-title">📖 Configuration rapide</div>
        <div style="font-size:11.5px; color:var(--text-dim); line-height:1.7; margin-top:8px">
          <strong style="color:#fff">WhatsApp</strong> : <code>openclaw channels login</code> → scanner le QR code<br>
          <strong style="color:#fff">Telegram</strong> : Créer un bot via @BotFather, ajouter <code>botToken</code> dans la config<br>
          <strong style="color:#fff">Discord</strong> : Créer une app + bot sur discord.com/developers, ajouter le <code>token</code><br>
          <strong style="color:#fff">Slack</strong> : Créer une app Slack avec Socket Mode, ajouter <code>botToken</code> + <code>appToken</code>
        </div>
      </div>`;
      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = `<div class="card"><div style="color:var(--err)">Erreur: ${e.message}</div></div>`;
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
