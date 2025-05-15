""" Settings for the verification database SQLAlchemy ORM manager."""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./verification.db"

engine = create_async_engine(DATABASE_URL, future=True, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()