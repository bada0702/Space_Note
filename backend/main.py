from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import settings
from db import init_db
from auth import require_auth
from routers import attachments, categories, notes, ai, search, routes, graph, conversations, mcp, reset

app = FastAPI(title="SpaceNote Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGIN.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 채팅 스트림은 gzip 버퍼에 막혀 답변이 끝날 때까지 안 보이고, 첨부파일은 Range 응답이 깨진다
_NO_GZIP_PATHS = ("/ai/chat", "/attachments/file/")


class _SelectiveGZip(GZipMiddleware):
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(_NO_GZIP_PATHS):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# 압축은 이벤트 루프에서 돈다 — 9MB 목록 기준 기본값 9는 819ms지만 크기는 수준 4와 5% 차이뿐
app.add_middleware(_SelectiveGZip, compresslevel=4)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    settings.reload()
    from services.vault import sync_db_with_vault
    sync_db_with_vault()
    _purge_dangling_rows()
    from services import graph_worker
    graph_worker.start()


def _purge_dangling_rows() -> None:
    import logging
    from db import get_conn
    from services import graph_extraction
    with get_conn() as conn:
        removed = graph_extraction.purge_dangling_rows(conn)
    if any(removed.values()):
        logging.getLogger(__name__).warning("purged rows of deleted notes: %s", removed)


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
app.include_router(reset.router, dependencies=[Depends(require_auth)])
app.include_router(mcp.public_router)
