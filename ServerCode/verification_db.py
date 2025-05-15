""" Module for ineracting with the SQLITE database (verficaiton codes database) using SQLAlchemy ORM """
from datetime import datetime, timedelta
from sqlalchemy import select, delete, and_
from vf_config import engine, async_session, Base
from vf_models import SignupSession

async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def create_signup_session(email: str, verification_code: str, expiry: timedelta):
    async with async_session() as session:
        await delete_expired_signup_sessions()
        existing_session = (await session.execute(
            select(SignupSession).where(
                (SignupSession.email == email) &
                (SignupSession.expire > datetime.utcnow())
            )
        )).scalar()
        
        if existing_session: 
            return existing_session.verification_code
        
        new_session = SignupSession(email=email, verification_code=verification_code)
        new_session.expire = datetime.utcnow() + expiry # type: ignore
        session.add(new_session)
        await session.commit()
        return verification_code


async def get_signup_session_by_email(email: str) -> SignupSession:
    async with async_session() as session:
        stmt = select(SignupSession).where(SignupSession.email == email)
        result = await session.execute(stmt)
        return result.scalar()

async def delete_expired_signup_sessions():
    async with async_session() as session:
        now = datetime.utcnow()

        stmt = delete(SignupSession).where(SignupSession.expire < now)
        await session.execute(stmt)
        await session.commit()

async def list_signup_sessions():
    async with async_session() as session:
        async with session.begin():
            result = await session.scalars(select(SignupSession))
            return result


async def main():
    await startup()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
