from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from models.database import init_db
from routers import auth, data
from services.scheduler import start_scheduler, stop_scheduler
import logging
import os

logging.basicConfig(level=logging.INFO)


def _cors_origins() -> list[str]:
    from services.url_config import get_public_url

    defaults = ["http://localhost:3000", "http://localhost:5173"]
    extra = os.getenv("CORS_ORIGINS", "").strip()
    if extra:
        defaults.extend(o.strip() for o in extra.split(",") if o.strip())
    public = get_public_url()
    if public and public not in defaults:
        defaults.append(public)
    return defaults


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.app_auth import auth_enabled

    from services.url_config import get_public_url

    public = get_public_url().lower()
    if public.startswith("https://") and not auth_enabled():
        logging.warning(
            "PUBLIC_URL is HTTPS but AUTH_USERNAME/AUTH_PASSWORD_HASH are not set — "
            "configure app login before exposing SA Hub to the internet"
        )
    await init_db()

    from services.ai_service import check_llm_available
    llm_err = await check_llm_available()
    if llm_err:
        logging.warning("LLM not ready (sync AI steps will fail until fixed): %s", llm_err)

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="SA Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(data.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
