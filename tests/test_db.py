import pytest

from db import RotatorDB
from constants import Provider


@pytest.mark.asyncio
async def test_db_initialize(tmp_path):
    db_path = tmp_path / "rotator.db"
    db = RotatorDB(str(db_path))
    await db.initialize()
    # Ensure daily quotas can be set and retrieved
    await db.increment_daily_quota(Provider.GOOGLE.value, "gemma-3-27b-it", f"{Provider.GOOGLE.value}:0")
    data = await db.load_daily_quota_map()
    assert data
