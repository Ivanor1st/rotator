# Ollama Catalog Sort & Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ajouter le tri (Plus récent, Plus populaires, Nom A→Z, Nom Z→A) et améliorer la recherche (fuzzy, multi-champs) pour le catalogue Ollama.

**Architecture:** Parser les champs `modified_at` et `downloads` pour le tri, implémenter une recherche fuzzy simple sans dépendance externe, ajouter un dropdown de tri dans l'UI.

**Tech Stack:** Vanilla JavaScript (pas de dépendance externe), HTML, CSS

---

## Task 1: Ajouter le dropdown de tri dans dashboard.html

**Files:**
- Modify: `dashboard.html:1470-1489` (barre d'outils Ollama)

**Step 1: Localiser la barre d'outils**

Ouvrir `dashboard.html` et trouver la section `cat-ollama` autour de la ligne 1470.

**Step 2: Ajouter le select de tri**

Ajouter un nouveau `<select id="ollamaSort">` après le champ de recherche :

```html
<select id="ollamaSort" onchange="filterOllamaModels()" style="width:150px">
  <option value="recent">⭐ Plus récent</option>
  <option value="popular">⭐ Plus populaires</option>
  <option value="name-asc">Nom A → Z</option>
  <option value="name-desc">Nom Z → A</option>
</select>
```

Le placement doit être après la ligne 1472 (input search) et avant le filtre type.

---

## Task 2: Ajouter les fonctions de parsing dans helpers.js

**Files:**
- Modify: `static/js/helpers.js:807` (fonction filterOllamaModels)

**Step 1: Ajouter parseDateModified()**

Ajouter cette fonction AVANT `filterOllamaModels()` :

```javascript
function parseDateModified(str) {
  // "2 years ago" → nombre de mois depuis maintenant (plus petit = plus récent)
  if (!str || str === 'unknown') return 999;
  const num = parseInt(str);
  if (str.includes('year')) return (new Date().getFullYear() - num) * 12;
  if (str.includes('month')) return new Date().getMonth() - num;
  if (str.includes('week')) return new Date().getMonth() - (num / 4);
  if (str.includes('day')) return new Date().getMonth() - (num / 30);
  return 999; // en dernier
}
```

**Step 2: Ajouter parseDownloads()**

```javascript
function parseDownloads(str) {
  // "109.6K" → 109600, "2.4M" → 2400000
  if (!str) return 0;
  if (str.includes('M')) return parseFloat(str) * 1e6;
  if (str.includes('K')) return parseFloat(str) * 1e3;
  return parseInt(str) || 0;
}
```

---

## Task 3: Ajouter fuzzyMatch() et searchModels()

**Files:**
- Modify: `static/js/helpers.js`

**Step 1: Ajouter fuzzyMatch()**

```javascript
function fuzzyMatch(text, query) {
  if (!text || !query) return { match: false, score: 0 };
  const t = text.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return { match: true, score: 1 };

  // Recherche exacte
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
```

**Step 2: Ajouter searchModels()**

```javascript
function searchModels(models, query) {
  if (!query || !query.trim()) return models;
  const q = query.toLowerCase().trim();

  return models.filter(m => {
    // Recherche dans le nom
    if (fuzzyMatch(m.name, q).match) return true;
    // Recherche dans la description
    if (fuzzyMatch(m.description || '', q).match) return true;
    // Recherche dans les tags
    if ((m.tags || []).some(t => fuzzyMatch(t, q).match)) return true;
    return false;
  });
}
```

---

## Task 4: Modifier filterOllamaModels() pour intégrer tri et recherche

**Files:**
- Modify: `static/js/helpers.js:807-834`

**Step 1: Ajouter la logique de tri et recherche**

Remplacer la fonction actuelle `filterOllamaModels()` par :

```javascript
function filterOllamaModels() {
  const q = document.getElementById('ollamaSearch').value;
  const sortBy = document.getElementById('ollamaSort').value;
  const type = document.getElementById('ollamaFilterType').value;
  const size = document.getElementById('ollamaFilterSize').value;

  // Step 1: Recherche puissante (fuzzy, multi-champs)
  let filtered = searchModels(ollamaModelsCache, q);

  // Step 2: Filtres existants (type et size)
  filtered = filtered.filter(m => {
    // Get size from first variant
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

  // Render
  document.getElementById('ollamaLoading').style.display = 'none';
  document.getElementById('ollamaModelGrid').innerHTML =
    filtered.length
      ? filtered.map(m => renderModelCard(m, 'ollama')).join('')
      : '<div style="color:var(--text-muted); padding:20px; grid-column:1/-1">Aucun modèle trouvé.</div>';
}
```

---

## Task 5: Tester manuellement

**Step 1: Démarrer le serveur**

```powershell
python main.py
```

**Step 2: Ouvrir le dashboard**

Aller à http://localhost:47822/dashboard

**Step 3: Vérifier les changements**

1. **Tri** : Le dropdown "Plus récent" doit être visible et fonctionnel
   - Cliquer sur "Plus populaires" → les modèles avec le plus de downloads en premier
   - Cliquer sur "Nom A → Z" → tri alphabétique

2. **Recherche** :
   - Taper "athene" → doit trouver "athene-v2"
   - Taper "aya" → doit trouver les modèles avec "aya" dans le nom ou description
   - Tester avec une faute de frappe (ex: "athne" au lieu de "athene")

---

## Task 6: Commit

```bash
git add dashboard.html static/js/helpers.js
git commit -m "feat(catalog): add sort (recent/popular/A-Z) and fuzzy search for Ollama models

- Add sort dropdown with recent, popular, name options
- Add fuzzyMatch() for typo-tolerant search
- Add searchModels() for multi-field search (name, description, tags)
- Parse modified_at and downloads for sorting"
```
