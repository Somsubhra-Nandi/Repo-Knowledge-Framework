import pytest
from pydantic import ValidationError

from graphrag.schema.models import (
    CallEdge,
    ClassNode,
    DependencyEdge,
    EndpointNode,
    FileNode,
    ImportNode,
    MethodNode,
    build_fqn,
)


def test_file_node_round_trip() -> None:
    model = FileNode(
        path="src/auth.py",
        language="python",
        checksum="a" * 64,
        last_parsed="2026-04-25T21:00:00Z",
    )
    data = model.model_dump()
    reconstructed = FileNode(**data)
    assert reconstructed == model


def test_class_node_round_trip() -> None:
    model = ClassNode(
        fqn="auth.UserService",
        name="UserService",
        file="src/auth.py",
        line=10,
        language="python",
        is_interface=False,
        is_abstract=False,
    )
    data = model.model_dump()
    reconstructed = ClassNode(**data)
    assert reconstructed == model


def test_method_node_round_trip() -> None:
    model = MethodNode(
        fqn="auth.UserService.get_user",
        name="get_user",
        file="src/auth.py",
        line=22,
        signature="def get_user(self, user_id: str) -> dict:",
        language="python",
        is_dynamic=False,
    )
    data = model.model_dump()
    reconstructed = MethodNode(**data)
    assert reconstructed == model


def test_endpoint_node_round_trip() -> None:
    model = EndpointNode(
        path="/api/users",
        http_method="POST",
        handler_fqn="auth.UserService.create_user",
        language="python",
        file="src/api.py",
        line=45,
    )
    data = model.model_dump()
    reconstructed = EndpointNode(**data)
    assert reconstructed == model


def test_import_node_round_trip() -> None:
    model = ImportNode(
        source_file="src/auth.py",
        target_module="pathlib",
        symbols=["Path"],
        is_external=True,
    )
    data = model.model_dump()
    reconstructed = ImportNode(**data)
    assert reconstructed == model


def test_call_edge_round_trip() -> None:
    model = CallEdge(
        caller_fqn="auth.UserService.get_user",
        callee_fqn="db.UserRepo.fetch",
        line=31,
        confidence=0.8,
        resolved=True,
        dynamic_flag=False,
    )
    data = model.model_dump()
    reconstructed = CallEdge(**data)
    assert reconstructed == model


def test_dependency_edge_round_trip() -> None:
    model = DependencyEdge(
        from_file="src/auth.py",
        to_file_or_package="pydantic",
        is_third_party=True,
    )
    data = model.model_dump()
    reconstructed = DependencyEdge(**data)
    assert reconstructed == model


def test_call_edge_confidence_validator_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        CallEdge(
            caller_fqn="a.A.one",
            callee_fqn="a.A.two",
            line=1,
            confidence=1.1,
            resolved=True,
        )

    with pytest.raises(ValidationError):
        CallEdge(
            caller_fqn="a.A.one",
            callee_fqn="a.A.two",
            line=1,
            confidence=-0.1,
            resolved=True,
        )


def test_call_edge_confidence_validator_accepts_boundaries() -> None:
    zero = CallEdge(
        caller_fqn="a.A.one",
        callee_fqn="a.A.two",
        line=1,
        confidence=0.0,
        resolved=True,
    )
    one = CallEdge(
        caller_fqn="a.A.one",
        callee_fqn="a.A.two",
        line=1,
        confidence=1.0,
        resolved=True,
    )
    assert zero.confidence == 0.0
    assert one.confidence == 1.0


def test_endpoint_http_method_validator() -> None:
    endpoint_upper = EndpointNode(
        path="/api/users",
        http_method="DELETE",
        handler_fqn="auth.UserService.delete_user",
        language="python",
        file="src/api.py",
        line=50,
    )
    endpoint_lower = EndpointNode(
        path="/api/users",
        http_method="delete",
        handler_fqn="auth.UserService.delete_user",
        language="python",
        file="src/api.py",
        line=51,
    )
    assert endpoint_upper.http_method == "DELETE"
    assert endpoint_lower.http_method == "DELETE"

    with pytest.raises(ValidationError):
        EndpointNode(
            path="/api/users",
            http_method="INVALID",
            handler_fqn="auth.UserService.delete_user",
            language="python",
            file="src/api.py",
            line=52,
        )


def test_build_fqn() -> None:
    assert build_fqn("auth", "UserService", "get_user") == "auth.UserService.get_user"
    assert build_fqn("", "UserService", "get_user") == "UserService.get_user"
    assert build_fqn("com.company", "auth", "UserService") == "com.company.auth.UserService"


def test_models_are_immutable() -> None:
    file_node = FileNode(
        path="src/auth.py",
        language="python",
        checksum="b" * 64,
        last_parsed="2026-04-25T21:00:00Z",
    )
    with pytest.raises(ValidationError):
        file_node.path = "src/renamed.py"
