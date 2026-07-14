from fastapi import FastAPI

app = FastAPI(title="Hardware Hub")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

