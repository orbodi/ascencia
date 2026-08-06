import asyncio

from sqlalchemy import func, select

from app.domain.db import AsyncSessionLocal
from app.domain.models import Teacher


async def main() -> None:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(Teacher))
        print(f"teachers={count}")


if __name__ == "__main__":
    asyncio.run(main())
