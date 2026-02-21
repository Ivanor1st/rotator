# API Rotator — Guide d'utilisation

Proxy local compatible OpenAI / Anthropic qui choisit automatiquement le meilleur modèle selon le type de tâche (`coding`, `reasoning`, `chat`, `long`, `vision`, `audio`, `translate`) et effectue une rotation automatique des clés API en cas de quota atteint ou d'erreurs répétées.

---

## 1. Prérequis

| Élément | Détail |
|---------|--------|
| **OS** | Windows + PowerShell 5.1+ |
| **Python** | 3.10+ dans le `PATH` |
| **Ollama** | Optionnel — recommandé pour les fallbacks locaux infinis |

---

## 2. Installation

```powershell
# Option A — via le lanceur (crée .venv + installe tout)
.\start.ps1

# Option B — manuel
pip install -r requirements.txt
python main.py
```

Premier lancement typique :

```powershell
cd "$HOME\Downloads\rotator"
.\start.ps1
```

> **PowerShell bloque les scripts ?**
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\start.ps1
> ```

### Enregistrer la commande `rotator` (accès global)

```powershell
.\rotator-register.ps1
```

Après ça, depuis **n'importe quel dossier** :

```powershell
rotator                    # démarre si besoin + ouvre le dashboard
rotator -StatusOnly        # statut rapide
rotator -Stop              # arrête le proxy
rotator -Restart           # redémarre le proxy
rotator -Claude            # lance Claude Code
rotator -Dashboard         # ouvre le dashboard
```

> Pour désinstaller : `.\rotator-register.ps1 -Uninstall`

---

## 3. Configuration

Éditez `config.yaml` (ou copiez `config.example.yaml`).

### Clés API

Utilisez des références d'environnement plutôt que des clés en clair :

```yaml
keys:
  openrouter:
    - label: "OpenRouter 1"
      key: "env:OPENROUTER_KEY"
  nvidia:
    - label: "NVIDIA 1"
      key: "env:NVIDIA_KEY"
  google:
    - label: "Google 1"
      key: "env:GOOGLE_KEY"
```

Préparez vos variables dans un fichier `.env` :

```
OPENROUTER_KEY=sk-or-...
NVIDIA_KEY=nvapi-...
GOOGLE_KEY=AIza...
```

### Paramètres principaux

| Clé | Description | Défaut |
|-----|-------------|--------|
| `settings.port` | Port du proxy | `47822` |
| `settings.require_auth_header` | En-tête `Authorization` obligatoire | `false` |
| `settings.auth_bruteforce_protection` | Protection anti brute-force | `true` |
| `settings.invalid_token_limit_per_minute` | Seuil de tokens invalides | `10` |
| `settings.invalid_token_block_seconds` | Durée de blocage | `300` |

### Sauvegardes automatiques

```yaml
settings:
  backups:
    auto_backup_on_shutdown: true
    auto_restore_latest_on_startup: true
```

### Recharge à chaud

```powershell
Invoke-RestMethod -Uri "http://localhost:47822/api/reload-config" -Method Post
```

---

## 4. Démarrer le proxy

### Première fois (installation complète)

```powershell
.\start.ps1
```

| Option | Action |
|--------|--------|
| `[1]` | Démarrer le proxy (direct) |
| `[2]` | Vérifier le statut |
| `[3]` | Connecter Claude Code |
| `[4]` | Ouvrir le dashboard |

### Lancements suivants (rapide, sans réinstallation)

```powershell
.\rotator-quick.ps1            # démarre si besoin + dashboard
.\rotator-quick.ps1 -StatusOnly
.\rotator-quick.ps1 -Stop
.\rotator-quick.ps1 -Restart
.\rotator-quick.ps1 -Claude
```

Ou, après enregistrement global (`.\rotator-register.ps1`) :

```powershell
rotator                        # depuis n'importe où
rotator -Claude -WorkDir "D:\Projects\myapp"
```

### Lancement non-interactif (scripts CI, tâches planifiées)

```powershell
.\start.ps1 go                 # auto-install deps + démarre + vérifie HTTP readiness
```

Après démarrage, le terminal affiche les URLs :

- **Proxy** : `http://localhost:47822`
- **Dashboard** : `http://localhost:47822/dashboard`
- **API** : `http://localhost:47822/v1`

---

## 5. Connecter Claude Code

### Via le lanceur

```powershell
.\start.ps1    # choisir option [3]
```

### Via le dashboard

Onglet **Claude Code** → Lancement rapide → cliquer **▶ Créer token + lancer Claude Code**.

### Manuellement

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:47822"
$env:ANTHROPIC_AUTH_TOKEN = "rotator"
claude --model coding
```

Le proxy expose `/v1/messages` (API Anthropic) et `/v1/chat/completions` (API OpenAI). Claude Code utilise l'API Anthropic nativement.

> **Alias supportés** : `claude-sonnet-4-6`, `gpt-5-mini`, `github/gpt5mini` → profil `coding`.

---

## 6. Profils de routage

| Profil | Usage |
|--------|-------|
| `coding` | Code, debug, implémentation |
| `reasoning` | Explications, analyse, maths |
| `chat` | Conversation générale (défaut) |
| `long` | Gros contexte / documents |
| `vision` | Images jointes |
| `audio` | Audio / transcription |
| `translate` | Traduction |

Si `--model` n'est pas précisé, le profil est détecté automatiquement depuis le contenu du prompt.

---

## 7. Dashboard Web

```
http://localhost:47822/dashboard
```

12 onglets : Vue d'ensemble · Presets · Tests & Benchmark · Statistiques · Journal · Clés API · Projets & tokens · **Claude Code** · Sauvegardes · Catalogue modèles · Configuration · Documentation.

Fonctionnalités clés :
- État des 7 profils et providers actifs
- Catalogue de modèles local (cache JSON) avec bouton rafraîchir
- Gestion des clés (ajout, test, sauvegarde)
- Centre Claude Code (connexion, modèles épinglés, sessions, mémoire)
- Sauvegardes et restauration
- Comparaison de modèles et benchmark

---

## 8. Commandes CLI

```powershell
.\rotator.ps1 status                     # État du proxy
.\rotator.ps1 force coding nvidia        # Forcer coding → NVIDIA
.\rotator.ps1 force chat local           # Forcer chat → local
.\rotator.ps1 key block "Google 1"       # Bloquer une clé
.\rotator.ps1 key unblock "Google 1"     # Débloquer une clé
.\rotator.ps1 reset                      # Remettre tout à auto
.\rotator.ps1 force all local            # Urgence : tout en local
.\rotator.ps1 benchmark                  # Lancer un benchmark
.\rotator.ps1 logs --follow              # Logs en direct
```

---

## 9. API exposée

> Source de vérité : `GET /openapi.json` et Swagger UI à `/docs` quand le serveur tourne.

### Compatibilité

| Endpoint | Protocole | Usage |
|----------|-----------|-------|
| `POST /v1/chat/completions` | OpenAI | SDK OpenAI, apps, sites |
| `POST /v1/messages` | Anthropic | Claude Code, SDK Anthropic |
| `GET /v1/models` | OpenAI | Liste des modèles disponibles |

### Configuration & clés

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/config` | Lire le config.yaml |
| `POST` | `/api/config` | Écrire le config.yaml |
| `GET` | `/api/config/keys` | Lire les clés structurées |
| `POST` | `/api/config/keys` | Enregistrer les clés |
| `POST` | `/api/config/keys/test` | Tester une clé cloud |
| `POST` | `/api/pause` | Mettre le proxy en pause |
| `POST` | `/api/resume` | Reprendre le proxy |
| `POST` | `/api/restart` | Redémarrer le proxy |
| `POST` | `/api/reload-config` | Recharger la config |

### Routage & overrides

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/override/force` | Forcer un profil → provider |
| `POST` | `/api/override/block` | Bloquer un provider |
| `POST` | `/api/override/unblock` | Débloquer un provider |
| `POST` | `/api/override/reset` | Remettre tout à auto |
| `POST` | `/api/lock` | Verrouiller un modèle |
| `DELETE` | `/api/lock/{profile}` | Supprimer un verrou |

### Catalogue & installation

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/catalogue/ollama` | Modèles Ollama (cache local) |
| `GET` | `/api/catalogue/openrouter` | Modèles OpenRouter gratuits |
| `GET` | `/api/catalogue/nvidia` | Modèles NVIDIA NIM |
| `GET` | `/api/catalogue/local` | Modèles installés localement |
| `POST` | `/api/catalogue/refresh` | Rafraîchir tous les caches |
| `POST` | `/api/catalogue/install` | Installer un modèle |
| `GET` | `/api/catalogue/install/status` | Progression d'installation |
| `POST` | `/api/catalogue/add-to-rotator` | Ajouter au rotator |
| `POST` | `/api/catalogue/delete` | Supprimer un modèle local |

### Projets & Claude Code

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/projects` | Lister les projets |
| `POST` | `/api/projects` | Créer un projet |
| `POST` | `/api/projects/{id}/revoke` | Révoquer un token |
| `POST` | `/api/projects/claude-onboarding` | Créer token Claude |
| `POST` | `/api/projects/claude-onboarding/launch` | Lancer terminal Claude |
| `GET` | `/api/claude-code/memory?dir=...` | Lire CLAUDE.md |
| `POST` | `/api/claude-code/memory` | Écrire CLAUDE.md |

### Sauvegardes & maintenance

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/maintenance/backups` | Lister les snapshots |
| `POST` | `/api/maintenance/backup` | Créer un snapshot |
| `POST` | `/api/maintenance/restore` | Restaurer un snapshot |
| `DELETE` | `/api/maintenance/backups/{name}` | Supprimer un snapshot |
| `POST` | `/api/maintenance/purge-before` | Purger avant une date |
| `POST` | `/api/maintenance/reset-all` | Réinitialiser la DB |
| `GET/POST` | `/api/maintenance/settings` | Options auto-backup |

### Monitoring & stats

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/status` | État global du proxy |
| `GET` | `/api/health` | Santé des providers |
| `GET` | `/api/quota` | Quotas par provider |
| `GET` | `/api/logs` | Derniers logs |
| `GET` | `/api/stats` | Statistiques (period=today/week/month) |
| `GET` | `/api/security/status` | État sécurité |

### Tests & benchmark

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/tests/run` | Lancer tous les tests |
| `POST` | `/api/benchmark/start` | Lancer benchmark |
| `POST` | `/api/compare` | Comparer des modèles |

---

## 10. Dépannage

| Problème | Solution |
|----------|----------|
| Proxy inaccessible | Vérifier que `start.ps1` tourne, port `47822` libre |
| Aucun provider dispo | Vérifier clés dans `config.yaml` et état `blocked`/`force` |
| Quotas Google épuisés | Attendre le reset ou forcer `local`/`openrouter` |
| Config non prise en compte | `POST /api/reload-config` |
| `running scripts is disabled` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `python is not recognized` | `winget install Python.Python.3.12` |
| Port occupé | `.\rotator.ps1 stop --force` puis `.\start.ps1` |
| Claude dit "model doesn't exist" | Vérifier que `.env` existe et contient les clés |

---

## 11. Sécurité

- Ne versionnez jamais un `config.yaml` contenant des clés réelles
- Utilisez `env:VAR_NAME` dans le YAML + fichier `.env` local
- Activez `require_auth_header: true` en production
- La protection brute-force bloque les IPs après trop de tokens invalides
- Statut sécurité : `GET /api/security/status`
