"""OSII-server ASGI composition root; PostgreSQL and authentication are required."""
from osii.server.api import create_app

app = create_app()
