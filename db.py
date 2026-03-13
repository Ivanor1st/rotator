import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from typing import Any

import aiosqlite
import httpx


class RotatorDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def _fetchone(self, db: aiosqlite.Connection, query: str, params: tuple = ()) -> Any:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def _fetchall(self, db: aiosqlite.Connection, query: str, params: tuple = ()) -> list[Any]:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS key_stats (
                    key_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    requests INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    tokens INTEGER DEFAULT 0,
                    avg_response_ms REAL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_quotas (
                    date TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    requests_used INTEGER DEFAULT 0,
                    PRIMARY KEY (date, provider, model, key_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_history (
                    timestamp TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    key_id TEXT,
                    success INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS override_state (
                    profile TEXT PRIMARY KEY,
                    forced_provider TEXT,
                    blocked_providers TEXT DEFAULT '[]'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_locks (
                    profile TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS suspensions (
                    provider TEXT PRIMARY KEY,
                    until_ts TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    value TEXT,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    days_of_week TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_votes (
                    timestamp TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    model_a TEXT NOT NULL,
                    model_b TEXT NOT NULL,
                    winner TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_performance (
                    date TEXT NOT NULL,
                    model TEXT NOT NULL,
                    avg_ttft_ms REAL DEFAULT 0,
                    avg_total_ms REAL DEFAULT 0,
                    error_rate REAL DEFAULT 0,
                    sample_count INTEGER DEFAULT 0,
                    PRIMARY KEY (date, model)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    token TEXT NOT NULL UNIQUE,
                    daily_limit INTEGER,
                    policy TEXT NOT NULL DEFAULT 'full_access',
                    quota_mode TEXT NOT NULL DEFAULT 'hard_block',
                    rate_limit INTEGER,
                    allowed_profiles TEXT,
                    forced_provider TEXT,
                    max_cost REAL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Add new columns if they don't exist (migration)
            try:
                await db.execute("ALTER TABLE project_keys ADD COLUMN rate_limit INTEGER")
            except:
                pass
            try:
                await db.execute("ALTER TABLE project_keys ADD COLUMN allowed_profiles TEXT")
            except:
                pass
            try:
                await db.execute("ALTER TABLE project_keys ADD COLUMN forced_provider TEXT")
            except:
                pass
            try:
                await db.execute("ALTER TABLE project_keys ADD COLUMN max_cost REAL")
            except:
                pass
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_daily_usage (
                    date TEXT NOT NULL,
                    project_token TEXT NOT NULL,
                    requests_used INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (date, project_token)
                )
                """
            )

            # =================================================================
            # NEW TABLES: Providers, Profiles, Models, Routing, Folders
            # =================================================================

            # Providers table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Profiles table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_custom INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Models table
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    context_window INTEGER,
                    supports_vision INTEGER DEFAULT 0,
                    supports_audio INTEGER DEFAULT 0,
                    is_custom INTEGER DEFAULT 0,
                    exists_on_disk INTEGER DEFAULT 1,
                    last_checked TEXT,
                    folder_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (provider_id) REFERENCES providers(id),
                    FOREIGN KEY (folder_id) REFERENCES model_folders(id)
                )
                """
            )

            # Model routing table (links models to profiles with order)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_routing (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    order_index INTEGER NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    is_suspended INTEGER NOT NULL DEFAULT 0,
                    quota_hint TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id),
                    FOREIGN KEY (model_id) REFERENCES models(id),
                    UNIQUE(profile_id, order_index),
                    UNIQUE(profile_id, model_id)
                )
                """
            )

            # Model folders table (for local models)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS model_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    scan_on_start INTEGER NOT NULL DEFAULT 1,
                    last_scanned TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            await db.commit()

    async def ensure_default_project_key(self) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO project_keys (name, token, daily_limit, policy, quota_mode, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token)
                DO UPDATE SET updated_at = excluded.updated_at
                """,
                ("rotator", "rotator", None, "full_access", "hard_block", 1, now, now),
            )
            await db.commit()

    async def create_project_key(
        self,
        name: str,
        daily_limit: int | None,
        policy: str = "full_access",
        quota_mode: str = "hard_block",
        rate_limit: int | None = None,
        allowed_profiles: str | None = None,
        forced_provider: str | None = None,
        max_cost: float | None = None,
    ) -> dict[str, Any]:
        token = f"proj-{secrets.token_urlsafe(12)}"
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO project_keys (name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, 1, now, now),
            )
            await db.commit()
            project_id = int(cur.lastrowid)
        return {
            "id": project_id,
            "name": name,
            "token": token,
            "daily_limit": daily_limit,
            "policy": policy,
            "quota_mode": quota_mode,
            "rate_limit": rate_limit,
            "allowed_profiles": allowed_profiles,
            "forced_provider": forced_provider,
            "max_cost": max_cost,
            "active": True,
        }

    async def list_project_keys(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT id, name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active, created_at, updated_at
                FROM project_keys
                ORDER BY id
                """,
            )
        return [
            {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "daily_limit": row[3],
                "policy": row[4],
                "quota_mode": row[5],
                "rate_limit": row[6],
                "allowed_profiles": row[7],
                "forced_provider": row[8],
                "max_cost": row[9],
                "active": bool(row[10]),
                "created_at": row[11],
                "updated_at": row[12],
            }
            for row in rows
        ]

    async def resolve_project_key(self, token: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                """
                SELECT id, name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active
                FROM project_keys
                WHERE token = ?
                """,
                (token,),
            )
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "token": row[2],
            "daily_limit": row[3],
            "policy": row[4],
            "quota_mode": row[5],
            "rate_limit": row[6],
            "allowed_profiles": row[7],
            "forced_provider": row[8],
            "max_cost": row[9],
            "active": bool(row[10]),
        }

    def is_profile_allowed(self, project: dict[str, Any], profile: str) -> bool:
        """
        Check if a profile is allowed for a project.

        Logic:
        - If allowed_profiles is set, use it (takes precedence)
        - Otherwise, fall back to policy
        """
        if not project:
            return False

        # Check if project is active
        if not project.get("active", False):
            return False

        # Get allowed profiles and policy
        allowed_profiles = project.get("allowed_profiles")
        policy = project.get("policy", "full_access")

        # If allowed_profiles is set, use it (takes precedence)
        if allowed_profiles:
            allowed_list = [p.strip().lower() for p in allowed_profiles.split(",") if p.strip()]
            return profile.lower() in allowed_list

        # Otherwise, fall back to policy
        policy_to_profiles = {
            "full_access": ["coding", "reasoning", "chat", "long", "vision", "audio", "translate"],
            "coding_only": ["coding"],
            "chat_only": ["chat"],
            "reasoning_only": ["reasoning"],
            "read_only": ["long"],  # read_only maps to long context
        }

        allowed = policy_to_profiles.get(policy, [])
        return profile.lower() in allowed

    async def deactivate_project_key(self, project_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE project_keys SET active = 0, updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(timespec="seconds"), project_id),
            )
            await db.commit()

    async def delete_project_key(self, project_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            # First check if project exists
            row = await self._fetchone(
                db,
                "SELECT id FROM project_keys WHERE id = ?",
                (project_id,),
            )
            if row is None:
                return False
            # Delete the project (cascade will handle project_daily_usage if foreign key exists)
            await db.execute("DELETE FROM project_keys WHERE id = ?", (project_id,))
            await db.commit()
            return True

    async def update_project_key(
        self,
        project_id: int,
        name: str | None = None,
        daily_limit: int | None = None,
        policy: str | None = None,
        quota_mode: str | None = None,
        rate_limit: int | None = None,
        allowed_profiles: str | None = None,
        forced_provider: str | None = None,
        max_cost: float | None = None,
    ) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            # Build update query dynamically
            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if daily_limit is not None:
                updates.append("daily_limit = ?")
                params.append(daily_limit)
            if policy is not None:
                updates.append("policy = ?")
                params.append(policy)
            if quota_mode is not None:
                updates.append("quota_mode = ?")
                params.append(quota_mode)
            if rate_limit is not None:
                updates.append("rate_limit = ?")
                params.append(rate_limit)
            if allowed_profiles is not None:
                updates.append("allowed_profiles = ?")
                params.append(allowed_profiles)
            if forced_provider is not None:
                updates.append("forced_provider = ?")
                params.append(forced_provider)
            if max_cost is not None:
                updates.append("max_cost = ?")
                params.append(max_cost)

            if not updates:
                return None

            updates.append("updated_at = ?")
            params.append(datetime.now(UTC).isoformat(timespec="seconds"))
            params.append(project_id)

            await db.execute(
                f"UPDATE project_keys SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            await db.commit()

            # Return updated project
            row = await self._fetchone(
                db,
                "SELECT id, name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active, created_at, updated_at FROM project_keys WHERE id = ?",
                (project_id,),
            )
            if row is None:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "daily_limit": row[3],
                "policy": row[4],
                "quota_mode": row[5],
                "rate_limit": row[6],
                "allowed_profiles": row[7],
                "forced_provider": row[8],
                "max_cost": row[9],
                "active": bool(row[10]),
                "created_at": row[11],
                "updated_at": row[12],
            }

    async def get_project(self, project_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT id, name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active, created_at, updated_at FROM project_keys WHERE id = ?",
                (project_id,),
            )
            if row is None:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "daily_limit": row[3],
                "policy": row[4],
                "quota_mode": row[5],
                "rate_limit": row[6],
                "allowed_profiles": row[7],
                "forced_provider": row[8],
                "max_cost": row[9],
                "active": bool(row[10]),
                "created_at": row[11],
                "updated_at": row[12],
            }

    async def get_project_by_token(self, token: str) -> dict[str, Any] | None:
        """Get project by token (or name as fallback)."""
        async with aiosqlite.connect(self.db_path) as db:
            # Try to find by token first, then by name
            row = await self._fetchone(
                db,
                "SELECT id, name, token, daily_limit, policy, quota_mode, rate_limit, allowed_profiles, forced_provider, max_cost, active, created_at, updated_at FROM project_keys WHERE token = ? OR name = ?",
                (token, token),
            )
            if row is None:
                return None
            return {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "daily_limit": row[3],
                "policy": row[4],
                "quota_mode": row[5],
                "rate_limit": row[6],
                "allowed_profiles": row[7],
                "forced_provider": row[8],
                "max_cost": row[9],
                "active": bool(row[10]),
                "created_at": row[11],
                "updated_at": row[12],
            }

    async def get_project_usage_history(
        self,
        project_id: int,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get usage history for a project over the last N days."""
        # First get the project token
        project = await self.get_project(project_id)
        if not project:
            return []

        token = project["token"]
        now = datetime.now(UTC)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT date, project_token, requests_used
                FROM project_daily_usage
                WHERE project_token = ? AND date >= ?
                ORDER BY date DESC
                """,
                (token, start_date),
            )

            return [
                {
                    "date": row[0],
                    "requests": row[2] or 0,
                }
                for row in rows
            ]

    async def increment_project_daily_usage(
        self,
        project_token: str,
        amount: int = 1,
        date_str: str | None = None,
    ) -> None:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT requests_used FROM project_daily_usage WHERE date = ? AND project_token = ?",
                (target_date, project_token),
            )
            if row is None:
                await db.execute(
                    """
                    INSERT INTO project_daily_usage (date, project_token, requests_used)
                    VALUES (?, ?, ?)
                    """,
                    (target_date, project_token, amount),
                )
            else:
                await db.execute(
                    """
                    UPDATE project_daily_usage
                    SET requests_used = requests_used + ?
                    WHERE date = ? AND project_token = ?
                    """,
                    (amount, target_date, project_token),
                )
            await db.commit()

    async def get_project_daily_usage(self, project_token: str, date_str: str | None = None) -> int:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT requests_used FROM project_daily_usage WHERE date = ? AND project_token = ?",
                (target_date, project_token),
            )
        return int(row[0]) if row else 0

    async def list_projects_usage_today(self, date_str: str | None = None) -> list[dict[str, Any]]:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT p.id, p.name, p.token, p.daily_limit, p.policy, p.quota_mode, p.active,
                       COALESCE(u.requests_used, 0)
                FROM project_keys p
                LEFT JOIN project_daily_usage u
                  ON u.project_token = p.token AND u.date = ?
                ORDER BY p.id
                """,
                (target_date,),
            )
        return [
            {
                "id": row[0],
                "name": row[1],
                "token": row[2],
                "daily_limit": row[3],
                "policy": row[4],
                "quota_mode": row[5],
                "active": bool(row[6]),
                "requests_today": int(row[7]),
            }
            for row in rows
        ]

    async def upsert_key_stats(
        self,
        key_id: str,
        provider: str,
        success: bool,
        response_ms: float,
        tokens: int = 0,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT requests, errors, tokens, avg_response_ms FROM key_stats WHERE key_id = ?",
                (key_id,),
            )
            if row is None:
                await db.execute(
                    """
                    INSERT INTO key_stats (key_id, provider, requests, errors, tokens, avg_response_ms)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key_id, provider, 1, 0 if success else 1, tokens, response_ms),
                )
            else:
                req, err, tok, avg_ms = row
                next_req = req + 1
                next_err = err + (0 if success else 1)
                next_tok = tok + tokens
                next_avg = ((avg_ms * req) + response_ms) / next_req if req > 0 else response_ms
                await db.execute(
                    """
                    UPDATE key_stats
                    SET requests = ?, errors = ?, tokens = ?, avg_response_ms = ?
                    WHERE key_id = ?
                    """,
                    (next_req, next_err, next_tok, next_avg, key_id),
                )
            await db.commit()

    async def get_all_key_stats(self) -> dict[str, dict[str, Any]]:
        """Get all key statistics as a dictionary keyed by key_id."""
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(db, "SELECT key_id, provider, requests, errors, tokens, avg_response_ms FROM key_stats")
        result = {}
        for key_id, provider, requests, errors, tokens, avg_response_ms in rows:
            # Determine status based on error rate
            error_rate = errors / requests if requests > 0 else 0
            if error_rate > 0.5:
                status = "error"
            elif error_rate > 0.1:
                status = "warning"
            else:
                status = "ok"

            # Extract label from key_id (e.g., "nvidia_1" -> "1" or "ollama_cloud:1" -> "1")
            label = key_id.replace("_", ":").split(":")[-1]

            result[key_id] = {
                "label": label,
                "provider": provider,
                "status": status,
                "requests": requests,
                "errors": errors,
                "tokens": tokens,
                "avg_ms": int(avg_response_ms) if avg_response_ms else 0
            }
        return result

    async def increment_daily_quota(
        self,
        provider: str,
        model: str,
        key_id: str,
        amount: int = 1,
        date_str: str | None = None,
    ) -> None:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                """
                SELECT requests_used FROM daily_quotas
                WHERE date = ? AND provider = ? AND model = ? AND key_id = ?
                """,
                (target_date, provider, model, key_id),
            )
            if row is None:
                await db.execute(
                    """
                    INSERT INTO daily_quotas (date, provider, model, key_id, requests_used)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (target_date, provider, model, key_id, amount),
                )
            else:
                await db.execute(
                    """
                    UPDATE daily_quotas
                    SET requests_used = requests_used + ?
                    WHERE date = ? AND provider = ? AND model = ? AND key_id = ?
                    """,
                    (amount, target_date, provider, model, key_id),
                )
            await db.commit()

    async def load_daily_quota_map(self, date_str: str | None = None) -> dict[str, int]:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                "SELECT provider, model, key_id, requests_used FROM daily_quotas WHERE date = ?",
                (target_date,),
            )
        result: dict[str, int] = {}
        for provider, model, key_id, requests_used in rows:
            result[f"{provider}:{model}:{key_id}"] = requests_used
        return result

    async def add_profile_history(
        self,
        profile: str,
        provider: str,
        model: str,
        key_id: str | None,
        success: bool,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO profile_history (timestamp, profile, provider, model, key_id, success)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(timespec="seconds"),
                    profile,
                    provider,
                    model,
                    key_id,
                    1 if success else 0,
                ),
            )
            await db.commit()

    async def get_profile_requests_today(self, date_str: str | None = None) -> dict[str, int]:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT profile, COUNT(*) FROM profile_history
                WHERE substr(timestamp, 1, 10) = ?
                GROUP BY profile
                """,
                (target_date,),
            )
        return {profile: count for profile, count in rows}

    async def get_recent_sessions(
        self,
        limit: int = 200,
        profile: str | None = None,
        provider: str | None = None,
    ) -> list[dict]:
        """Return recent profile_history rows for the Sessions tab."""
        async with aiosqlite.connect(self.db_path) as db:
            conditions = []
            params: list = []
            if profile:
                conditions.append("profile = ?")
                params.append(profile)
            if provider:
                conditions.append("provider = ?")
                params.append(provider)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(min(limit, 500))
            rows = await self._fetchall(
                db,
                f"""
                SELECT timestamp, profile, provider, model, key_id, success
                FROM profile_history
                {where}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                tuple(params),
            )
        return [
            {
                "timestamp": r[0],
                "profile": r[1],
                "provider": r[2],
                "model": r[3],
                "key_id": r[4],
                "success": bool(r[5]),
            }
            for r in rows
        ]

    async def reset_daily_quotas(self, date_str: str | None = None) -> None:
        target_date = date_str or datetime.now(UTC).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM daily_quotas WHERE date = ?", (target_date,))
            await db.commit()

    async def save_override(
        self,
        profile: str,
        forced_provider: str | None,
        blocked_providers: list[str],
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO override_state (profile, forced_provider, blocked_providers)
                VALUES (?, ?, ?)
                ON CONFLICT(profile)
                DO UPDATE SET forced_provider = excluded.forced_provider,
                              blocked_providers = excluded.blocked_providers
                """,
                (profile, forced_provider, json.dumps(blocked_providers)),
            )
            await db.commit()

    async def load_overrides(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                "SELECT profile, forced_provider, blocked_providers FROM override_state"
            )
        data: dict[str, Any] = {"profiles": {}, "blocked": []}
        for profile, forced_provider, blocked_json in rows:
            blocked = json.loads(blocked_json or "[]")
            if profile == "_global":
                data["blocked"] = blocked
            else:
                data["profiles"][profile] = forced_provider or "auto"
        return data

    async def set_app_state(self, key: str, value: Any) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO app_state (key, value)
                VALUES (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value
                """,
                (key, json.dumps(value)),
            )
            await db.commit()

    async def get_app_state(self, key: str, default: Any = None) -> Any:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(db, "SELECT value FROM app_state WHERE key = ?", (key,))
        if not row:
            return default
        return json.loads(row[0])

    async def save_model_lock(self, profile: str, model: str, provider: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO model_locks (profile, model, provider, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile)
                DO UPDATE SET model = excluded.model,
                              provider = excluded.provider,
                              created_at = excluded.created_at
                """,
                (profile, model, provider, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            await db.commit()

    async def delete_model_lock(self, profile: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM model_locks WHERE profile = ?", (profile,))
            await db.commit()

    async def load_model_locks(self) -> dict[str, dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(db, "SELECT profile, model, provider FROM model_locks")
        return {profile: {"model": model, "provider": provider} for profile, model, provider in rows}

    async def save_suspension(self, provider: str, until_ts: str | None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO suspensions (provider, until_ts, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(provider)
                DO UPDATE SET until_ts = excluded.until_ts
                """,
                (provider, until_ts, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            await db.commit()

    async def delete_suspension(self, provider: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM suspensions WHERE provider = ?", (provider,))
            await db.commit()

    async def load_suspensions(self) -> dict[str, str | None]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(db, "SELECT provider, until_ts FROM suspensions")
        return {provider: until_ts for provider, until_ts in rows}

    async def list_presets(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                "SELECT id, name, description, data_json, created_at, updated_at FROM presets ORDER BY id"
            )
        results = []
        for preset_id, name, description, data_json, created_at, updated_at in rows:
            results.append(
                {
                    "id": preset_id,
                    "name": name,
                    "description": description,
                    "data": json.loads(data_json),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )
        return results

    async def save_preset(self, name: str, description: str, data: dict[str, Any], preset_id: int | None = None) -> int:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            if preset_id is None:
                cur = await db.execute(
                    """
                    INSERT INTO presets (name, description, data_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, description, json.dumps(data), now, now),
                )
                await db.commit()
                return int(cur.lastrowid)
            await db.execute(
                """
                UPDATE presets
                SET name = ?, description = ?, data_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, description, json.dumps(data), now, preset_id),
            )
            await db.commit()
            return preset_id

    async def delete_preset(self, preset_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
            await db.commit()

    async def list_schedules(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT id, name, action, target, value, time_start, time_end, days_of_week, active
                FROM schedules
                ORDER BY id
                """
            )
        return [
            {
                "id": row[0],
                "name": row[1],
                "action": row[2],
                "target": row[3],
                "value": row[4],
                "time_start": row[5],
                "time_end": row[6],
                "days_of_week": row[7],
                "active": bool(row[8]),
            }
            for row in rows
        ]

    async def save_schedule(self, data: dict[str, Any], schedule_id: int | None = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            if schedule_id is None:
                cur = await db.execute(
                    """
                    INSERT INTO schedules (name, action, target, value, time_start, time_end, days_of_week, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["name"],
                        data["action"],
                        data["target"],
                        data.get("value"),
                        data["time_start"],
                        data["time_end"],
                        data["days_of_week"],
                        1 if data.get("active", True) else 0,
                    ),
                )
                await db.commit()
                return int(cur.lastrowid)
            await db.execute(
                """
                UPDATE schedules
                SET name = ?, action = ?, target = ?, value = ?, time_start = ?, time_end = ?, days_of_week = ?, active = ?
                WHERE id = ?
                """,
                (
                    data["name"],
                    data["action"],
                    data["target"],
                    data.get("value"),
                    data["time_start"],
                    data["time_end"],
                    data["days_of_week"],
                    1 if data.get("active", True) else 0,
                    schedule_id,
                ),
            )
            await db.commit()
            return schedule_id

    async def delete_schedule(self, schedule_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            await db.commit()

    async def add_model_vote(
        self,
        profile: str,
        model_a: str,
        model_b: str,
        winner: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO model_votes (timestamp, profile, model_a, model_b, winner)
                VALUES (?, ?, ?, ?, ?)
                """,
                (datetime.now(UTC).isoformat(timespec="seconds"), profile, model_a, model_b, winner),
            )
            await db.commit()

    async def upsert_model_performance(
        self,
        date_str: str,
        model: str,
        avg_ttft_ms: float,
        avg_total_ms: float,
        error_rate: float,
        sample_count: int,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO model_performance (date, model, avg_ttft_ms, avg_total_ms, error_rate, sample_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, model)
                DO UPDATE SET avg_ttft_ms = excluded.avg_ttft_ms,
                              avg_total_ms = excluded.avg_total_ms,
                              error_rate = excluded.error_rate,
                              sample_count = excluded.sample_count
                """,
                (date_str, model, avg_ttft_ms, avg_total_ms, error_rate, sample_count),
            )
            await db.commit()

    async def list_model_performance(self, date_str: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                "SELECT model, avg_ttft_ms, avg_total_ms, error_rate, sample_count FROM model_performance WHERE date = ?",
                (date_str,),
            )
        return [
            {
                "model": row[0],
                "avg_ttft_ms": row[1],
                "avg_total_ms": row[2],
                "error_rate": row[3],
                "sample_count": row[4],
            }
            for row in rows
        ]

    async def create_backup_snapshot(self, backup_dir: str) -> dict[str, Any]:
        source = Path(self.db_path)
        if not source.exists():
            raise FileNotFoundError("Database file not found")

        root = Path(backup_dir)
        root.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        target = root / f"rotator_{stamp}.db"
        await asyncio.to_thread(shutil.copy2, source, target)

        return {
            "name": target.name,
            "path": str(target),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    async def list_backups(self, backup_dir: str) -> list[dict[str, Any]]:
        root = Path(backup_dir)
        if not root.exists():
            return []
        files = sorted(root.glob("rotator_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [
            {
                "name": item.name,
                "path": str(item),
                "size_bytes": item.stat().st_size,
                "created_at": datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat(timespec="seconds"),
            }
            for item in files
        ]

    async def reset_all_data(self) -> dict[str, int]:
        tables = [
            "key_stats",
            "daily_quotas",
            "profile_history",
            "override_state",
            "app_state",
            "model_locks",
            "suspensions",
            "presets",
            "schedules",
            "model_votes",
            "model_performance",
            "project_daily_usage",
            "project_keys",
        ]
        async with aiosqlite.connect(self.db_path) as db:
            for table in tables:
                await db.execute(f"DELETE FROM {table}")  # SAFETY: table names from hardcoded internal list, no user input
            await db.commit()

        await self.ensure_default_project_key()
        return {"tables_cleared": len(tables)}

    async def purge_data_before(self, before_date: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        date_cutoff = before_date.strip()

        targets = [
            ("daily_quotas", "date"),
            ("profile_history", "substr(timestamp, 1, 10)"),
            ("model_votes", "substr(timestamp, 1, 10)"),
            ("model_performance", "date"),
            ("project_daily_usage", "date"),
        ]

        async with aiosqlite.connect(self.db_path) as db:
            for table, field_expr in targets:
                await db.execute(f"DELETE FROM {table} WHERE {field_expr} < ?", (date_cutoff,))  # SAFETY: table/field names from hardcoded internal list, no user input
                row = await self._fetchone(db, "SELECT changes()")
                deleted[table] = int(row[0]) if row else 0
            await db.commit()

        deleted["total"] = sum(v for k, v in deleted.items() if k != "total")
        return deleted

    async def restore_backup_by_name(self, backup_dir: str, backup_name: str) -> dict[str, Any]:
        root = Path(backup_dir)
        source = root / backup_name
        if not source.exists() or not source.is_file():
            raise FileNotFoundError("Backup not found")

        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, source, db_file)

        return {
            "name": source.name,
            "restored_to": str(db_file),
            "restored_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    async def restore_latest_backup(self, backup_dir: str) -> dict[str, Any] | None:
        items = await self.list_backups(backup_dir)
        if not items:
            return None
        latest_name = str(items[0]["name"])
        return await self.restore_backup_by_name(backup_dir, latest_name)

    async def delete_backup_by_name(self, backup_dir: str, backup_name: str) -> bool:
        root = Path(backup_dir)
        target = root / backup_name
        if not target.exists() or not target.is_file():
            return False
        await asyncio.to_thread(target.unlink)
        return True

    # =================================================================
    # SEED FUNCTIONS: Initial data for providers, profiles, models
    # =================================================================

    async def seed_providers(self) -> None:
        """Seed the default providers if they don't exist."""
        now = datetime.now(UTC).isoformat(timespec="seconds")

        providers_data = [
            ("ollama_cloud", "Ollama Cloud", "https://cloud.ollama.ai", 10),
            ("local", "Local (Ollama)", "http://localhost:11434", 20),
            ("nvidia", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", 30),
            ("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", 40),
            ("google", "Google AI", "https://generativelanguage.googleapis.com/v1beta/openai", 50),
            ("openai", "OpenAI", "https://api.openai.com/v1", 60),
            ("anthropic", "Anthropic", "https://api.anthropic.com", 70),
            ("custom", "Custom", "", 80),
        ]

        async with aiosqlite.connect(self.db_path) as db:
            for name, display_name, base_url, priority in providers_data:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO providers (name, display_name, base_url, is_active, priority, created_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (name, display_name, base_url, priority, now),
                )
            await db.commit()

    async def seed_profiles(self) -> None:
        """Seed the default profiles if they don't exist."""
        now = datetime.now(UTC).isoformat(timespec="seconds")

        profiles_data = [
            ("coding", "Coding", "Code, debug, implementation"),
            ("reasoning", "Reasoning", "Explanations, analysis, math"),
            ("chat", "Chat", "General conversation"),
            ("long", "Long Context", "Large context / documents"),
            ("vision", "Vision", "Image analysis"),
            ("audio", "Audio", "Audio / transcription"),
            ("translate", "Translate", "Translation"),
        ]

        async with aiosqlite.connect(self.db_path) as db:
            for name, display_name, description in profiles_data:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO profiles (name, display_name, description, is_active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (name, display_name, description, now),
                )
            await db.commit()

    async def seed_default_models_and_routing(self) -> None:
        """Seed default models and routing chains."""
        now = datetime.now(UTC).isoformat(timespec="seconds")

        # Default routing chains (from router.py)
        default_routing = {
            "coding": [
                # Ollama Cloud - best for coding
                ("ollama_cloud", "minimax-m2.5:cloud", 1),
                ("ollama_cloud", "qwen3-coder-next:cloud", 2),
                # NVIDIA - top coding models
                ("nvidia", "qwen/qwen3-coder-480b-a35b-instruct", 3),
                ("nvidia", "z-ai/glm5", 4),
                # OpenRouter - best free coding models (Qwen3 Coder is 7/7!)
                ("openrouter", "qwen/qwen3-coder:free", 5),
                ("openrouter", "openai/gpt-oss-120b:free", 6),
                ("openrouter", "deepseek/deepseek-r1-0528:free", 7),
                # Google
                ("google", "gemma-3-27b-it", 8),
                ("google", "gemini-2.5-flash", 9),
                # LOCAL models will be dynamically resolved at runtime
            ],
            "reasoning": [
                # Ollama Cloud - best reasoning
                ("ollama_cloud", "glm-5:cloud", 1),
                ("ollama_cloud", "minimax-m2.5:cloud", 2),
                # NVIDIA - top reasoning models
                ("nvidia", "qwen/qwen3-next-80b-a3b-thinking", 3),
                ("nvidia", "deepseek-ai/deepseek-v3.2", 4),
                ("nvidia", "openai/gpt-oss-120b", 5),
                # OpenRouter - best free reasoning models (DeepSeek R1 is 7/7!)
                ("openrouter", "deepseek/deepseek-r1-0528:free", 6),
                ("openrouter", "qwen/qwen3-vl-235b-a22b-thinking", 7),
                ("openrouter", "qwen/qwen3-next-80b-a3b-instruct:free", 8),
                ("openrouter", "nousresearch/hermes-3-llama-3.1-405b:free", 9),
                # Google
                ("google", "gemma-3-27b-it", 10),
                ("google", "gemini-2.5-flash", 11),
                # LOCAL models will be dynamically resolved at runtime
            ],
            "chat": [
                # Ollama Cloud - best chat models
                ("ollama_cloud", "glm-5:cloud", 1),
                ("ollama_cloud", "minimax-m2.5:cloud", 2),
                ("ollama_cloud", "qwen3.5:397b-cloud", 3),
                # NVIDIA
                ("nvidia", "minimaxai/minimax-m2.1", 4),
                # OpenRouter - best free chat models (Trinity is 7/7, Dolphin is 7/7!)
                ("openrouter", "arcee-ai/trinity-large-preview:free", 5),
                ("openrouter", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free", 6),
                ("openrouter", "google/gemma-3-27b-it:free", 7),
                ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", 8),
                ("openrouter", "mistralai/mistral-small-3.1-24b-instruct:free", 9),
                # Google
                ("google", "gemma-3-27b-it", 10),
                ("google", "gemini-2.5-flash", 11),
                # LOCAL models will be dynamically resolved at runtime
            ],
            "long": [
                # Ollama Cloud - best long context (ONLY models with cloud variants!)
                ("ollama_cloud", "qwen3-next:80b-cloud", 1),  # Has cloud variant!
                ("ollama_cloud", "qwen3.5:397b-cloud", 2),  # 256K context
                ("ollama_cloud", "kimi-k2.5:cloud", 3),  # Large context
                ("ollama_cloud", "deepseek-v3.2:cloud", 4),  # DeepSeek flagship
                # NVIDIA - excellent long context
                ("nvidia", "nvidia/nemotron-3-nano-30b-a3b", 5),  # 1M context!
                ("nvidia", "deepseek-ai/deepseek-v3.2", 6),  # 256K
                ("nvidia", "meta/llama-4-maverick-17b-128e-instruct", 7),
                # OpenRouter - free options
                ("openrouter", "qwen/qwen3-next-80b-a3b-instruct:free", 8),  # 262K
                ("openrouter", "stepfun/step-3.5-flash:free", 9),  # 256K
                # Google - best free tier
                ("google", "gemini-2.5-flash", 10),  # 1M!
            ],
            "vision": [
                # Ollama Cloud - ONLY models with cloud variants!
                ("ollama_cloud", "qwen3-vl:235b-cloud", 1),  # Best VLM, 235B!
                ("ollama_cloud", "kimi-k2.5:cloud", 2),  # Native multimodal agentic
                ("ollama_cloud", "gemma3:27b-cloud", 3),  # Google's flagship
                ("ollama_cloud", "qwen3.5:397b-cloud", 4),  # Best overall?
                ("ollama_cloud", "mistral-large-3:675b-cloud", 5),  # Mistral flagship
                ("ollama_cloud", "ministral-3:14b-cloud", 6),  # Good smaller option
                # OpenRouter - free vision models
                ("openrouter", "qwen/qwen3-vl-235b-a22b-thinking", 7),
                ("openrouter", "qwen/qwen3-vl-30b-a3b-thinking", 8),
                # NVIDIA - vision models
                ("nvidia", "meta/llama-3.2-90b-vision-instruct", 9),
                ("nvidia", "moonshotai/kimi-k2.5", 10),
                # Google - free tier
                ("google", "gemini-2.5-flash", 11),
                # LOCAL models will be dynamically resolved at runtime
            ],
            "audio": [
                ("google", "gemini-2.5-flash-native-audio", 1),
            ],
            "translate": [
                # LOCAL models will be dynamically resolved at runtime
                ("openrouter", "openrouter/free", 2),
            ],
        }

        async with aiosqlite.connect(self.db_path) as db:
            # First, get provider IDs
            provider_map = {}
            rows = await self._fetchall(db, "SELECT id, name FROM providers")
            for row in rows:
                provider_map[row[1]] = row[0]

            # Get profile IDs
            profile_map = {}
            rows = await self._fetchall(db, "SELECT id, name FROM profiles")
            for row in rows:
                profile_map[row[1]] = row[0]

            # Insert models and routing
            for profile_name, models in default_routing.items():
                profile_id = profile_map.get(profile_name)
                if not profile_id:
                    continue

                for provider_name, model_name, order in models:
                    # Skip local models - they will be seeded via scan_and_seed_ollama_models
                    if provider_name == "local":
                        continue

                    provider_id = provider_map.get(provider_name)
                    if not provider_id:
                        continue

                    # Insert model if not exists
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO models (provider_id, name, is_custom, created_at)
                        VALUES (?, ?, 0, ?)
                        """,
                        (provider_id, model_name, now),
                    )

                    # Get model ID
                    model_row = await self._fetchone(
                        db,
                        "SELECT id FROM models WHERE provider_id = ? AND name = ?",
                        (provider_id, model_name),
                    )
                    if not model_row:
                        continue

                    model_id = model_row[0]

                    # Insert routing (is_default = 1 for default models)
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO model_routing (profile_id, model_id, order_index, is_default, is_suspended, created_at)
                        VALUES (?, ?, ?, 1, 0, ?)
                        """,
                        (profile_id, model_id, order, now),
                    )

            await db.commit()

    async def scan_and_seed_ollama_models(self) -> dict[str, Any]:
        """Scan Ollama API for installed models and add them to the database."""
        result = {"added": 0, "skipped": 0, "errors": []}
        now = datetime.now(UTC).isoformat(timespec="seconds")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code != 200:
                    return {"error": f"Ollama returned {response.status_code}"}
                ollama_models = response.json().get("models", [])
        except httpx.ConnectError:
            return {"error": "Ollama not running on localhost:11434"}
        except Exception as e:
            return {"error": str(e)}

        if not ollama_models:
            return {"message": "No models found in Ollama"}

        async with aiosqlite.connect(self.db_path) as db:
            # Get local provider ID
            provider_row = await self._fetchone(
                db,
                "SELECT id FROM providers WHERE name = ?",
                ("local",),
            )
            if not provider_row:
                result["errors"].append("Local provider not found in database")
                return result

            local_provider_id = provider_row[0]

            # Get coding profile ID
            coding_profile_row = await self._fetchone(
                db,
                "SELECT id FROM profiles WHERE name = ?",
                ("coding",),
            )
            coding_profile_id = coding_profile_row[0] if coding_profile_row else None

            for ollama_model in ollama_models:
                model_name = ollama_model.get("name", "")
                if not model_name:
                    continue

                # Check if model already exists
                existing = await self._fetchone(
                    db,
                    "SELECT id FROM models WHERE provider_id = ? AND name = ?",
                    (local_provider_id, model_name),
                )

                model_id = None
                if existing:
                    # Update exists_on_disk flag
                    await db.execute(
                        "UPDATE models SET exists_on_disk = 1, last_checked = ? WHERE id = ?",
                        (now, existing[0]),
                    )
                    model_id = existing[0]
                    result["skipped"] += 1
                else:
                    # Insert new model
                    cursor = await db.execute(
                        """
                        INSERT INTO models (provider_id, name, is_custom, exists_on_disk, last_checked, created_at)
                        VALUES (?, ?, 0, 1, ?, ?)
                        """,
                        (local_provider_id, model_name, now, now),
                    )
                    model_id = cursor.lastrowid
                    result["added"] += 1

                # Add to coding profile routing if not already there
                if model_id and coding_profile_id:
                    routing_exists = await self._fetchone(
                        db,
                        "SELECT id FROM model_routing WHERE profile_id = ? AND model_id = ?",
                        (coding_profile_id, model_id),
                    )
                    if not routing_exists:
                        # Get max order_index
                        order_row = await self._fetchone(
                            db,
                            "SELECT MAX(order_index) FROM model_routing WHERE profile_id = ?",
                            (coding_profile_id,),
                        )
                        order_index = (order_row[0] or 0) + 1

                        await db.execute(
                            """
                            INSERT INTO model_routing (profile_id, model_id, order_index, is_default, is_suspended, created_at)
                            VALUES (?, ?, ?, 0, 0, ?)
                            """,
                            (coding_profile_id, model_id, order_index, now),
                        )

            await db.commit()

        return result

    async def seed_default_local_folder(self) -> None:
        """Seed the default local model folder."""
        import os

        now = datetime.now(UTC).isoformat(timespec="seconds")

        # Default Ollama folder on Windows
        default_folder = os.path.join(os.environ.get("USERPROFILE", ""), ".ollama", "models")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO model_folders (path, is_active, scan_on_start, created_at)
                VALUES (?, 1, 1, ?)
                """,
                (default_folder, now),
            )
            await db.commit()

    async def seed_all(self) -> dict[str, int]:
        """Seed all default data. Returns count of seeded items."""
        await self.seed_providers()
        await self.seed_profiles()
        await self.seed_default_models_and_routing()
        await self.seed_default_local_folder()

        # Scan Ollama for real local models and add them to the database
        ollama_result = await self.scan_and_seed_ollama_models()

        # Return counts
        async with aiosqlite.connect(self.db_path) as db:
            providers_count = await self._fetchone(db, "SELECT COUNT(*) FROM providers")
            profiles_count = await self._fetchone(db, "SELECT COUNT(*) FROM profiles")
            models_count = await self._fetchone(db, "SELECT COUNT(*) FROM models")
            routing_count = await self._fetchone(db, "SELECT COUNT(*) FROM model_routing")
            folders_count = await self._fetchone(db, "SELECT COUNT(*) FROM model_folders")

        return {
            "providers": providers_count[0] if providers_count else 0,
            "profiles": profiles_count[0] if profiles_count else 0,
            "models": models_count[0] if models_count else 0,
            "routing": routing_count[0] if routing_count else 0,
            "folders": folders_count[0] if folders_count else 0,
        }

    async def is_db_seeded(self) -> bool:
        """Check if the database has been seeded with initial data."""
        async with aiosqlite.connect(self.db_path) as db:
            providers = await self._fetchone(db, "SELECT COUNT(*) FROM providers")
            profiles = await self._fetchone(db, "SELECT COUNT(*) FROM profiles")

        return (providers and providers[0] > 0) and (profiles and profiles[0] > 0)

    # =================================================================
    # CRUD: Providers
    # =================================================================

    async def list_providers(self, active_only: bool = True) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT id, name, display_name, base_url, is_active, priority, created_at FROM providers"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY priority ASC"

            rows = await self._fetchall(db, query)

        return [
            {
                "id": row[0],
                "name": row[1],
                "display_name": row[2],
                "base_url": row[3],
                "is_active": bool(row[4]),
                "priority": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    async def get_provider_by_name(self, name: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT id, name, display_name, base_url, is_active, priority, created_at FROM providers WHERE name = ?",
                (name,),
            )

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "base_url": row[3],
            "is_active": bool(row[4]),
            "priority": row[5],
            "created_at": row[6],
        }

    async def get_provider_by_id(self, provider_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT id, name, display_name, base_url, is_active, priority, created_at FROM providers WHERE id = ?",
                (provider_id,),
            )

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "base_url": row[3],
            "is_active": bool(row[4]),
            "priority": row[5],
            "created_at": row[6],
        }

    async def create_provider(
        self,
        name: str,
        display_name: str,
        base_url: str,
        priority: int = 50,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO providers (name, display_name, base_url, is_active, priority, created_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (name, display_name, base_url, priority, now),
            )
            await db.commit()
            provider_id = int(cur.lastrowid)

        return {
            "id": provider_id,
            "name": name,
            "display_name": display_name,
            "base_url": base_url,
            "is_active": True,
            "priority": priority,
            "created_at": now,
        }

    async def update_provider(self, provider_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update provider. Only custom providers can be updated."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if provider exists and is custom
            row = await self._fetchone(db, "SELECT name FROM providers WHERE id = ?", (provider_id,))
            if not row:
                return None

            # Build update query
            updates = []
            params = []

            if "display_name" in data:
                updates.append("display_name = ?")
                params.append(data["display_name"])
            if "base_url" in data:
                updates.append("base_url = ?")
                params.append(data["base_url"])
            if "is_active" in data:
                updates.append("is_active = ?")
                params.append(1 if data["is_active"] else 0)
            if "priority" in data:
                updates.append("priority = ?")
                params.append(data["priority"])

            if not updates:
                return await self.get_provider_by_id(provider_id)

            params.append(provider_id)
            await db.execute(f"UPDATE providers SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()

        return await self.get_provider_by_id(provider_id)

    async def delete_provider(self, provider_id: int) -> bool:
        """Delete a provider. Only custom providers can be deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if provider is custom (not in default list)
            row = await self._fetchone(db, "SELECT name FROM providers WHERE id = ?", (provider_id,))
            if not row:
                return False

            # Don't delete default providers
            default_providers = ["ollama_cloud", "local", "nvidia", "openrouter", "google", "openai", "anthropic", "custom"]
            if row[0] in default_providers:
                return False

            await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
            await db.commit()

        return True

    # =================================================================
    # CRUD: Profiles
    # =================================================================

    async def list_profiles(self, active_only: bool = True) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT id, name, display_name, description, is_active, is_custom, created_at FROM profiles"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY id ASC"

            rows = await self._fetchall(db, query)

        return [
            {
                "id": row[0],
                "name": row[1],
                "display_name": row[2],
                "description": row[3],
                "is_active": bool(row[4]),
                "is_custom": bool(row[5]) if row[5] is not None else False,
                "created_at": row[6],
            }
            for row in rows
        ]

    async def get_profile_by_name(self, name: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT id, name, display_name, description, is_active, created_at FROM profiles WHERE name = ?",
                (name,),
            )

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "description": row[3],
            "is_active": bool(row[4]),
            "created_at": row[5],
        }

    async def get_profile_by_id(self, profile_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                "SELECT id, name, display_name, description, is_active, is_custom, created_at FROM profiles WHERE id = ?",
                (profile_id,),
            )

        if not row:
            return None

        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "description": row[3],
            "is_active": bool(row[4]),
            "is_custom": bool(row[5]) if row[5] is not None else False,
            "created_at": row[6],
        }

    async def migrate_add_is_custom_column(self) -> None:
        """Add is_custom column to profiles table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if column exists
            rows = await self._fetchall(db, "PRAGMA table_info(profiles)")
            columns = [r[1] for r in rows] if rows else []
            if "is_custom" not in columns:
                await db.execute("ALTER TABLE profiles ADD COLUMN is_custom INTEGER DEFAULT 0")
                await db.commit()

    async def create_custom_profile(self, name: str, description: str, models: list[dict[str, Any]]) -> dict[str, Any]:
        """Create a custom profile in the database with routing chain."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat(timespec="seconds")

        async with aiosqlite.connect(self.db_path) as db:
            # Insert profile
            cur = await db.execute(
                """
                INSERT INTO profiles (name, display_name, description, is_active, is_custom, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, name.replace("-", " ").title(), description, 1, 1, now),
            )
            profile_id = cur.lastrowid

            # Add models to routing chain
            for idx, model_info in enumerate(models):
                provider_name = model_info.get("provider", "")
                model_name = model_info.get("model", "")

                if not provider_name or not model_name:
                    continue

                # Get provider ID
                provider_row = await self._fetchone(
                    db,
                    "SELECT id FROM providers WHERE name = ?",
                    (provider_name,),
                )
                if not provider_row:
                    continue
                provider_id = provider_row[0]

                # Get model ID
                model_row = await self._fetchone(
                    db,
                    "SELECT id FROM models WHERE provider_id = ? AND name = ?",
                    (provider_id, model_name),
                )
                if not model_row:
                    continue
                model_id = model_row[0]

                # Add to routing chain
                await db.execute(
                    """
                    INSERT INTO model_routing (profile_id, model_id, order_index, is_default, is_suspended, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (profile_id, model_id, idx + 1, 0, 0, now),
                )

            await db.commit()

        return {
            "id": profile_id,
            "name": name,
            "display_name": name.replace("-", " ").title(),
            "description": description,
            "is_active": True,
            "is_custom": True,
            "models": models,
        }

    async def get_custom_profiles(self) -> list[dict[str, Any]]:
        """Get all custom profiles from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                "SELECT id, name, display_name, description, is_active, created_at FROM profiles WHERE is_custom = 1 ORDER BY id ASC",
            )

        profiles = []
        for row in rows:
            profile_id = row[0]
            # Get routing chain for this profile
            routing = await self.get_profile_routing_chain(row[1])
            # Convert routing_chain to models format for frontend compatibility
            models = [{"model": r["model"], "provider": r["provider"]} for r in routing]
            
            profiles.append({
                "id": profile_id,
                "name": row[1],
                "display_name": row[2],
                "description": row[3],
                "is_active": bool(row[4]),
                "is_custom": True,
                "created_at": row[5],
                "routing_chain": routing,
                "models": models,  # Frontend expects this format
            })

        return profiles

    async def delete_custom_profile(self, name: str) -> bool:
        """Delete a custom profile from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get profile ID
            profile_row = await self._fetchone(
                db,
                "SELECT id FROM profiles WHERE name = ? AND is_custom = 1",
                (name,),
            )
            if not profile_row:
                return False

            profile_id = profile_row[0]

            # Delete from routing chain first
            await db.execute(
                "DELETE FROM model_routing WHERE profile_id = ?",
                (profile_id,),
            )

            # Delete profile
            await db.execute(
                "DELETE FROM profiles WHERE id = ?",
                (profile_id,),
            )

            await db.commit()

        return True

    async def get_profile_routing_chain(self, profile_name: str) -> list[dict[str, Any]]:
        """Get the routing chain for a profile, ordered by order_index."""
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT mr.order_index, m.name, p.name as provider_name, mr.is_default, mr.is_suspended, mr.quota_hint
                FROM model_routing mr
                JOIN models m ON mr.model_id = m.id
                JOIN providers p ON m.provider_id = p.id
                JOIN profiles pr ON mr.profile_id = pr.id
                WHERE pr.name = ? AND mr.is_suspended = 0
                ORDER BY mr.order_index ASC
                """,
                (profile_name,),
            )

        return [
            {
                "order": row[0],
                "model": row[1],
                "provider": row[2],
                "is_default": bool(row[3]),
                "is_suspended": bool(row[4]),
                "quota_hint": row[5],
            }
            for row in rows
        ]

    # =================================================================
    # CRUD: Models
    # =================================================================

    async def list_models(self, provider_id: int | None = None) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            query = """
                SELECT m.id, m.provider_id, p.name as provider_name, m.name, m.display_name,
                       m.context_window, m.supports_vision, m.supports_audio, m.is_custom,
                       m.exists_on_disk, m.folder_id, m.created_at
                FROM models m
                JOIN providers p ON m.provider_id = p.id
            """
            params = []
            if provider_id:
                query += " WHERE m.provider_id = ?"
                params.append(provider_id)

            rows = await self._fetchall(db, query, tuple(params) if params else ())

        return [
            {
                "id": row[0],
                "provider_id": row[1],
                "provider_name": row[2],
                "name": row[3],
                "display_name": row[4],
                "context_window": row[5],
                "supports_vision": bool(row[6]),
                "supports_audio": bool(row[7]),
                "is_custom": bool(row[8]),
                "exists_on_disk": bool(row[9]),
                "folder_id": row[10],
                "created_at": row[11],
            }
            for row in rows
        ]

    async def get_model_by_id(self, model_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                """
                SELECT m.id, m.provider_id, p.name as provider_name, m.name, m.display_name,
                       m.context_window, m.supports_vision, m.supports_audio, m.is_custom,
                       m.exists_on_disk, m.folder_id, m.created_at
                FROM models m
                JOIN providers p ON m.provider_id = p.id
                WHERE m.id = ?
                """,
                (model_id,),
            )

        if not row:
            return None

        return {
            "id": row[0],
            "provider_id": row[1],
            "provider_name": row[2],
            "name": row[3],
            "display_name": row[4],
            "context_window": row[5],
            "supports_vision": bool(row[6]),
            "supports_audio": bool(row[7]),
            "is_custom": bool(row[8]),
            "exists_on_disk": bool(row[9]),
            "folder_id": row[10],
            "created_at": row[11],
        }

    async def create_model(
        self,
        provider_id: int,
        name: str,
        display_name: str | None = None,
        is_custom: bool = True,
        context_window: int | None = None,
        supports_vision: bool = False,
        supports_audio: bool = False,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO models (provider_id, name, display_name, is_custom, context_window, supports_vision, supports_audio, exists_on_disk, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (provider_id, name, display_name or name, is_custom, context_window, supports_vision, supports_audio, now),
            )
            await db.commit()
            model_id = int(cur.lastrowid)

        return await self.get_model_by_id(model_id)

    async def add_model_to_profile(
        self,
        model_id: int,
        profile_id: int,
        order_index: int | None = None,
    ) -> dict[str, Any]:
        """Add a model to a profile's routing chain."""
        now = datetime.now(UTC).isoformat(timespec="seconds")

        async with aiosqlite.connect(self.db_path) as db:
            # Get max order_index if not specified
            if order_index is None:
                row = await self._fetchone(
                    db,
                    "SELECT MAX(order_index) FROM model_routing WHERE profile_id = ?",
                    (profile_id,),
                )
                order_index = (row[0] or 0) + 1

            # Check if model is default
            is_default_row = await self._fetchone(
                db,
                "SELECT is_custom FROM models WHERE id = ?",
                (model_id,),
            )
            is_default = 0 if (is_default_row and is_default_row[0]) else 0

            await db.execute(
                """
                INSERT OR IGNORE INTO model_routing (profile_id, model_id, order_index, is_default, is_suspended, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (profile_id, model_id, order_index, is_default, now),
            )
            await db.commit()

        return {
            "model_id": model_id,
            "profile_id": profile_id,
            "order_index": order_index,
            "is_default": is_default,
        }

    async def suspend_model_in_profile(self, model_id: int, profile_id: int, suspended: bool = True) -> bool:
        """Suspend or unsuspend a model in a specific profile."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE model_routing SET is_suspended = ? WHERE model_id = ? AND profile_id = ?",
                (1 if suspended else 0, model_id, profile_id),
            )
            await db.commit()

        return True

    async def remove_model_from_profile(self, model_id: int, profile_id: int) -> bool:
        """Remove a model from a profile's routing chain. Only non-default models can be removed."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if it's a default model
            row = await self._fetchone(
                db,
                "SELECT is_default FROM model_routing WHERE model_id = ? AND profile_id = ?",
                (model_id, profile_id),
            )

            if not row:
                return False

            if row[0]:  # is_default = 1
                return False  # Cannot remove default models

            await db.execute(
                "DELETE FROM model_routing WHERE model_id = ? AND profile_id = ?",
                (model_id, profile_id),
            )
            await db.commit()

        return True

    async def delete_model(self, model_id: int) -> bool:
        """Delete a model. Only custom models can be deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if model is custom
            row = await self._fetchone(db, "SELECT is_custom FROM models WHERE id = ?", (model_id,))
            if not row or row[0] != 1:
                return False

            # Remove from routing first
            await db.execute("DELETE FROM model_routing WHERE model_id = ?", (model_id,))
            # Delete model
            await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
            await db.commit()

        return True

    async def reorder_models_in_profile(self, profile_id: int, model_ids: list[int]) -> bool:
        """Reorder models in a profile. Only non-default models can be reordered."""
        now = datetime.now(UTC).isoformat(timespec="seconds")

        async with aiosqlite.connect(self.db_path) as db:
            for idx, model_id in enumerate(model_ids, 1):
                # Check if this model is default
                row = await self._fetchone(
                    db,
                    "SELECT is_default FROM model_routing WHERE model_id = ? AND profile_id = ?",
                    (model_id, profile_id),
                )

                if not row:
                    continue

                if row[0]:  # is_default = 1
                    return False  # Cannot reorder default models

                await db.execute(
                    "UPDATE model_routing SET order_index = ? WHERE model_id = ? AND profile_id = ?",
                    (idx, model_id, profile_id),
                )

            await db.commit()

        return True

    # =================================================================
    # CRUD: Model Folders
    # =================================================================

    async def list_model_folders(self, active_only: bool = True) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT id, path, is_active, scan_on_start, last_scanned, created_at FROM model_folders"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY id ASC"

            rows = await self._fetchall(db, query)

        return [
            {
                "id": row[0],
                "path": row[1],
                "is_active": bool(row[2]),
                "scan_on_start": bool(row[3]),
                "last_scanned": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    async def create_model_folder(self, path: str, scan_on_start: bool = True) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO model_folders (path, is_active, scan_on_start, created_at)
                VALUES (?, 1, ?, ?)
                """,
                (path, 1 if scan_on_start else 0, now),
            )
            await db.commit()
            folder_id = int(cur.lastrowid)

        return {
            "id": folder_id,
            "path": path,
            "is_active": True,
            "scan_on_start": scan_on_start,
            "last_scanned": None,
            "created_at": now,
        }

    async def delete_model_folder(self, folder_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM model_folders WHERE id = ?", (folder_id,))
            await db.commit()

        return True

    async def scan_model_folder(self, folder_id: int) -> dict[str, Any]:
        """Scan a model folder for local models and add them to the database."""
        import os

        async with aiosqlite.connect(self.db_path) as db:
            # Get folder path
            row = await self._fetchone(db, "SELECT path FROM model_folders WHERE id = ?", (folder_id,))
            if not row:
                return {"added": 0, "errors": ["Folder not found"]}

            folder_path = row[0]

            # Check if folder exists
            if not os.path.isdir(folder_path):
                return {"added": 0, "errors": [f"Folder does not exist: {folder_path}"]}

            # Get local provider ID
            local_provider = await self._fetchone(db, "SELECT id FROM providers WHERE name = 'local'")
            if not local_provider:
                return {"added": 0, "errors": ["Local provider not found"]}

            local_provider_id = local_provider[0]

            # Scan for model folders (each subfolder is a model)
            now = datetime.now(UTC).isoformat(timespec="seconds")
            added = 0
            errors = []

            try:
                for item in os.listdir(folder_path):
                    item_path = os.path.join(folder_path, item)
                    if os.path.isdir(item_path):
                        # Check if model already exists
                        existing = await self._fetchone(
                            db,
                            "SELECT id FROM models WHERE provider_id = ? AND name = ?",
                            (local_provider_id, item),
                        )

                        if not existing:
                            # Add model
                            await db.execute(
                                """
                                INSERT INTO models (provider_id, name, is_custom, exists_on_disk, folder_id, created_at)
                                VALUES (?, ?, 0, 1, ?, ?)
                                """,
                                (local_provider_id, item, folder_id, now),
                            )
                            added += 1

                # Update last_scanned
                await db.execute(
                    "UPDATE model_folders SET last_scanned = ? WHERE id = ?",
                    (now, folder_id),
                )

                await db.commit()

            except Exception as e:
                errors.append(str(e))

        return {"added": added, "errors": errors}

    async def validate_local_models(self) -> dict[str, Any]:
        """Validate that local models still exist on disk."""
        import os

        validated = {"valid": 0, "invalid": 0, "errors": []}
        now = datetime.now(UTC).isoformat(timespec="seconds")

        async with aiosqlite.connect(self.db_path) as db:
            # Get all local models with their folders
            rows = await self._fetchall(
                db,
                """
                SELECT m.id, m.name, mf.path
                FROM models m
                JOIN model_folders mf ON m.folder_id = mf.id
                WHERE m.provider_id = (SELECT id FROM providers WHERE name = 'local')
                """,
            )

            for model_id, model_name, folder_path in rows:
                model_path = os.path.join(folder_path, model_name)

                if os.path.isdir(model_path):
                    # Model exists, update status
                    await db.execute(
                        "UPDATE models SET exists_on_disk = 1, last_checked = ? WHERE id = ?",
                        (now, model_id),
                    )
                    validated["valid"] += 1
                else:
                    # Model doesn't exist, mark as invalid and suspended
                    await db.execute(
                        "UPDATE models SET exists_on_disk = 0, last_checked = ? WHERE id = ?",
                        (now, model_id),
                    )
                    # Suspend in all profiles
                    await db.execute(
                        "UPDATE model_routing SET is_suspended = 1 WHERE model_id = ?",
                        (model_id,),
                    )
                    validated["invalid"] += 1
                    validated["errors"].append(f"Model not found: {model_name}")

            await db.commit()

        return validated