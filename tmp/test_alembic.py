from fastapi import FastAPI
from app.core.db import alembic_upgrade

app = FastAPI()

alembic_upgrade()

@app.get("/healthz")
async def health():
    return {"ok": True}