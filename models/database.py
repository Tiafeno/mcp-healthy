from sqlmodel import create_engine, Session
from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
import logging

logging.basicConfig(level=logging.INFO)

# Get database URL from environment variables for security
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

engine = create_engine(DATABASE_URL, echo=False) # echo=True for logging SQL queries

def get_session():
    with Session(engine) as session:
        yield session

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import Redis service here to avoid circular imports
    from utils.redis_service import redis_service
    
    logging.info("Starting up...")
    
    # Initialize Redis connection
    try:
        redis_connected = await redis_service.connect()
        if redis_connected:
            logging.info("Redis service initialized successfully")
        else:
            logging.warning("Redis service failed to initialize, continuing without cache")
    except Exception as e:
        logging.error(f"Error initializing Redis service: {e}")
    
    yield
    
    # Cleanup Redis connection
    logging.info("Shutting down...")
    try:
        await redis_service.disconnect()
    except Exception as e:
        logging.error(f"Error disconnecting Redis service: {e}")