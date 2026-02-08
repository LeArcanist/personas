from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    personas = relationship("Persona", back_populates="user")

    # MFA fields
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(String, nullable=True)  # store TOTP secret (prototype)

class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)

    category = Column(String, nullable=False, default="other")  
    description = Column(String, nullable=True)                 
    is_public = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="personas")
    profile = relationship("PersonaProfile", back_populates="persona", uselist=False)

class PersonaProfile(Base):
    __tablename__ = "persona_profiles"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), unique=True)
    display_name = Column(String)
    avatar_url = Column(String)
    bio = Column(String)

    persona = relationship("Persona", back_populates="profile")

class CategoryMessage(Base):
    __tablename__ = "category_messages"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    sender_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender_persona = relationship("Persona")

class DMThread(Base):
    __tablename__ = "dm_threads"

    id = Column(Integer, primary_key=True, index=True)
    persona_a_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    persona_b_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    category = Column(String, nullable=False) 
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    persona_a = relationship("Persona", foreign_keys=[persona_a_id])
    persona_b = relationship("Persona", foreign_keys=[persona_b_id])

class DMMessage(Base):
    __tablename__ = "dm_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("dm_threads.id"), nullable=False)
    sender_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    thread = relationship("DMThread")
    sender_persona = relationship("Persona")
