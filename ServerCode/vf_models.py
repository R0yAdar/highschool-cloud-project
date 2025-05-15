""" Model/table for storing the entries in the Verification code's external database."""
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from vf_config import Base


class SignupSession(Base):
    __tablename__ = "signup_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    verification_code = Column(String, nullable=False)
    expire = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<SignupSession(id={self.id}, email='{self.email}', verification_code='{self.verification_code}, expire='{self.expire}')>"
