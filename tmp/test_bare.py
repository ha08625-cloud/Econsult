from fastapi import FastAPI
app = FastAPI()

@app.get("/healthz")
async def health():
    return {"ok": True}