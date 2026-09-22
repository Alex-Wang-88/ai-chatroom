from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db.session import SessionFactory, init_db
from app.logging import configure_logging
from app.orchestrator.service import ConversationOrchestrator
from app.providers import JimoProvider, ProviderRegistry
from app.realtime.event_hub import ConversationEventHub

settings = get_settings()
configure_logging(settings.log_level)
providers = ProviderRegistry()
providers.register("jimo", JimoProvider(settings))
hub = ConversationEventHub(settings.ws_ring_buffer_size)
orchestrator = ConversationOrchestrator(settings, SessionFactory, providers, hub)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await orchestrator.seed_agents()
    yield


app = FastAPI(title="AI Chat Room API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
