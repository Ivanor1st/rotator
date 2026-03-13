/* ─── I18N (Internationalization) ─── */
const i18n = {
  current: 'fr',
  translations: {
    fr: {
      loading: 'Chargement...',
      error: 'Erreur',
      retry: 'Réessayer',
      copied: 'Copié!',
      copyFailed: 'Erreur de copie',
      save: 'Enregistrer',
      cancel: 'Annuler',
      delete: 'Supprimer',
      edit: 'Modifier',
      close: 'Fermer',
      confirm: 'Confirmer',
      yes: 'Oui',
      no: 'Non',
      apiKeyLabel: 'Clé API',
      baseUrlLabel: 'Base URL',
      modelsLabel: 'Modèles disponibles',
      showKey: 'Afficher la clé API',
      hideKey: 'Masquer la clé API',
      copyKey: 'Copier la clé API',
    },
    en: {
      loading: 'Loading...',
      error: 'Error',
      retry: 'Retry',
      copied: 'Copied!',
      copyFailed: 'Copy failed',
      save: 'Save',
      cancel: 'Cancel',
      delete: 'Delete',
      edit: 'Edit',
      close: 'Close',
      confirm: 'Confirm',
      yes: 'Yes',
      no: 'No',
      apiKeyLabel: 'API Key',
      baseUrlLabel: 'Base URL',
      modelsLabel: 'Available Models',
      showKey: 'Show API Key',
      hideKey: 'Hide API Key',
      copyKey: 'Copy API Key',
    }
  },
  t(key) {
    return this.translations[this.current]?.[key] || this.translations['fr'][key] || key;
  },
  setLang(lang) {
    if (this.translations[lang]) {
      this.current = lang;
      document.documentElement.lang = lang;
      // Update language buttons
      document.getElementById('langFr')?.setAttribute('aria-pressed', lang === 'fr');
      document.getElementById('langEn')?.setAttribute('aria-pressed', lang === 'en');
      this.updateUI();
    }
  },
  detectLang() {
    const browserLang = navigator.language?.split('-')[0];
    if (this.translations[browserLang]) {
      this.setLang(browserLang);
    }
  },
  updateUI() {
    // Update elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      el.textContent = this.t(key);
    });
    // Update placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = this.t(key);
    });
  }
};

// Auto-detect language on load
i18n.detectLang();

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

// API Key visibility toggle (for security)
let apiKeyVisible = false;
function toggleApiKeyVisibility(button) {
  const displayEl = document.getElementById('onboardApiKey');
  const hiddenEl = document.getElementById('onboardApiKeyValue');
  if (!displayEl || !hiddenEl) return;

  apiKeyVisible = !apiKeyVisible;
  if (apiKeyVisible) {
    displayEl.textContent = hiddenEl.value;
    displayEl.style.fontFamily = 'var(--font-mono)';
    button.textContent = '🔒';
    button.setAttribute('aria-label', 'Masquer la clé API');
  } else {
    displayEl.textContent = '••••••••';
    displayEl.style.fontFamily = '';
    button.textContent = '👁️';
    button.setAttribute('aria-label', 'Afficher la clé API');
  }
}

async function copyApiKey(button) {
  const hiddenEl = document.getElementById('onboardApiKeyValue');
  if (!hiddenEl) return;
  await copyText(hiddenEl.value, button);
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
  // For Ollama tab, show confirmation first
  if (catTab === 'ollama') {
    const confirmed = confirm(
      'Cette opération va mettre à jour la liste des modèles depuis Ollama.\n\n' +
      'Cela peut prendre jusqu\'à 3 minutes selon votre connexion.\n' +
      'Pendant ce temps, le catalogue sera indisponible.\n\n' +
      'Voulez-vous continuer ?'
    );
    if (!confirmed) return;

    // Use the new Ollama-specific scrape endpoint
    btn.disabled = true;
    btn.innerText = '⏳ Rafraîchissement...';
    const st = document.getElementById('catalogueRefreshStatus');
    st.innerText = 'Lancement du rafraîchissement Ollama...';

    try {
      const res = await api('/api/catalogue/ollama/scrape', 'POST');
      if (res.ok) {
        // Show progress
        showOllamaScrapeProgress(res.progress || { status: 'running', current_model: 'Démarrage...' });
      } else {
        st.innerText = '❌ Erreur: ' + (res.error || 'Erreur inconnue');
      }
    } catch (err) {
      st.innerText = '❌ Erreur: ' + err.message;
    }

    btn.disabled = false;
    btn.innerText = '↺ Rafraîchir tous les catalogues';
    return;
  }

  // For other tabs, use the existing refresh
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
  // Check if this is the new grouped structure (Ollama)
  const isGrouped = m.variants && m.variants.length > 0;

  // For grouped models (Ollama), extract info from group level
  const modelName = m.name;
  const description = m.description || '';
  const paramsSummary = m.params_summary || '';
  const visionSupport = m.vision_support || '';
  const agenticRl = m.agentic_rl || '';
  const modifiedAt = m.modified_at || '';
  const variants = m.variants || [];

  // Get info from first variant for display
  const firstVariant = variants.length > 0 ? variants[0] : {};
  const isInstalled = firstVariant.installed || m.installed || false;
  const modelSize = firstVariant.size || m.size || 0;

  const sizeLabel = modelSize ? formatBytes(modelSize) : m.parameter_size || '—';
  const paramSize = paramsSummary || m.parameter_size || (m.details || {}).parameter_size || '';
  const family = (m.details || {}).family || '';
  const quant = (m.details || {}).quantization_level || '';

  // Availability badge - use new grouped structure for Ollama
  let availabilityBadge = '';
  if (source === 'ollama' || source === 'ollama-library') {
    // Check if model is cloud or local based on name
    const isCloudVariant = m.name.includes('-cloud');
    const isInstalled = m.installed || false;
    if (isCloudVariant) {
      availabilityBadge = '<span class="badge amber" style="font-size:10px; flex-shrink:0">☁️ Cloud</span>';
    } else if (isInstalled) {
      availabilityBadge = '<span class="badge green" style="font-size:10px; flex-shrink:0">💾 Local</span>';
    } else {
      availabilityBadge = '<span class="badge" style="font-size:10px; flex-shrink:0">⬇ Disponible</span>';
    }
  } else if (source === 'local') {
    availabilityBadge = '<span class="badge green" style="font-size:10px; flex-shrink:0">💾 Local</span>';
  } else if ((m.tags || []).includes('cloud') || source === 'openrouter' || source === 'nvidia') {
    availabilityBadge = '<span class="badge amber" style="font-size:10px; flex-shrink:0">☁️ Cloud</span>';
  } else if (isInstalled) {
    availabilityBadge = '<span class="badge green" style="font-size:10px; flex-shrink:0">✅ Installé</span>';
  } else {
    availabilityBadge = '<span class="badge" style="font-size:10px; flex-shrink:0">⬇ Disponible</span>';
  }

  const tagBadges = (m.tags || []).slice(0, 4).map(t => {
    const colors = { cloud: 'amber', vision: 'blue', tools: 'green', thinking: 'purple', code: 'green' };
    const c = colors[t] || '';
    return `<span class="badge ${c}" style="font-size:10px">${t}</span>`;
  }).join('');

  // Enriched capability badges
  const capBadges = [
    visionSupport && visionSupport !== 'non' ? `<span class="badge blue" style="font-size:10px">👁 Vision</span>` : '',
    agenticRl && agenticRl !== 'non' ? `<span class="badge purple" style="font-size:10px">🤖 Agentic</span>` : '',
  ].filter(Boolean).join('');

  // Downloads and updated - from first variant or model
  const downloads = firstVariant.downloads || m.downloads || 0;
  const downloadsBadge = downloads ? `<span class="badge" style="font-size:10px">⬇ ${downloads >= 1e6 ? (downloads / 1e6).toFixed(0) + 'M' : downloads >= 1e3 ? (downloads / 1e3).toFixed(0) + 'K' : downloads}</span>` : '';
  const updatedBadge = modifiedAt ? `<span class="badge" style="font-size:10px">📅 ${formatUpdated(modifiedAt)}</span>` : '';

  // Show variant count for grouped models
  const variantCount = variants.length > 1 ? `<span class="badge" style="font-size:10px">📦 ${variants.length} variants</span>` : '';

  const extraBadges = [
    paramSize ? `<span class="badge" style="font-size:10px">🧠 ${paramSize}</span>` : '',
    family ? `<span class="badge" style="font-size:10px">🏷 ${family}</span>` : '',
    quant ? `<span class="badge purple" style="font-size:10px">⚙ ${quant}</span>` : '',
  ].filter(Boolean).join('');

  // NO buttons on small card - user clicks to see modal
  const cardData = encodeURIComponent(JSON.stringify(m));

  // Params summary subtitle
  const paramsSub = paramsSummary ? `<div style="font-size:11px; color:var(--accent); margin-bottom:6px; font-family:var(--font-mono)">${paramsSummary}</div>` : '';
  // Top benchmark mini-line
  const benchLine = m.top_benchmark ? `<div style="font-size:10px; color:var(--text-muted); margin-bottom:8px">🏆 ${m.top_benchmark}</div>` : '';

  return `
      <div id="modelcard-${modelName.replace(/[^a-z0-9]/gi, '-')}" onclick="showModelDetail(decodeURIComponent('${cardData}'), '${source}')" style="
        background:var(--surface); border:1px solid var(--border);
        border-radius:var(--r-lg); padding:16px; cursor:pointer;
        ${isInstalled ? 'border-color:var(--green-bdr);' : ''}
        transition: border-color .2s, transform .15s, box-shadow .15s;
        display: flex; flex-direction: column;
      " onmouseover="this.style.borderColor='var(--border-hi)'; this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,.3)'"
         onmouseout="this.style.borderColor='${isInstalled ? 'var(--green-bdr)' : 'var(--border)'}'; this.style.transform='none'; this.style.boxShadow='none'">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px">
          <div style="font-family:var(--font-mono); font-size:13px; font-weight:600; color:#fff; flex:1; margin-right:8px">${modelName}</div>
          ${availabilityBadge}
        </div>
        ${paramsSub}
        <div style="font-size:12px; color:var(--text-dim); margin-bottom:8px; line-height:1.4">
          ${description.slice(0, 100)}${description.length > 100 ? '...' : ''}
        </div>
        <div style="display:flex; gap:5px; flex-wrap:wrap; margin-bottom:6px">
          ${capBadges}
          ${tagBadges}
          ${variantCount}
          ${sizeLabel && sizeLabel !== '—' ? `<span class="badge" style="font-size:10px">📦 ${sizeLabel}</span>` : ''}
          ${extraBadges}
        </div>
        <div style="display:flex; gap:5px; flex-wrap:wrap; margin-bottom:6px">
          ${downloadsBadge}
          ${updatedBadge}
        </div>
        ${benchLine}
      </div>`;
}

function showModelDetail(jsonStr, source) {
  const m = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr;

  // Check if this is the new grouped structure (Ollama with variants)
  const variants = m.variants || [];
  const isGrouped = variants.length > 0;

  // For grouped models, get info from group level
  const modelName = m.name;
  const description = m.description || '';
  const paramsSummary = m.params_summary || '';
  const visionSupport = m.vision_support || '';
  const agenticRl = m.agentic_rl || '';
  const topBenchmark = m.top_benchmark || '';
  const modifiedAt = m.modified_at || '';

  // Get info from first variant for single-model display
  const firstVariant = isGrouped ? variants[0] : {};
  const isInstalled = firstVariant.installed || m.installed || false;
  const modelSize = firstVariant.size || m.size || 0;
  const details = m.details || {};

  // Check if model is in DB or installed locally (for Ollama catalogue)
  let dbModels = [];
  let installedModels = [];

  // Only for Ollama source, check status
  if (source === 'ollama' || source === 'ollama-library') {
    // Get models in DB
    dbModels = window.myCatalogueModels || [];
    // Get locally installed
    api('/api/catalogue/ollama/installed').then(data => {
      window.ollamaInstalledModels = data.installed || [];
      // Re-render if we're in the detail view
      if (document.getElementById('modelDetailModal')?.classList.contains('active')) {
        // Just refresh the button states
      }
    }).catch(() => {});
  }

  // Determine if cloud or local variant
  // Use is_cloud field from the data, fallback to checking variant name
  // Cloud: is_cloud = true OR variant ends with "cloud" or contains "-cloud"
  // Local: is_cloud = false AND (has size OR no explicit cloud marker)
  const isCloudVariant = (v) => {
    if (v.is_cloud !== undefined) return v.is_cloud;
    const variant = v.variant || '';
    return variant === 'cloud' || variant.includes('-cloud');
  };
  const isLocalVariant = (v) => {
    const variant = v.variant || '';
    // If it's cloud, it's not local
    if (isCloudVariant(v)) return false;
    // If it has a size, it's local
    if (v.size && v.size > 0) return true;
    // If it has no explicit cloud marker and no size, treat as local (to be downloaded)
    return !variant.includes('-cloud') && variant !== 'cloud';
  };

  document.getElementById('modelDetailTitle').innerText = modelName;

  // If grouped with variants, show variant table
  if (isGrouped && (source === 'ollama' || source === 'ollama-library')) {
    // Build variant table rows
    const variantRows = variants.map(v => {
      const vName = v.name || `${modelName}:${v.variant}`;
      const vSize = v.size ? formatBytes(v.size) : '—';
      const vContext = v.context_length ? formatContext(v.context_length) : '—';
      const vCloud = isCloudVariant(v);
      const vLocal = isLocalVariant(v);

      // Check if installed/in DB using the arrays
      const installedList = window.ollamaInstalledModels || [];
      const isLocallyInstalled = installedList.includes(vName);
      const dbList = window.myCatalogueModels || [];
      const isInCatalogue = dbList.some(m => m.name === vName);

      // Determine action button based on actual status
      let actionBtn = '';
      if (vCloud) {
        // Cloud variant - check if in catalogue
        if (isInCatalogue) {
          actionBtn = `<button class="secondary" style="font-size:11px; padding:4px 8px; cursor:default">✅ Present</button>`;
        } else {
          actionBtn = `<button class="primary" onclick="closeModelDetail(); addToMyCatalogue(${JSON.stringify(v).replace(/"/g, '&quot;')}, this)" style="font-size:11px; padding:4px 8px">➕ Ajouter</button>`;
        }
      } else if (vLocal || v.size) {
        // Local variant - check if installed
        if (isLocallyInstalled) {
          actionBtn = `<button class="secondary" style="font-size:11px; padding:4px 8px; cursor:default">✅ Present</button>`;
        } else {
          actionBtn = `<button class="primary" onclick="closeModelDetail(); confirmInstallModel('${vName}', ${v.size || 0})" style="font-size:11px; padding:4px 8px">⬇ Télécharger</button>`;
        }
      }

      // Determine badge
      let badge = '';
      if (vCloud) {
        badge = '<span class="badge amber" style="font-size:9px">☁️ Cloud</span>';
      } else if (isLocallyInstalled) {
        badge = '<span class="badge green" style="font-size:9px">💾 Installé</span>';
      } else if (v.size) {
        badge = '<span class="badge" style="font-size:9px">💾 Local</span>';
      }

      return `
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:10px 8px; font-family:var(--font-mono); font-size:12px">${v.variant} ${badge}</td>
          <td style="padding:10px 8px; font-size:12px">${vSize}</td>
          <td style="padding:10px 8px; font-size:12px">${vContext}</td>
          <td style="padding:10px 8px; font-size:12px">Text${visionSupport && visionSupport !== 'non' ? ', Image' : ''}</td>
          <td style="padding:10px 8px; text-align:right">${actionBtn}</td>
        </tr>
      `;
    }).join('');

    // Group-level info
    const infoRows = [
      { label: 'Description', value: description || '—' },
      { label: 'Paramètres', value: paramsSummary || '—' },
      { label: '👁 Vision', value: visionSupport && visionSupport !== 'non' ? visionSupport : '—' },
      { label: '🤖 Agentic', value: agenticRl && agenticRl !== 'non' ? agenticRl : '—' },
      { label: '🏆 Benchmark', value: topBenchmark || '—' },
      { label: 'Mis à jour', value: modifiedAt ? formatUpdated(modifiedAt) : '—' },
    ].filter(r => r.value !== '—');

    const capBadges = [
      visionSupport && visionSupport !== 'non' ? `<span class="badge blue" style="font-size:11px">👁 Vision</span>` : '',
      agenticRl && agenticRl !== 'non' ? `<span class="badge purple" style="font-size:11px">🤖 Agentic</span>` : '',
    ].filter(Boolean).join(' ');

    // Action buttons
    const modelBase = modelName.split(':')[0];
    const ollamaLink = `<a href="https://ollama.com/library/${modelBase}" target="_blank" style="font-size:12px; padding:8px 16px; text-decoration:none; color:var(--accent)">🔗 Voir sur Ollama</a>`;

    document.getElementById('modelDetailBody').innerHTML = `
      <div style="margin-bottom:16px">
        ${capBadges ? `<div style="display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px">${capBadges}</div>` : ''}
        <table style="width:100%; font-size:12px; border-collapse:collapse; margin-bottom:16px">
          ${infoRows.map(r => `
            <tr style="border-bottom:1px solid var(--border)">
              <td style="padding:8px 12px 8px 0; color:var(--text-muted); font-weight:600; white-space:nowrap; width:130px">${r.label}</td>
              <td style="padding:8px 0; color:var(--text); font-family:var(--font-mono); word-break:break-all">${r.value}</td>
            </tr>
          `).join('')}
        </table>

        <div style="font-size:13px; font-weight:600; margin-bottom:10px; color:var(--text)">Variantes (${variants.length})</div>
        <table style="width:100%; font-size:12px; border-collapse:collapse; background:var(--surface); border-radius:8px; overflow:hidden">
          <thead>
            <tr style="background:var(--bg-dim)">
              <th style="padding:10px 8px; text-align:left; font-size:11px; color:var(--text-muted)">Variante</th>
              <th style="padding:10px 8px; text-align:left; font-size:11px; color:var(--text-muted)">Taille</th>
              <th style="padding:10px 8px; text-align:left; font-size:11px; color:var(--text-muted)">Contexte</th>
              <th style="padding:10px 8px; text-align:left; font-size:11px; color:var(--text-muted)">Input</th>
              <th style="padding:10px 8px; text-align:right; font-size:11px; color:var(--text-muted)">Action</th>
            </tr>
          </thead>
          <tbody>
            ${variantRows}
          </tbody>
        </table>
      </div>
      <div style="display:flex; gap:8px; justify-content:flex-end; align-items:center; padding-top:8px; border-top:1px solid var(--border)">
        ${ollamaLink}
        <button onclick="closeModelDetail()">Fermer</button>
      </div>
    `;
  } else {
    // Original single model display
    const sizeLabel = modelSize ? formatBytes(modelSize) : m.parameter_size || '—';
    const isCloud = (m.tags || []).includes('cloud') || source === 'openrouter' || source === 'nvidia';

    const infoRows = [
      { label: 'Nom', value: modelName },
      { label: 'Description', value: description || '—' },
      { label: 'Architecture', value: paramsSummary || '—' },
      { label: 'Taille', value: sizeLabel },
      { label: 'Paramètres', value: m.parameter_size || details.parameter_size || '—' },
      { label: 'Famille', value: details.family || '—' },
      { label: 'Quantization', value: details.quantization_level || '—' },
      { label: 'Format', value: details.format || '—' },
      { label: 'Contexte', value: m.context_length ? formatContext(m.context_length) : '—' },
      { label: '👁 Vision', value: visionSupport && visionSupport !== 'non' ? visionSupport : '—' },
      { label: '🤖 Agentic RL', value: agenticRl && agenticRl !== 'non' ? agenticRl : '—' },
      { label: '🏆 Benchmark', value: topBenchmark || '—' },
      { label: 'Téléchargements', value: (firstVariant.downloads || m.downloads) ? (firstVariant.downloads || m.downloads).toLocaleString() : '—' },
      { label: 'Source', value: source },
      { label: 'Statut', value: isInstalled ? '✅ Installé localement' : isCloud ? '☁️ Cloud' : '⬇ Disponible au téléchargement' },
    ].filter(r => r.value !== '—');

    const tagBadges = (m.tags || []).map(t => {
      const colors = { cloud: 'amber', vision: 'blue', tools: 'green', thinking: 'purple', code: 'green' };
      const c = colors[t] || '';
      return `<span class="badge ${c}" style="font-size:11px">${t}</span>`;
    }).join(' ');

    const actionBtn = source === 'local'
      ? `<button class="danger" onclick="closeModelDetail(); deleteLocalModel('${modelName}')" style="font-size:12px; padding:8px 16px">🗑 Supprimer</button>`
      : source === 'my-catalogue'
        ? `<button class="danger" onclick="closeModelDetail(); removeFromMyCatalogue('${modelName}')" style="font-size:12px; padding:8px 16px">🗑 Retirer du catalogue</button>`
        : isCloud
          ? `<button class="primary" onclick="closeModelDetail(); addToRotator('${modelName}','${source}')" style="font-size:12px; padding:8px 16px">➕ Ajouter au catalogue</button>`
          : isInstalled
            ? `<button onclick="closeModelDetail(); addToRotator('${modelName}','local')" style="font-size:12px; padding:8px 16px">➕ Ajouter au rotator</button>`
            : `<button class="primary" onclick="closeModelDetail(); confirmInstallModel('${modelName}', ${modelSize || 0})" style="font-size:12px; padding:8px 16px">⬇ Télécharger & Installer</button>`;

    const modelBase = modelName.split(':')[0];
    const ollamaLink = (source === 'ollama' || source === 'local' || source === 'my-catalogue') ? `<a href="https://ollama.com/library/${modelBase}" target="_blank" style="font-size:12px; padding:8px 16px; text-decoration:none; color:var(--accent)">🔗 Voir sur Ollama</a>` : '';

    const addBtn = (source === 'ollama' || source === 'local' || source === 'ollama-library') ? `<button class="secondary" onclick="addToMyCatalogue(${JSON.stringify(m).replace(/"/g, '&quot;')}, this)" style="font-size:12px; padding:8px 16px">✨ Ajouter à Mon Catalogue</button>` : '';

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
      <div style="display:flex; gap:8px; justify-content:flex-end; align-items:center; padding-top:8px; border-top:1px solid var(--border)">
        ${ollamaLink}
        ${addBtn}
        <button onclick="closeModelDetail()">Fermer</button>
        ${actionBtn}
      </div>
    `;
  }

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

function formatUpdated(dateStr) {
  // The date is already in human-readable format like "2 years ago"
  return dateStr || '—';
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

  // If already polling, stop it
  if (window.ollamaProgressInterval) {
    clearInterval(window.ollamaProgressInterval);
    window.ollamaProgressInterval = null;
  }

  try {
    // Load Ollama models and check installed/DB status in parallel
    const [data, installedData, myModelsData] = await Promise.all([
      api('/api/catalogue/ollama'),
      api('/api/catalogue/ollama/installed').catch(() => ({ installed: [] })),
      api('/api/catalogue/my-models').catch(() => ({ models: [] }))
    ]);

    // Store globally for variant buttons
    window.ollamaInstalledModels = installedData.installed || [];
    window.myCatalogueModels = myModelsData.models || [];

    console.log('loadOllamaModels response:', data);

    // If we have models, display them
    if (data.models && data.models.length > 0) {
      ollamaModelsCache = data.models;
      filterOllamaModels();
      const refreshDate = data.last_refresh || data.updated_at;
      if (refreshDate) showCatalogueTimestamp('ollama', refreshDate);
      return;
    }

    // If scraping in progress, show progress
    if (data.status === 'scraping' || data.status === 'running') {
      showOllamaScrapeProgress(data.progress);
      return;
    }

    // No models - trigger scrape
    console.log('No models, triggering scrape...');
    await api('/api/catalogue/ollama/scrape', 'POST');
    showOllamaScrapeProgress({ status: 'running', current_model: 'Démarrage...', total_models: 0, scraped_count: 0 });

  } catch (err) {
    console.error('loadOllamaModels error:', err);
    document.getElementById('ollamaLoading').innerText = '❌ Impossible de charger le catalogue. Vérifiez votre connexion.';
  }
}

function showOllamaScrapeProgress(progress) {
  const loadingEl = document.getElementById('ollamaLoading');
  const gridEl = document.getElementById('ollamaModelGrid');

  // Show initial message
  loadingEl.innerHTML = `
    <div style="text-align:center; padding: 20px;">
      <div style="font-size: 18px; margin-bottom: 10px;">🚀 Premier lancement : génération du catalogue...</div>
      <div style="color: var(--text-dim); font-size: 14px;" id="ollamaProgressMsg">Initialisation...</div>
    </div>
  `;
  loadingEl.style.display = 'block';
  gridEl.innerHTML = '';

  // Poll for progress updates
  window.ollamaProgressInterval = setInterval(async () => {
    try {
      const progressData = await api('/api/catalogue/ollama/progress');
      const p = progressData;

      if (p.status === 'completed') {
        // Scraping done, reload models
        clearInterval(window.ollamaProgressInterval);
        window.ollamaProgressInterval = null;

        loadingEl.innerHTML = '<div style="text-align:center; padding: 20px;"><div style="font-size: 18px;">✅ Catalogue généré ! Chargement...</div></div>';

        // Reload models
        try {
          const data = await api('/api/catalogue/ollama');
          console.log('Ollama data received:', data);
          if (data.models && data.models.length > 0) {
            ollamaModelsCache = data.models;
            filterOllamaModels();
            if (data.last_refresh) showCatalogueTimestamp('ollama', data.last_refresh);
          } else {
            // No models returned, show error
            console.log('No models in response:', data);
            loadingEl.innerText = '❌ Erreur: Aucun modèle retourné. Vérifiez le cache.';
          }
        } catch (err) {
          console.error('Error loading models:', err);
          loadingEl.innerText = '❌ Erreur lors du chargement: ' + err.message;
        }
        return;
      }

      if (p.status === 'error') {
        clearInterval(window.ollamaProgressInterval);
        window.ollamaProgressInterval = null;
        loadingEl.innerText = '❌ Erreur lors du scraping: ' + (p.error || 'Erreur inconnue');
        return;
      }

      // Show progress
      const progressMsg = document.getElementById('ollamaProgressMsg');
      if (progressMsg) {
        const total = p.total_models || 0;
        const current = p.scraped_count || 0;
        const percent = total > 0 ? Math.round((current / total) * 100) : 0;

        progressMsg.innerHTML = `
          <div>${p.current_model || 'Chargement...'}</div>
          <div style="margin-top: 10px;">
            <div style="background: var(--bg-dim); height: 8px; border-radius: 4px; overflow: hidden; max-width: 300px; margin: 0 auto;">
              <div style="background: var(--accent); height: 100%; width: ${percent}%; transition: width 0.3s;"></div>
            </div>
            <div style="margin-top: 5px;">${current} / ${total} modèles (${percent}%)</div>
          </div>
          <div style="margin-top: 10px; font-size: 12px; color: var(--text-dim);">Veuillez ne pas rafraîchir la page</div>
        `;
      }

    } catch (err) {
      console.error('Error polling progress:', err);
    }
  }, 2000); // Poll every 2 seconds
}

// Parse modified_at for sorting - convert to "months ago" (smaller = more recent)
function parseDateModified(str) {
  if (!str || str === 'unknown') return 999; // unknown at end
  const num = parseInt(str);

  if (str.includes('year')) return num * 12; // 2 years = 24 months
  if (str.includes('month')) return num; // months
  if (str.includes('week') || str.includes('day')) return 0; // recent
  return 999;
}

// Parse downloads for sorting ("109.6K" -> 109600)
function parseDownloads(str) {
  if (!str) return 0;
  if (str.includes('M')) return parseFloat(str) * 1e6;
  if (str.includes('K')) return parseFloat(str) * 1e3;
  return parseInt(str) || 0;
}

// Fuzzy match - tolerates typos
function fuzzyMatch(text, query) {
  if (!text || !query) return { match: false, score: 0 };
  const t = text.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return { match: true, score: 1 };
  if (t.includes(q)) return { match: true, score: 1 };

  // Fuzzy: tolère jusqu'à 2 caractères manquants/incorrects
  let misses = 0;
  let qIndex = 0;
  for (let i = 0; i < t.length && qIndex < q.length; i++) {
    if (t[i] === q[qIndex]) {
      qIndex++;
    } else {
      misses++;
    }
  }
  return { match: qIndex === q.length && misses <= 2, score: 1 - (misses / q.length) };
}

// Search across name, description, and tags
function searchModels(models, query) {
  if (!query || !query.trim()) return models;
  const q = query.toLowerCase().trim();
  return models.filter(m => {
    if (fuzzyMatch(m.name, q).match) return true;
    if (fuzzyMatch(m.description || '', q).match) return true;
    if ((m.tags || []).some(t => fuzzyMatch(t, q).match)) return true;
    return false;
  });
}

function filterOllamaModels() {
  const q = document.getElementById('ollamaSearch').value;
  const sortBy = document.getElementById('ollamaSort').value;
  const type = document.getElementById('ollamaFilterType').value;
  const size = document.getElementById('ollamaFilterSize').value;

  // Step 1: Recherche puissante (fuzzy, multi-champs)
  let filtered = searchModels(ollamaModelsCache, q);

  // Step 2: Filtres existants (type et size)
  filtered = filtered.filter(m => {
    const firstVariant = (m.variants && m.variants[0]) || {};
    const modelSize = firstVariant.size || m.size || 0;

    // Type filter
    if (type) {
      const isCloud = firstVariant.is_cloud || m.is_cloud;
      const hasVision = (m.vision_support || '').toLowerCase() === 'oui';
      const hasTools = (m.tags || []).includes('tools');
      const hasThinking = (m.tags || []).includes('thinking');

      if (type === 'cloud' && !isCloud) return false;
      if (type === 'local' && isCloud) return false;
      if (type === 'vision' && !hasVision) return false;
      if (type === 'tools' && !hasTools) return false;
      if (type === 'thinking' && !hasThinking) return false;
    }

    // Size filter
    if (size) {
      const gb = modelSize / 1e9;
      if (size === 'tiny' && gb >= 2) return false;
      if (size === 'small' && (gb < 2 || gb >= 8)) return false;
      if (size === 'medium' && (gb < 8 || gb >= 30)) return false;
      if (size === 'large' && gb < 30) return false;
    }
    return true;
  });

  // Step 3: TRI - Plus récent, Plus populaires, Nom A-Z, Nom Z-A
  filtered.sort((a, b) => {
    switch(sortBy) {
      case 'recent':
        return parseDateModified(a.modified_at) - parseDateModified(b.modified_at);
      case 'popular':
        return parseDownloads(b.downloads) - parseDownloads(a.downloads);
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'name-desc':
        return b.name.localeCompare(a.name);
      default:
        return 0;
    }
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

    // Cache models and apply filters
    if (data.models && data.models.length > 0) {
      openrouterModelsCache = data.models;
      filterOpenRouterModels();
    } else {
      document.getElementById('openrouterModelGrid').innerHTML =
        '<div style="color:var(--text-muted); padding:20px">Aucun modèle gratuit trouvé.</div>';
    }

    if (data.updated_at) showCatalogueTimestamp('openrouter', data.updated_at);
  } catch {
    document.getElementById('openrouterLoading').innerText = '❌ Erreur de chargement.';
  }
}

function filterOpenRouterModels() {
  if (!openrouterModelsCache) return;

  const q = document.getElementById('openrouterSearch').value;
  const sortBy = document.getElementById('openrouterSort').value;
  const contextFilter = document.getElementById('openrouterFilterContext').value;

  // Step 1: Recherche puissante (fuzzy, multi-champs)
  let filtered = searchModels(openrouterModelsCache, q);

  // Step 2: Filtre par contexte
  if (contextFilter) {
    filtered = filtered.filter(m => {
      const ctx = m.context_length || 0;
      switch(contextFilter) {
        case '32k': return ctx <= 32000;
        case '128k': return ctx > 32000 && ctx <= 128000;
        case '256k': return ctx > 128000 && ctx <= 256000;
        case '512k+': return ctx > 512000;
        default: return true;
      }
    });
  }

  // Step 3: TRI
  filtered.sort((a, b) => {
    switch(sortBy) {
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'name-desc':
        return b.name.localeCompare(a.name);
      case 'context-desc':
        return (b.context_length || 0) - (a.context_length || 0);
      case 'context-asc':
        return (a.context_length || 0) - (b.context_length || 0);
      default:
        return 0;
    }
  });

  document.getElementById('openrouterLoading').style.display = 'none';
  document.getElementById('openrouterModelGrid').innerHTML =
    filtered.length
      ? filtered.map(m => renderModelCard(m, 'openrouter')).join('')
      : '<div style="color:var(--text-muted); padding:20px; grid-column:1/-1">Aucun modèle trouvé.</div>';
}

async function loadNvidiaModels() {
  document.getElementById('nvidiaLoading').style.display = 'block';
  document.getElementById('nvidiaModelGrid').innerHTML = '';
  try {
    const data = await api('/api/catalogue/nvidia');
    document.getElementById('nvidiaLoading').style.display = 'none';

    // Cache models and apply filters
    if (data.models && data.models.length > 0) {
      nvidiaModelsCache = data.models;
      filterNvidiaModels();
    } else {
      document.getElementById('nvidiaModelGrid').innerHTML =
        '<div style="color:var(--text-muted); padding:20px">Configurez une clé NVIDIA pour voir les modèles.</div>';
    }

    if (data.updated_at) showCatalogueTimestamp('nvidia', data.updated_at);
  } catch {
    document.getElementById('nvidiaLoading').innerText = '❌ Erreur de chargement.';
  }
}

function filterNvidiaModels() {
  if (!nvidiaModelsCache) return;

  const q = document.getElementById('nvidiaSearch').value;
  const sortBy = document.getElementById('nvidiaSort').value;

  // Step 1: Recherche puissante (fuzzy, multi-champs)
  let filtered = searchModels(nvidiaModelsCache, q);

  // Step 2: TRI (par nom seulement pour NVIDIA)
  filtered.sort((a, b) => {
    switch(sortBy) {
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'name-desc':
        return b.name.localeCompare(a.name);
      default:
        return 0;
    }
  });

  document.getElementById('nvidiaLoading').style.display = 'none';
  document.getElementById('nvidiaModelGrid').innerHTML =
    filtered.length
      ? filtered.map(m => renderModelCard(m, 'nvidia')).join('')
      : '<div style="color:var(--text-muted); padding:20px; grid-column:1/-1">Aucun modèle trouvé.</div>';
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

function confirmInstallModel(modelName, sizeBytes, button) {
  const sizeGB = sizeBytes ? (sizeBytes / 1e9).toFixed(1) : null;
  let msg = `Télécharger et installer "${modelName}" ?`;
  if (sizeGB && parseFloat(sizeGB) > 0) {
    msg += `\n\n📦 Taille estimée : ${sizeGB} Go`;
    if (parseFloat(sizeGB) > 10) {
      msg += `\n⚠️ Ce téléchargement est volumineux et peut prendre du temps.`;
    }
  }
  if (!confirm(msg)) return;
  installModel(modelName, button);
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

// ─────────────────────────────────────────────
// Custom Profiles
// ─────────────────────────────────────────────
let customProfilesLoaded = false;
let newProfileModels = [];

async function loadCustomProfiles() {
  try {
    const data = await api('/api/profiles/custom');

    // Builtin profiles
    const builtinEl = document.getElementById('builtinProfilesList');
    if (builtinEl) {
      const emojis = { coding: '💻', reasoning: '🧠', chat: '💬', long: '📄', vision: '👁️', audio: '🎵', translate: '🌍' };
      // Make builtin profile badges clickable to show models in order
      builtinEl.innerHTML = (data.builtin_profiles || []).map(p =>
        `<button class="badge" style="font-size:11px; padding:4px 10px; cursor:pointer" onclick="showBuiltinProfileModels('${p}')">${emojis[p] || '📌'} ${p}</button>`
      ).join('');
    }

    // Custom profiles
    const customEl = document.getElementById('customProfilesList');
    if (customEl) {
      const customs = data.custom_profiles || [];
      if (customs.length === 0) {
        customEl.innerHTML = '<div style="font-size:12px; color:var(--text-dim); padding:10px">Aucun profil personnalisé créé.</div>';
      } else {
        customEl.innerHTML = customs.map(cp => `
          <div style="background:var(--surface); border:1px solid var(--border); border-radius:var(--r-md); padding:12px; display:flex; justify-content:space-between; align-items:center">
            <div>
              <div style="font-weight:600; font-size:13px; font-family:var(--font-mono); color:#fff">✨ ${cp.name}</div>
              ${cp.description ? `<div style="font-size:11px; color:var(--text-dim); margin-top:2px">${cp.description}</div>` : ''}
              ${cp.models && cp.models.length > 0 ? `<div style="font-size:10px; color:var(--text-muted); margin-top:4px">${cp.models.length} modèle(s) associé(s)</div>` : '<div style="font-size:10px; color:var(--text-muted); margin-top:4px">Aucun modèle associé</div>'}
            </div>
            <div style="display:flex; gap:6px">
              <button class="secondary" onclick="viewCustomProfile('${cp.name}')" style="font-size:11px; padding:4px 10px">👁️ Voir</button>
              <button class="secondary" onclick="editCustomProfile('${cp.name}')" style="font-size:11px; padding:4px 10px">✏️ Modifier</button>
              <button class="danger" onclick="deleteCustomProfile('${cp.name}')" style="font-size:11px; padding:4px 10px">🗑</button>
            </div>
          </div>
        `).join('');
      }
    }

    customProfilesLoaded = true;
  } catch (err) {
    console.error('Failed to load custom profiles:', err);
  }
}

// Show models for a builtin profile in a modal (ordered routing chain)
async function showBuiltinProfileModels(profile) {
  try {
    const data = await api(`/api/profiles/builtin/${encodeURIComponent(profile)}`);
    const body = document.getElementById('profileModelsBody');
    const title = document.getElementById('profileModelsTitle');
    if (!body || !title) return;
    title.innerText = `Profil: ${data.profile}`;
    const models = data.models || [];
    if (models.length === 0) {
      body.innerHTML = '<div style="color:var(--text-muted); padding:12px">Aucun modèle configuré pour ce profil.</div>';
    } else {
      body.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:8px; padding:6px 0">
          ${models.map((m, i) => `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 8px; border-radius:6px; background:var(--surface)"><div style="font-family:var(--font-mono); color:var(--text)">${i+1}. ${m}</div><button onclick="copyText('${m.replace(/'/g, "\\'")}', this)" class="ghost" style="font-size:11px">📋</button></div>`).join('')}
        </div>`;
    }
    document.getElementById('profileModelsModal').classList.add('active');
  } catch (err) {
    alert('Erreur: ' + (err.message || err));
  }
}

function closeProfileModelsModal() { document.getElementById('profileModelsModal').classList.remove('active'); }

function removeNewProfileModel(index) {
  newProfileModels.splice(index, 1);
  renderNewProfileModels();
}

function renderNewProfileModels() {
  const el = document.getElementById('newProfileModelsList');
  if (!el) return;
  if (newProfileModels.length === 0) {
    el.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Aucun modèle ajouté</div>';
    return;
  }
  el.innerHTML = newProfileModels.map((m, i) => `
    <div style="display:flex; justify-content:space-between; align-items:center; background:var(--surface); padding:6px 8px; border-radius:6px">
      <div style="display:flex; align-items:center; gap:8px">
        <span style="color:var(--text-muted); font-size:11px">${i+1}.</span>
        <span style="font-family:var(--font-mono); color:var(--text)">${m.model || m}</span>
        ${m.provider ? `<span style="font-size:10px; color:var(--text-dim)">(${m.provider})</span>` : ''}
      </div>
      <div style="display:flex; gap:8px"><button class="ghost" onclick="removeNewProfileModel(${i})">✕</button></div>
    </div>
  `).join('');
}

async function deleteCustomProfile(name) {
  if (!confirm(`Supprimer le profil "${name}" ?`)) return;
  try {
    await api(`/api/profiles/custom/${encodeURIComponent(name)}`, 'DELETE');
    await loadCustomProfiles();
  } catch (err) {
    alert('❌ Erreur : ' + (err.message || 'Impossible de supprimer'));
  }
}

/* ─── PROFILE CREATION FUNCTIONS ─── */

// Global variables for new profile form
function openNewProfileForm() {
  const form = document.getElementById('newProfileForm');
  if (!form) return;

  form.style.display = 'block';

  // Clear form fields
  document.getElementById('newProfileName').value = '';
  document.getElementById('newProfileDesc').value = '';
  document.getElementById('newProfileProvider').selectedIndex = 0;
  document.getElementById('newProfileModel').innerHTML = '<option value="">Sélectionner un provider d\'abord...</option>';
  document.getElementById('newProfileStatus').innerHTML = '';

  // Clear tags
  document.querySelectorAll('.tag-checkbox').forEach(cb => cb.checked = false);

  // Clear models list
  newProfileModels = [];
  renderNewProfileModels();

  // Load providers
  loadProfileProviders();
}

function closeNewProfileForm() {
  const form = document.getElementById('newProfileForm');
  if (form) form.style.display = 'none';
}

async function loadProfileProviders() {
  try {
    const data = await api('/api/db/providers');
    const select = document.getElementById('newProfileProvider');
    if (!select) return;

    // Clear and populate providers
    select.innerHTML = '<option value="">Sélectionner un provider...</option>';
    (data.providers || []).forEach(provider => {
      const option = document.createElement('option');
      option.value = provider.name;
      option.textContent = provider.display_name || provider.name;
      select.appendChild(option);
    });
  } catch (err) {
    console.error('Failed to load providers:', err);
  }
}

async function onProviderChanged() {
  const providerSelect = document.getElementById('newProfileProvider');
  const modelSelect = document.getElementById('newProfileModel');
  const provider = providerSelect.value;

  if (!provider) {
    modelSelect.innerHTML = '<option value="">Sélectionner un provider d\'abord...</option>';
    return;
  }

  try {
    modelSelect.innerHTML = '<option value="">Chargement...</option>';

    // Get models for this provider from database
    const data = await api('/api/db/models');
    const models = (data.models || []).filter(m => m.provider === provider);

    if (models.length === 0) {
      modelSelect.innerHTML = '<option value="">Aucun modèle disponible</option>';
      return;
    }

    // Populate model select
    modelSelect.innerHTML = '<option value="">Sélectionner un modèle...</option>';
    models.forEach(model => {
      const option = document.createElement('option');
      option.value = model.name;
      option.textContent = model.display_name || model.name;
      option.dataset.provider = provider;
      modelSelect.appendChild(option);
    });
  } catch (err) {
    modelSelect.innerHTML = '<option value="">Erreur de chargement</option>';
    console.error('Failed to load models:', err);
  }
}

function addNewProfileModel() {
  const modelSelect = document.getElementById('newProfileModel');
  const selectedOption = modelSelect.selectedOptions[0];
  const model = modelSelect.value;

  if (!model) {
    alert('Veuillez sélectionner un modèle');
    return;
  }

  // Add to newProfileModels array
  newProfileModels.push({
    model: model,
    provider: selectedOption.dataset.provider || document.getElementById('newProfileProvider').value
  });

  // Update UI
  renderNewProfileModels();

  // Reset selection
  modelSelect.selectedIndex = 0;
}

function renderNewProfileModels() {
  const el = document.getElementById('newProfileModelsList');
  if (!el) return;

  if (newProfileModels.length === 0) {
    el.innerHTML = '<div style="font-size:12px; color:var(--text-muted)">Aucun modèle ajouté</div>';
    return;
  }

  el.innerHTML = newProfileModels.map((m, i) => `
    <div style="display:flex; justify-content:space-between; align-items:center; background:var(--surface); padding:6px 8px; border-radius:6px">
      <div style="display:flex; align-items:center; gap:8px">
        <span style="color:var(--text-muted); font-size:11px">${i+1}.</span>
        <span style="font-family:var(--font-mono); color:var(--text)">${m.model}</span>
        <span style="font-size:10px; color:var(--text-dim)">(${m.provider})</span>
      </div>
      <div style="display:flex; gap:8px">
        <button class="ghost" onclick="removeNewProfileModel(${i})" style="font-size:11px; padding:2px 6px">✕</button>
      </div>
    </div>
  `).join('');
}

function removeNewProfileModel(index) {
  newProfileModels.splice(index, 1);
  renderNewProfileModels();
}

async function createCustomProfile() {
  const nameInput = document.getElementById('newProfileName');
  const descInput = document.getElementById('newProfileDesc');
  const statusEl = document.getElementById('newProfileStatus');

  const name = (nameInput.value || '').trim().toLowerCase();
  const description = (descInput.value || '').trim();

  if (!name) {
    statusEl.innerHTML = '<span style="color:var(--error)">❌ Nom requis</span>';
    return;
  }

  // Validate name format (2-30 chars, lowercase alphanumeric, dashes and underscores, must start with letter)
  const nameRegex = /^[a-z][a-z0-9_-]{1,29}$/;
  if (!nameRegex.test(name)) {
    statusEl.innerHTML = '<span style="color:var(--error)">❌ Format invalide: 2-30 caractères, commence par une lettre</span>';
    return;
  }

  if (newProfileModels.length === 0) {
    statusEl.innerHTML = '<span style="color:var(--warning)">⚠️ Aucun modèle ajouté (profil vide)</span>';
  }

  try {
    statusEl.innerHTML = '<span style="color:var(--text-dim)">⏳ Création en cours...</span>';

    const payload = {
      name: name,
      description: description,
      models: newProfileModels
    };

    await api('/api/profiles/custom', 'POST', payload);

    statusEl.innerHTML = '<span style="color:var(--success)">✅ Profil créé avec succès!</span>';

    // Refresh profiles list
    await loadCustomProfiles();

    // Close form after delay
    setTimeout(() => {
      closeNewProfileForm();
    }, 1500);

  } catch (err) {
    statusEl.innerHTML = `<span style="color:var(--error)">❌ Erreur: ${err.message || 'Échec de création'}</span>`;
  }
}

/* ─── MY MODELS FUNCTIONS ─── */

async function loadMyModels() {
  try {
    // This function was called but not implemented
    // It should refresh the "Mes Modèles" section
    console.log('loadMyModels called - refreshing models display');

    // Trigger filtering to refresh display
    filterMyModels();
  } catch (err) {
    console.error('Failed to load my models:', err);
  }
}

function filterMyModels() {
  // Implementation would go here to filter models based on search/filter criteria
  // This is a placeholder for now
  console.log('filterMyModels called');
}

function showMyModelsView(view) {
  // Switch between "providers" and "profiles" views
  document.querySelectorAll('.mymodels-view').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.subtab').forEach(btn => btn.classList.remove('active'));

  if (view === 'providers') {
    document.getElementById('mymodels-providers-view').style.display = 'block';
    document.getElementById('mymodels-view-providers').classList.add('active');
  } else {
    document.getElementById('mymodels-profiles-view').style.display = 'block';
    document.getElementById('mymodels-view-profiles').classList.add('active');
  }
}

function closeMyModelsModal() {
  const modal = document.getElementById('mymodels-detail-modal');
  if (modal) modal.style.display = 'none';
}

/* ─── CUSTOM PROFILE VIEW/EDIT FUNCTIONS ─── */

// Store profile data for editing
let editingProfileData = null;

// View profile details
async function viewCustomProfile(name) {
  try {
    const data = await api('/api/profiles/custom');
    const profile = (data.custom_profiles || []).find(cp => cp.name === name);
    
    if (!profile) {
      alert('Profil non trouvé');
      return;
    }
    
    // Get model details
    const modelsList = profile.routing_chain || profile.models || [];
    let modelsHtml = '';
    
    if (modelsList.length > 0) {
      modelsHtml = modelsList.map((m, i) => {
        const modelName = typeof m === 'string' ? m : (m.model || 'Unknown');
        const providerName = typeof m === 'string' ? '' : (m.provider || '');
        return `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 8px; border-radius:6px; background:var(--surface); margin-bottom:4px">
          <div>
            <span style="color:var(--text-muted); font-size:11px">${i+1}.</span>
            <span style="font-family:var(--font-mono); color:var(--text); margin-left:8px">${modelName}</span>
          </div>
          ${providerName ? `<span style="font-size:10px; color:var(--text-dim)">(${providerName})</span>` : ''}
        </div>`;
      }).join('');
    } else {
      modelsHtml = '<div style="color:var(--text-muted); padding:12px">Aucun modèle associé</div>';
    }
    
    // Show in modal or alert
    const body = document.getElementById('profileModelsBody');
    const title = document.getElementById('profileModelsTitle');
    if (body && title) {
      title.innerText = 'Profil: ' + profile.name;
      body.innerHTML = `
        <div style="margin-bottom:16px">
          <div style="font-size:12px; color:var(--text-dim); margin-bottom:8px">${profile.description || 'Aucune description'}</div>
          <div style="font-size:11px; color:var(--text-muted)">${modelsList.length} modèle(s)</div>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px">
          ${modelsHtml}
        </div>
      `;
      document.getElementById('profileModelsModal').classList.add('active');
    } else {
      // Fallback to alert if modal not found
      alert('Profil: ' + profile.name + '\n\nDescription: ' + (profile.description || 'Aucune') + '\n\nModèles: ' + modelsList.map(m => typeof m === 'string' ? m : m.model).join(', '));
    }
  } catch (err) {
    alert('Erreur: ' + (err.message || err));
  }
}

// Edit profile - populate form with existing data
async function editCustomProfile(name) {
  try {
    const data = await api('/api/profiles/custom');
    const profile = (data.custom_profiles || []).find(cp => cp.name === name);
    
    if (!profile) {
      alert('Profil non trouvé');
      return;
    }
    
    // Store profile data for editing
    editingProfileData = {
      originalName: name,
      name: profile.name,
      description: profile.description || '',
      models: profile.models || []
    };
    
    // Open the form and populate fields
    openNewProfileForm();
    
    // Fill in the form fields
    document.getElementById('newProfileName').value = profile.name;
    document.getElementById('newProfileName').disabled = true; // Can't change name during edit
    document.getElementById('newProfileDesc').value = profile.description || '';
    
    // Load providers for the dropdown
    await loadProfileProviders();
    
    // Populate models from routing_chain
    newProfileModels = [];
    const modelsList = profile.routing_chain || profile.models || [];
    for (const m of modelsList) {
      // routing_chain has {order, model, provider, ...}
      if (m.model) {
        newProfileModels.push({ model: m.model, provider: m.provider || '' });
      } else if (typeof m === 'string') {
        newProfileModels.push({ model: m, provider: '' });
      }
    }
    renderNewProfileModels();
    
    // Update status to show we're editing
    document.getElementById('newProfileStatus').innerHTML = '<span style="color:var(--warning)">⚠️ Mode modification - Impossible de changer le nom</span>';
    
  } catch (err) {
    alert('Erreur: ' + (err.message || err));
  }
}

// Override createCustomProfile to handle edit mode
const originalCreateCustomProfile = createCustomProfile;
createCustomProfile = async function() {
  if (editingProfileData) {
    // We're in edit mode - update the profile instead of creating new
    await updateCustomProfile();
    return;
  }
  // Original create logic
  await originalCreateCustomProfile.call(this);
};

// Update existing profile
async function updateCustomProfile() {
  if (!editingProfileData) return;
  
  const statusEl = document.getElementById('newProfileStatus');
  const descInput = document.getElementById('newProfileDesc');
  
  const description = (descInput.value || '').trim();
  
  try {
    statusEl.innerHTML = '<span style="color:var(--text-dim)">⏳ Mise à jour en cours...</span>';
    
    // Build the models array in the format the API expects
    const models = newProfileModels.map(m => ({
      model: m.model,
      provider: m.provider
    }));
    
    // Delete old profile and create new one (since name can't be changed)
    // First delete
    await api(`/api/profiles/custom/${encodeURIComponent(editingProfileData.originalName)}`, 'DELETE');
    
    // Then create with new data
    const payload = {
      name: editingProfileData.originalName, // Keep same name
      description: description,
      models: models
    };
    
    await api('/api/profiles/custom', 'POST', payload);
    
    statusEl.innerHTML = '<span style="color:var(--success)">✅ Profil mis à jour!</span>';
    
    // Refresh profiles list
    await loadCustomProfiles();
    
    // Close form and reset edit mode
    editingProfileData = null;
    
    setTimeout(() => {
      closeNewProfileForm();
    }, 1500);
    
  } catch (err) {
    statusEl.innerHTML = '<span style="color:var(--error)">❌ Erreur: ' + (err.message || 'Échec de mise à jour') + '</span>';
  }
}

// Reset edit mode when form is closed
const originalCloseNewProfileForm = closeNewProfileForm;
closeNewProfileForm = function() {
  editingProfileData = null;
  document.getElementById('newProfileName').disabled = false;
  originalCloseNewProfileForm.call(this);
};
