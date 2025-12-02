"""
Root-level entry point for Railway buildpack detection.
This file imports the FastAPI app from app.main to help Railway auto-detect the application.
"""
from app.main import app

# This allows Railway's buildpack to detect the FastAPI app
__all__ = ['app']

