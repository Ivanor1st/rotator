# Gemini Native Rotator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Brancher Gemini CLI 0.61.0 sur `D:\Project\rotator` avec un proxy Google natif, une rotation dynamique des clés de `D:\googlewiki\googlekeys.txt` et un failover sûr sur quota ou erreur.

**Architecture:** Ajouter un chargeur de clés externe avec identifiants stables par empreinte, persister l’état de santé dans SQLite, puis exposer un reverse proxy natif `/v1beta` qui conserve les payloads Gemini et le SSE. Le CLI utilisera un jeton local dans `GEMINI_API_KEY`; les clés Google resteront uniquement dans le fichier protégé et ne seront jamais renvoyées par le proxy.

**Tech Stack:** Python 3.10+, FastAPI, httpx, aiosqlite, PyYAML, pytest, SQLite.

---

## Task 1: Écrire les tests du chargeur de clés

**Files:**
- Create: `google_keys.py`
- Create: `tests/test_google_keys.py`

**Step 1: Écrire les tests en échec**

Couvrir :

- lecture d’un fichier avec lignes vides et commentaires ;
- rejet des lignes invalides sans exposer leur valeur ;
- identifiant stable `google:<sha256-court>` indépendant de l’ordre ;
- rechargement lorsque l’empreinte du fichier change ;
- aucune clé complète dans `repr`, les logs ou les erreurs.

**Step 2: Lancer les tests ciblés**

Run: `python -m pytest tests/test_google_keys.py -q`

Expected: FAIL parce que le module n’existe pas encore.

**Step 3: Implémenter le module minimal**

Exposer une fonction de lecture qui :

- accepte `Path` ou chemin configuré ;
- ignore les lignes vides et celles commençant par `#` ;
- valide le format Google sans journaliser la valeur ;
- calcule l’identifiant avec SHA-256 tronqué ;
- conserve seulement les métadonnées nécessaires à la rotation ;
- supporte une signature `mtime_ns`/taille pour recharger sans relire inutilement.

**Step 4: Relancer les tests**

Run: `python -m pytest tests/test_google_keys.py -q`

Expected: PASS.

---

## Task 2: Ajouter l’état de santé persistant

**Files:**
- Modify: `db.py:50-220` et méthodes de persistance existantes
- Modify: `key_manager.py:20-292`
- Modify: `tests/test_db.py`
- Modify: `tests/test_key_manager.py`

**Step 1: Écrire les tests en échec**

Tester :

- création/migration de la table `key_health` ;
- sauvegarde et relecture de `cooldown_until`, `blocked_reason`, `failure_count` et `last_success_at` ;
- conservation de l’état pour une empreinte inchangée ;
- absence de valeur de clé dans les colonnes et réponses ;
- statut `blocked` visible dans `get_provider_status()`.

**Step 2: Lancer les tests**

Run: `python -m pytest tests/test_db.py tests/test_key_manager.py -q`

Expected: FAIL sur les nouvelles assertions.

**Step 3: Implémenter la migration et les méthodes**

Ajouter une table clé par/provider/fingerprint, avec index sur `cooldown_until`. Ajouter des méthodes upsert/load/delete atomiques. Ne jamais stocker la clé brute.

**Step 4: Étendre `KeyManager`**

- accepter une liste de clés externes pour `google` ;
- utiliser l’empreinte stable comme `key_id` ;
- charger l’état persistant au démarrage ;
- scorer les clés par santé, cooldown, RPM et utilisation ;
- distribuer les requêtes entre les clés plutôt que choisir toujours la même clé ;
- bloquer une clé `401/403` jusqu’à changement de fichier ou déblocage explicite ;
- rafraîchir le cooldown sans transfert d’état lors d’un réordonnancement.

**Step 5: Relancer les tests**

Run: `python -m pytest tests/test_db.py tests/test_key_manager.py -q`

Expected: PASS.

---

## Task 3: Créer l’adaptateur Google natif

**Files:**
- Create: `google_native.py`
- Create: `tests/test_google_native.py`

**Step 1: Écrire les tests en échec**

Couvrir :

- parsing des suffixes `:generateContent`, `:streamGenerateContent` et `:countTokens` ;
- conservation exacte du JSON entrant ;
- construction de l’URL Google `v1beta` ;
- suppression de `Authorization`, `x-goog-api-key`, `x-api-key` et du paramètre `key` reçus ;
- ajout de l’API key choisie uniquement vers l’upstream ;
- classification `429`, quota, `401/403`, timeout et `5xx` ;
- conservation du SSE natif ;
- failover avant le premier octet et comportement défini après émission.

**Step 2: Lancer les tests**

Run: `python -m pytest tests/test_google_native.py -q`

Expected: FAIL puisque l’adaptateur n’existe pas.

**Step 3: Implémenter le module**

Créer une classe ou fonctions séparées du routage OpenAI existant. Le module devra :

- accepter un client `httpx.AsyncClient` injectable ;
- exposer une méthode unary et une méthode stream ;
- filtrer les en-têtes sensibles ;
- passer les paramètres `alt=sse` et les corps sans conversion ;
- capturer le premier chunk avant de retourner un `StreamingResponse` ;
- retourner une erreur Gemini native si toutes les clés sont indisponibles.

**Step 4: Relancer les tests**

Run: `python -m pytest tests/test_google_native.py -q`

Expected: PASS.

---

## Task 4: Brancher les routes et l’authentification locale

**Files:**
- Modify: `main.py:895-1051`, `main.py:1181-1496`, `main.py:1962-1980`
- Modify: `constants.py:116-160`
- Modify: `tests/test_main_api.py`

**Step 1: Écrire les tests en échec**

Ajouter des tests `TestClient` pour :

- `/v1beta/models/{model}:generateContent` ;
- `/v1beta/models/{model}:streamGenerateContent?alt=sse` ;
- `/v1beta/models/{model}:countTokens` ;
- rejet d’un jeton local absent ou incorrect ;
- relais d’une clé upstream mockée ;
- rotation après une réponse `429` ;
- rechargement de `googlekeys.txt` via la configuration.

**Step 2: Lancer les tests**

Run: `python -m pytest tests/test_main_api.py -q`

Expected: FAIL sur les routes absentes.

**Step 3: Implémenter l’initialisation et le rechargement**

- ajouter les paramètres de chemin du fichier, du jeton local, du nombre de tentatives et du cooldown ;
- initialiser le pool Google après le chargement de la configuration ;
- recharger le pool dans `init_state()` et `reload_config()` ;
- faire pointer la source du fichier externe sur `D:\googlewiki\googlekeys.txt` dans la configuration locale ;
- ne jamais modifier `googlekeys.txt`.

**Step 4: Enregistrer les routes**

Ajouter les routes `/v1beta` en conservant les routes `/v1/chat/completions` et `/v1/messages`. Pour la route native :

1. vérifier le jeton local issu de `GEMINI_API_KEY` ou d’un en-tête Bearer ;
2. recharger le fichier si nécessaire ;
3. sélectionner les clés selon l’état de santé ;
4. appeler l’adaptateur natif ;
5. mettre à jour l’état après succès ou erreur.

**Step 5: Vérifier les tests**

Run: `python -m pytest tests/test_main_api.py -q`

Expected: PASS.

---

## Task 5: Ajouter la configuration et la documentation d’exploitation

**Files:**
- Modify: `config.example.yaml:45-65`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md:64-119`

**Step 1: Documenter les paramètres**

Ajouter les paramètres suivants dans l’exemple :

- `google_keys_file` ;
- `google_native_proxy_enabled` ;
- `google_token_env` ;
- `google_max_attempts` ;
- `google_quota_cooldown_minutes` ;
- `google_file_reload_seconds`.

**Step 2: Protéger les secrets**

Ajouter `googlekeys.txt`, `.env` et les fichiers de clé aux exclusions Git. Ne jamais ajouter de valeur réelle à `config.example.yaml`, `.env.example` ou au dashboard.

**Step 3: Documenter le démarrage Gemini**

Documenter les variables persistantes :

- `GEMINI_API_KEY` = jeton local du proxy, jamais une clé Google ;
- `GOOGLE_GEMINI_BASE_URL` = `http://127.0.0.1:47822` ;
- `ROTATOR_GEMINI_TOKEN` = même jeton local lu par le rotator.

Documenter le format une clé par ligne, les commentaires et le rechargement dynamique.

---

## Task 6: Vérifier la rotation de bout en bout

**Files:**
- Modify: `tests/test_google_keys.py`, `tests/test_google_native.py`, `tests/test_main_api.py` si nécessaire

**Step 1: Ajouter les tests de non-fuite**

Vérifier par recherche dans les réponses, logs capturés et objets d’état qu’aucune clé brute n’apparaît. Vérifier que les erreurs Google sont sanitisées avant retour.

**Step 2: Tester la séquence de failover**

Simuler deux clés avec `httpx.MockTransport` :

- première réponse `429` ;
- cooldown persistant de la première empreinte ;
- seconde réponse `200` ;
- requête suivante distribuée selon la politique de santé ;
- aucune clé indisponible ne provoque une boucle infinie.

**Step 3: Tester le streaming**

Simuler une erreur avant le premier chunk puis un flux réussi. Vérifier le type MIME, le format SSE et l’absence de retry après le premier octet.

**Step 4: Lancer la suite complète**

Run: `python -m pytest tests/ -v`

Expected: tous les tests passent.

Run: `python -m compileall -q .`

Expected: code Python compilé sans erreur.

---

## Task 7: Configurer l’environnement Windows de manière persistante

**Files:**
- Aucun fichier de projet modifié automatiquement.

**Step 1: Générer un jeton local aléatoire**

Le générer avec une source cryptographique Windows, sans l’afficher, et le conserver uniquement dans les variables utilisateur Windows `ROTATOR_GEMINI_TOKEN` et `GEMINI_API_KEY`.

**Step 2: Définir les variables**

Via `[Environment]::SetEnvironmentVariable(..., 'User')`, définir :

- `ROTATOR_GEMINI_TOKEN` avec le jeton local ;
- `GEMINI_API_KEY` avec ce même jeton local ;
- `GOOGLE_GEMINI_BASE_URL` avec `http://127.0.0.1:47822`.

Ne jamais exécuter `setx` avec une clé Google en argument visible.

**Step 3: Vérifier sans afficher les secrets**

Ouvrir un nouveau PowerShell et vérifier uniquement :

- présence et longueur minimale des variables ;
- URL du proxy ;
- `gemini --version` ;
- état du rotator sur `http://127.0.0.1:47822`.

Ne pas imprimer la valeur de `GEMINI_API_KEY`.

**Step 4: Tester une commande Gemini**

Lancer `gemini` depuis `D:\googlewiki` avec le rotator démarré, puis vérifier que la requête native traverse le proxy sans exposer de clé dans les logs.

---

## Non-objectifs

- Ne pas convertir les payloads Gemini en OpenAI.
- Ne pas modifier les routes OpenAI/Anthropic existantes.
- Ne pas stocker les clés Google dans SQLite, YAML, PowerShell history ou les logs.
- Ne pas engager de commit Git sans demande explicite de l’utilisateur.
