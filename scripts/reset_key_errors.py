import asyncio
from pathlib import Path
import json
import aiosqlite
from datetime import datetime, UTC

# locate project root
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.yaml"

async def load_db_path():
    db_file = "rotator.db"
    try:
        if CONFIG_FILE.exists():
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.suffix == ".json" else None
    except Exception:
        cfg = None
    # try YAML if JSON failed
    if cfg is None:
        try:
            import yaml
            if CONFIG_FILE.exists():
                cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    if cfg and isinstance(cfg, dict):
        db_file = str(cfg.get("settings", {}).get("db_file") or db_file)
    db_path = Path(db_file)
    if not db_path.is_absolute():
        db_path = (BASE_DIR / db_path).resolve()
    return str(db_path)

async def main():
    db_path = await load_db_path()
    print(f"Using DB: {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # Ensure tables exist
        await db.execute("PRAGMA foreign_keys = ON")

        # Reset persisted blocked keys
        await db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", ("blocked_keys", '[]'))

        # Reset key_stats counters (requests/errors/tokens/avg)
        await db.execute("UPDATE key_stats SET requests = 0, errors = 0, tokens = 0, avg_response_ms = 0")

        # Clear today's daily_quotas
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        await db.execute("DELETE FROM daily_quotas WHERE date = ?", (today,))

        await db.commit()

    print("Blocked keys cleared, key_stats reset, today's daily_quotas cleared.")

if __name__ == '__main__':
    asyncio.run(main())
