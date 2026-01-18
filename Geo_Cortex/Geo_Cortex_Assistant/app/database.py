from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment variable or use default.
# Quickstart allows SQLite for dev/testing; default to a local SQLite DB if DATABASE_URL isn't set.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./geocortex.db"

# Create engine
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Dialect helpers (used for conditional geo support)
DB_DIALECT = engine.dialect.name
IS_POSTGIS = DB_DIALECT == "postgresql"
IS_SQLITE = DB_DIALECT == "sqlite"

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()
