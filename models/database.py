from sqlmodel import create_engine, Session
from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
import logging

logging.basicConfig(level=logging.INFO)

# Get database URL from environment variables for security
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://macbookprom1:password@127.0.0.1:5432/rgo")

engine = create_engine(DATABASE_URL, echo=True) # echo=True for logging SQL queries

def get_session():
    with Session(engine) as session:
        yield session

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Starting up...")
    yield
    logging.info("Shutting down...")