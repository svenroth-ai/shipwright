from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/users")
def create_user(name: str):
    return {"name": name}
