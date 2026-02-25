# Design: Amélioration du Catalogue Ollama - Tri et Recherche

**Date:** 2026-02-25
**Auteur:** Claude
**Status:** Approuvé

---

## Objectif

Améliorer l'expérience utilisateur du catalogue de modèles Ollama dans le dashboard :
1. Ajouter un tri (Plus récent, Plus populaires, Nom A→Z, Nom Z→A)
2. Améliorer la recherche (fuzzy, multi-champs)

---

## Contexte

### Données disponibles (ollama_models_cloud.json)

| Champ | Exemple | Usage |
|-------|---------|-------|
| `name` | `athene-v2` | Affichage, tri nom |
| `description` | "Aya 23..." | Recherche |
| `tags` | `["tools"]` | Recherche, filtre |
| `downloads` | `"109.6K"`, `"2.4M"` | Tri popularité |
| `modified_at` | `"2 years ago"` | Tri récent |

### État actuel

- Filtres : Type (Cloud/Local/Vision/Tools/Thinking), Taille
- **Manquant** : Tri, recherche puissante

---

## Design détaillé

### 1. Ajout du TRI

**Nouvelle UI (dashboard.html):**
```html
<select id="ollamaSort" onchange="filterOllamaModels()">
  <option value="recent">⭐ Plus récent</option>
  <option value="popular">⭐ Plus populaires</option>
  <option value="name-asc">Nom A → Z</option>
  <option value="name-desc">Nom Z → A</option>
</select>
```

**Logique de tri (helpers.js):**

```javascript
function parseDateModified(str) {
  // "2 years ago" → nombre de mois depuis maintenant
  const now = new Date();
  const num = parseInt(str);
  if (str.includes('year')) return num * 12;
  if (str.includes('month')) return num;
  if (str.includes('week')) return num / 4;
  if (str.includes('day')) return num / 30;
  return 999; // "unknown" en dernier
}

function parseDownloads(str) {
  // "109.6K" → 109600, "2.4M" → 2400000
  if (str.includes('M')) return parseFloat(str) * 1e6;
  if (str.includes('K')) return parseFloat(str) * 1e3;
  return 0;
}

function sortModels(models, sortBy) {
  return [...models].sort((a, b) => {
    switch(sortBy) {
      case 'recent':
        return parseDateModified(b.modified_at) - parseDateModified(a.modified_at);
      case 'popular':
        return parseDownloads(b.downloads) - parseDownloads(a.downloads);
      case 'name-asc':
        return a.name.localeCompare(b.name);
      case 'name-desc':
        return b.name.localeCompare(a.name);
    }
  });
}
```

---

### 2. Recherche PUISSANTE

**Améliorations:**
- Recherche fuzzy (tolère les fautes de frappe)
- Recherche multi-champs : name, description, tags
- Highlight des termes recherchés

**Implémentation avec regex simple (sans dépendance externe):**

```javascript
function fuzzyMatch(text, query) {
  // Convertit en lowercase et échappe les caractères spéciaux
  const t = text.toLowerCase();
  const q = query.toLowerCase().trim();

  // Recherche exacte d'abord
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

function searchModels(models, query) {
  if (!query) return models;

  return models.filter(m => {
    const nameMatch = fuzzyMatch(m.name, query);
    const descMatch = fuzzyMatch(m.description || '', query);
    const tagsMatch = (m.tags || []).some(t => fuzzyMatch(t, query).match);

    return nameMatch.match || descMatch.match || tagsMatch.match;
  });
}
```

---

## Fichiers à modifier

1. **dashboard.html** (~ligne 1470)
   - Ajouter `<select id="ollamaSort">` dans la toolbar

2. **helpers.js** (~ligne 807)
   - Ajouter `parseDateModified()`
   - Ajouter `parseDownloads()`
   - Ajouter `fuzzyMatch()`
   - Ajouter `searchModels()`
   - Modifier `filterOllamaModels()` pour intégrer tri et recherche

---

## Ordre de priorité

1. Parser les dates et downloads
2. Ajouter le dropdown de tri
3. Implémenter la recherche fuzzy
4. Tester avec les données existantes
