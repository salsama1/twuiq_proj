from database import Base

from sqlalchemy import Column, Integer, String, Float,Boolean,ForeignKey
from sqlalchemy.orm import relationship

from sqlalchemy.ext.declarative import declarative_base

class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True)
    user_name = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String, index=True)
    
    # Relationships
    tovisit_places = relationship("Tovisit", back_populates="owner", cascade="all, delete-orphan")
    visited_places = relationship("VisitedPlace", back_populates="user", cascade="all, delete-orphan")


class Places(Base):
    """ Class to represent the places table in the database"""
    __tablename__ = 'places'
    uuid = Column(String, primary_key=True, index=True)
    poi_name = Column(String, index=True)
    lat = Column(Float, index=True)
    lng = Column(Float, index=True)
    reviews_no = Column(Float, index=True)
    price_range = Column(String, index=True)
    category = Column(String, index=True)
    
    # Relationships
    visitors = relationship("VisitedPlace", back_populates="place", cascade="all, delete-orphan")
    tovisit_users = relationship("Tovisit", back_populates="place", cascade="all, delete-orphan")


class Tovisit(Base):
    __tablename__ = 'tovisits'

    id = Column(Integer, primary_key=True, index=True)  # Primary key
    user_id = Column(Integer, ForeignKey('users.id'))  # User ID (FK)
    place_uuid = Column(String, ForeignKey('places.uuid'))  # Place UUID (FK)
    name = Column(String, index=True)
    description = Column(String, index=True)
    priority = Column(Integer, index=True)
    category = Column(String, index=True)
    
    # Relationships
    owner = relationship("Users", back_populates="tovisit_places")
    place = relationship("Places", back_populates="tovisit_users")


class VisitedPlace(Base):
    __tablename__ = 'visited_places'

    id = Column(Integer, primary_key=True, index=True)  # Primary key
    user_id = Column(Integer, ForeignKey('users.id'))  # User ID (FK)
    place_uuid = Column(String, ForeignKey('places.uuid'))  # Place UUID (FK)
    
    name = Column(String, index=True)
    description = Column(String, index=True)
    priority = Column(Integer, index=True)
    category = Column(String, index=True)
    visited = Column(Boolean, index=True)
    rating_if_visited = Column(Float, index=True)
    
    # Relationships
    user = relationship("Users", back_populates="visited_places")
    place = relationship("Places", back_populates="visitors")
