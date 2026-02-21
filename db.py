import asyncio
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
import shutil
from typing import Any

import aiosqlite


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
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
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
    ) -> dict[str, Any]:
        token = f"proj-{secrets.token_urlsafe(12)}"
        now = datetime.now(UTC).isoformat(timespec="seconds")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO project_keys (name, token, daily_limit, policy, quota_mode, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, token, daily_limit, policy, quota_mode, 1, now, now),
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
            "active": True,
        }

    async def list_project_keys(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await self._fetchall(
                db,
                """
                SELECT id, name, token, daily_limit, policy, quota_mode, active, created_at, updated_at
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
                "active": bool(row[6]),
                "created_at": row[7],
                "updated_at": row[8],
            }
            for row in rows
        ]

    async def resolve_project_key(self, token: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await self._fetchone(
                db,
                """
                SELECT id, name, token, daily_limit, policy, quota_mode, active
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
            "active": bool(row[6]),
        }

    async def deactivate_project_key(self, project_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE project_keys SET active = 0, updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(timespec="seconds"), project_id),
            )
            await db.commit()

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