/* ─── TABS ─── */
function showTab(name) {
  currentTab = name;
  document.querySelectorAll('.top-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.top-section').forEach(s => s.classList.remove('active'));
  const tab = document.querySelector(`.top-tab[onclick="showTab('${name}')"]`);
  if (tab) tab.classList.add('active');
  const sec = document.getElementById(`tab-${name}`);
  if (sec) sec.classList.add('active');

  // Handle skeleton loaders - hide skeleton, show content
  const skeletonMap = {
    'routing': ['profileCardsSkeleton', 'providerGridSkeleton', 'securityCardSkeleton'],
    'presets': ['presetsSkeleton'],
    'stats': ['statsSkeleton']
    // Tests n'a pas de skeleton - contenu toujours visible
  };
  const contentMap = {
    'routing': ['profileCards', 'providerGrid', 'securityCard'],
    'presets': ['presetsContent'],
    'stats': ['statsContent']
    // Tests n'a pas de content séparé
  };

  // Hide skeleton loaders and show content for this tab
  if (skeletonMap[name]) {
    skeletonMap[name].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
  }
  if (contentMap[name]) {
    contentMap[name].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = id === 'presetsContent' ? 'grid' : (id === 'testsContent' ? 'block' : 'block');
    });
  }

  if (name === 'catalogue' && ollamaModelsCache.length === 0) loadOllamaModels();
  if (name === 'myprofiles') { loadCustomProfiles(); loadMyModels(); }
  if (name === 'projects') loadProjects();
  if (name === 'claudecode') ccLoadConnect();
  if (name === 'openclaw') ocLoadConnect();
  if (name === 'backups') loadBackups();
  if (name === 'docs') loadReadme();
  const meta = PAGE_META[name] || {};
  document.getElementById('pageTitle').innerText = meta.title || name;
  document.getElementById('pageDesc').innerText = meta.desc || '';
  // Show welcome toggle only on routing tab
  const toggleBtn = document.getElementById('welcomeToggleBtn');
  if (toggleBtn) toggleBtn.style.display = name === 'routing' ? 'flex' : 'none';
}

function showDocsSection(name) {
  document.querySelectorAll('.docs-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.docs-nav-item').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById(`docs-${name}`);
  if (sec) sec.classList.add('active');
  const navItems = document.querySelectorAll('.docs-nav-item');
  navItems.forEach(item => {
    if (item.getAttribute('onclick') === `showDocsSection('${name}')`) {
      item.classList.add('active');
    }
  });
}

function showSubTab(name) {
  currentSub = name;
  document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.sub-section').forEach(s => s.classList.remove('active'));
  const btn = document.querySelector(`.sub-tab[onclick="showSubTab('${name}')"]`);
  if (btn) btn.classList.add('active');
  const sec = document.getElementById(`sub-${name}`);
  if (sec) sec.classList.add('active');
}
