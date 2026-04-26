class UserService:
    def get_all(self) -> list:
        return self._query_db("SELECT * FROM users")

    def create(self, name: str) -> dict:
        return self._query_db(f"INSERT INTO users VALUES ('{name}')")

    def get_by_id(self, user_id: str) -> dict:
        return self._query_db(f"SELECT * FROM users WHERE id='{user_id}'")

    def delete(self, user_id: str) -> bool:
        return self._query_db(f"DELETE FROM users WHERE id='{user_id}'")

    def _query_db(self, sql: str) -> dict:
        return {"sql": sql}
