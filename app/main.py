import logging

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(title="Personal Dietitian Bot API", version="0.1.0")

from .local_access import LocalOnly
app.add_middleware(LocalOnly)

app.include_router(router)
