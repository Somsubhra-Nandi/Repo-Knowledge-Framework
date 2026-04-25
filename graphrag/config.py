from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    repo_root_path: str = "/workspace"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()