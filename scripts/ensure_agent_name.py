"""Insert agent_display_name config if missing."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.domain.db import AsyncSessionLocal
from app.domain.models import SystemConfig
from app.services.system_config import DEFAULT_AGENT_NAME, KEY_AGENT_NAME


async def main() -> None:
    async with AsyncSessionLocal() as session:
        row = await session.scalar(
            select(SystemConfig).where(SystemConfig.key == KEY_AGENT_NAME)
        )
        if row is None:
            session.add(
                SystemConfig(
                    key=KEY_AGENT_NAME,
                    value=DEFAULT_AGENT_NAME,
                    description="Nom affiché de l'assistant IA",
                    updated_by="migrate",
                )
            )
            await session.commit()
            print(f"inserted {DEFAULT_AGENT_NAME}")
        else:
            print(f"exists {row.value}")


if __name__ == "__main__":
    asyncio.run(main())
