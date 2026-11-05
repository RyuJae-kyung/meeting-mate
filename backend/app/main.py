import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from . import migrations
from .database import Base, engine
from .routers import auth, briefings, dashboard, emails, materials, meetings, questions, results, tasks
from .scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("meeting_mate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # 테이블 자동 생성 (운영 확장 시 Alembic 도입)
    migrations.run(engine)
    s = get_settings()
    log.info("AI provider=%s, Email provider=%s", s.ai_mode, s.email_mode)
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Meeting Mate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
        msgs.append(f"{loc}: {e.get('msg')}" if loc else e.get("msg"))
    return JSONResponse(status_code=422, content={"detail": " / ".join(msgs), "errors": jsonable(exc.errors())})


def jsonable(errors):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(errors, custom_encoder={Exception: str})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


for r in (auth.router, meetings.router, materials.router, briefings.router, emails.router, dashboard.router,
          questions.router, results.router, tasks.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    s = get_settings()
    return {"status": "ok", "db": "ok", "ai_provider": s.ai_mode, "email_provider": s.email_mode}
