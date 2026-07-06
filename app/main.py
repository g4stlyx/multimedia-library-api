from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import request_id_middleware
from app.routers import auth, users


settings = get_settings()
configure_logging(settings)

app = FastAPI(title=settings.app_name)
app.middleware("http")(request_id_middleware)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
