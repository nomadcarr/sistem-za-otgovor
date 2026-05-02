# Входна точка — опростена за n8n архитектура.
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db
from scheduler import start_scheduler
from internal_api import router as internal_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Main] Инициализиране на база данни...")
    init_db()
    print("[Main] Стартиране на scheduler...")
    start_scheduler()
    print("[Main] Системата е готова на порт 8000.")
    yield


app = FastAPI(
    title="AI Система за отговор",
    description="Вътрешно API — извиква се от n8n",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(internal_router, prefix="/internal", tags=["Internal"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/admin/report/send-now")
async def trigger_report():
    from scheduler import _send_daily_report
    await _send_daily_report()
    return {"status": "report_sent"}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
