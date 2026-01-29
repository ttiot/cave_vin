"""Base module for SQLAlchemy database instance.

This module centralizes the SQLAlchemy instance to avoid circular imports
and ensure a single db instance across the application.
"""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
