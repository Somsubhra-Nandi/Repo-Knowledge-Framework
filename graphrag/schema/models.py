"""Canonical Pydantic schema models for graph persistence."""

from pydantic import BaseModel, ConfigDict, field_validator

ALLOWED_HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def build_fqn(*parts: str) -> str:
    """
    Build a fully-qualified name from parts, filtering empty strings.

    Examples:
        build_fqn("auth", "UserService", "get_user") -> "auth.UserService.get_user"
        build_fqn("", "UserService", "get_user")     -> "UserService.get_user"
    """
    filtered_parts = [part for part in parts if part]
    return ".".join(filtered_parts)


class FileNode(BaseModel):
    path: str
    language: str
    checksum: str
    last_parsed: str

    model_config = ConfigDict(frozen=True)


class ClassNode(BaseModel):
    fqn: str
    name: str
    file: str
    line: int
    language: str
    is_interface: bool = False
    is_abstract: bool = False

    model_config = ConfigDict(frozen=True)


class MethodNode(BaseModel):
    fqn: str
    name: str
    file: str
    line: int
    signature: str
    language: str
    source_code: str = ""
    is_dynamic: bool = False

    model_config = ConfigDict(frozen=True)


class EndpointNode(BaseModel):
    path: str
    http_method: str
    handler_fqn: str
    language: str
    file: str
    line: int

    model_config = ConfigDict(frozen=True)

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, value: str) -> str:
        method = value.upper()
        if method not in ALLOWED_HTTP_METHODS:
            raise ValueError("http_method must be one of GET, POST, PUT, DELETE, PATCH")
        return method


class ImportNode(BaseModel):
    source_file: str
    target_module: str
    symbols: list[str]
    is_external: bool

    model_config = ConfigDict(frozen=True)


class CallEdge(BaseModel):
    caller_fqn: str
    callee_fqn: str
    line: int
    confidence: float
    resolved: bool
    dynamic_flag: bool = False

    model_config = ConfigDict(frozen=True)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0 inclusive")
        return value


class DependencyEdge(BaseModel):
    from_file: str
    to_file_or_package: str
    is_third_party: bool

    model_config = ConfigDict(frozen=True)

