from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import request_id_middleware
from app.routers import auth, media, users, library, reviews, comments, lists

# (Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& c:\Users\sefa_\Desktop\multimedia-library-app\multimedia-library-api\venv\Scripts\Activate.ps1)
# alembic upgrade head

#! to run: uvicorn app.main:app --reload
#! health check: http://localhost:8000/health
#! docs: http://localhost:8000/docs
#TODO: this docs must be inactive in prod.

settings = get_settings()
configure_logging(settings)

app = FastAPI(title=settings.app_name)
app.middleware("http")(request_id_middleware)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(library.router, prefix=settings.api_prefix)
app.include_router(reviews.router, prefix=settings.api_prefix)
app.include_router(comments.router, prefix=settings.api_prefix)
app.include_router(lists.router, prefix=settings.api_prefix)



@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
