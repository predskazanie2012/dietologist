import asyncio
import logging

from app.database import Base, engine
from app.seed import seed
from sqlalchemy import inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        user_columns = await conn.run_sync(_user_columns)
        if "target_weight_kg" not in user_columns:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN target_weight_kg FLOAT")
        if "height_cm" not in user_columns:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN height_cm FLOAT")
        if "age_years" not in user_columns:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN age_years INTEGER")
        if "sex" not in user_columns:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN sex VARCHAR(32)")
        if "activity_level" not in user_columns:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN activity_level VARCHAR(32)")
    await seed()
    logger.info("Local database is ready")


def _user_columns(sync_conn) -> set[str]:
    return {column["name"] for column in inspect(sync_conn).get_columns("users")}


if __name__ == "__main__":
    asyncio.run(main())
