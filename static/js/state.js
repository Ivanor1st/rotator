  /* ─── STATE ─── */
  let currentTab = 'routing';
  let currentSub = 'unit';
  let lockProfile = null;
  let modelsCatalog = {};
  let charts = { providers: null, profiles: null };
  let logsCache = [];
  let presetDraft = { profiles: {} };
  const keyProviders = ['ollama_cloud', 'nvidia', 'openrouter', 'google'];
  let keysState = {};
  const keyTestTimers = {};
  const keyTestStatus = {};
  const keyTestMessages = {};
  let keyTestCenterState = {};
  let keyTestCenterRunning = false;
  let ollamaModelsCache = [];
  let catTab = 'ollama';
  let configEditorMode = 'locked';
  let readmeLoaded = false;

  /* ─── PAGES META ─── */
  const PAGE_META = {
    routing:  { title: 'Vue d\'ensemble',       desc: 'État du routage et des providers en temps réel' },
    presets:  { title: 'Presets de routage',     desc: 'Créez et appliquez des configurations nommées' },
    tests:    { title: 'Tests & Benchmark',      desc: 'Vérifiez les providers et comparez les modèles' },
    stats:    { title: 'Statistiques',           desc: 'Analyse détaillée de l\'utilisation et des quotas' },
    logs:     { title: 'Journal d\'activité',    desc: 'Requêtes, rotations et événements en temps réel' },
    keys:     { title: 'Mes clés API',           desc: 'Gérez vos clés pour chaque fournisseur' },
    projects: { title: 'Projets & tokens',       desc: 'Isolation des quotas/logs par projet' },
    claudecode:{ title: 'Claude Code',           desc: 'Sessions, modèles épinglés, mémoire et configuration Claude Code' },
    openclaw: { title: 'OpenClaw',               desc: 'Connectez vos apps de messagerie à l\'IA via le rotator' },
    backups:  { title: 'Sauvegardes',            desc: 'Backups DB, restauration, purge et réinitialisation' },
    catalogue:{ title: 'Catalogue de modèles',   desc: 'Parcourez et installez des modèles depuis Ollama, OpenRouter et NVIDIA' },
    config:   { title: 'Configuration',          desc: 'Modifiez les paramètres du proxy' },
    docs:     { title: 'Documentation',          desc: 'Guide complet — endpoints, providers, sécurité et dépannage' },
  };
