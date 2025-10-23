"""
db.py — Database session setup for GPU Reseller API
Handles SQLAlchemy engine creation and dependency injection for FastAPI.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
import os

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/gpureseller")

# --- SQLAlchemy Engine & Session ---
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Base Class for Models (optional for future ORM usage) ---
Base = declarative_base()

# --- Dependency for FastAPI routes ---
def get_db():
    """
    FastAPI dependency that yields a SQLAlchemy session.
    Ensures proper cleanup after each request.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
