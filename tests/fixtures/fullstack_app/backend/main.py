from fastapi import FastAPI

app = FastAPI()


@app.get("/api/users")
def get_users():
    from users import UserService

    svc = UserService()
    return svc.get_all()


@app.post("/api/users")
def create_user(name: str):
    from users import UserService

    svc = UserService()
    return svc.create(name)


@app.get("/api/users/{user_id}")
def get_user(user_id: str):
    from users import UserService

    svc = UserService()
    return svc.get_by_id(user_id)


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str):
    from users import UserService

    svc = UserService()
    return svc.delete(user_id)
