from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/users")
def create_user(name: str):
    return {"name": name}


@router.get("/users/{user_id}")
def get_user(user_id: str):
    return {"id": user_id}


@router.delete("/users/{user_id}")
def delete_user(user_id: str):
    return {"deleted": user_id}
