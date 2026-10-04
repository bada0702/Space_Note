from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import init_db
from auth import require_auth
from routers import attachments, categories, notes, ai, search, routes, graph, conversations, mcp

app = FastAPI(title="SpaceNote Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGIN.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    settings.reload()
    from services.vault import sync_db_with_vault
    sync_db_with_vault()
    from services import graph_worker
    graph_worker.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    from services import graph_worker
    graph_worker.stop()


@app.get("/health")
def health():
    return {"status": "ok", "default_vault": str(settings.VAULT_DIR)}


app.include_router(categories.router, dependencies=[Depends(require_auth)])
app.include_router(notes.router, dependencies=[Depends(require_auth)])
app.include_router(ai.router, dependencies=[Depends(require_auth)])
app.include_router(search.router, dependencies=[Depends(require_auth)])
app.include_router(routes.router, dependencies=[Depends(require_auth)])
app.include_router(graph.router, dependencies=[Depends(require_auth)])
app.include_router(conversations.router, dependencies=[Depends(require_auth)])
app.include_router(attachments.router, dependencies=[Depends(require_auth)])
app.include_router(attachments.public_router)
app.include_router(mcp.router, dependencies=[Depends(require_auth)])
app.include_router(mcp.public_router)
