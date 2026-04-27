from pathlib import Path
from unittest.mock import MagicMock, patch


def _target_path(name: str) -> Path:
    target_dir = Path("tests") / ".tmp_sync"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / name


def _cleanup_target(target: Path) -> None:
    target.unlink(missing_ok=True)
    target.parent.rmdir()


def test_validate_syntax_rejects_broken_python() -> None:
    from graphrag.graph.sync import validate_syntax

    errors = validate_syntax("test.py", "def broken(:\n    pass")
    assert len(errors) > 0


def test_validate_syntax_accepts_valid_python() -> None:
    from graphrag.graph.sync import validate_syntax

    errors = validate_syntax("test.py", "def valid():\n    return True\n")
    assert errors == []


def test_validate_syntax_accepts_unsupported_extension() -> None:
    from graphrag.graph.sync import validate_syntax

    errors = validate_syntax("file.unknown", "any content here")
    assert errors == []


def test_safe_write_file_rejects_syntax_errors() -> None:
    from graphrag.graph.sync import safe_write_file

    target = _target_path("reject.py")
    try:
        result = safe_write_file(str(target), "def broken(:\n    pass")
        assert result.success is False
        assert len(result.syntax_errors) > 0
        assert not target.exists()
    finally:
        _cleanup_target(target)


def test_safe_write_file_writes_valid_content() -> None:
    from graphrag.graph.sync import safe_write_file

    target = _target_path("valid.py")
    try:
        with patch("graphrag.graph.sync.auto_sync_graph") as mock_sync:
            mock_sync.return_value = MagicMock(
                nodes_added=1,
                nodes_removed=0,
                nodes_updated=0,
                edges_added=0,
                git_sha="abc123",
            )
            result = safe_write_file(str(target), "def valid():\n    return True\n")
        assert result.success is True
        assert target.exists()
        assert target.read_text() == "def valid():\n    return True\n"
    finally:
        _cleanup_target(target)


def test_safe_write_file_does_not_write_on_error() -> None:
    from graphrag.graph.sync import safe_write_file

    target = _target_path("no_write.py")
    try:
        result = safe_write_file(str(target), "class Broken(:\n    pass")
        assert result.success is False
        assert not target.exists()
    finally:
        _cleanup_target(target)


def test_get_git_sha_returns_string() -> None:
    from graphrag.graph.sync import _get_git_sha

    sha = _get_git_sha()
    assert isinstance(sha, str)
    assert len(sha) > 0


def test_mcp_safe_write_tool_returns_correct_shape() -> None:
    from graphrag.mcp.server import safe_write_file as mcp_safe_write

    mock_result = MagicMock(
        success=False,
        file_path="test.py",
        message="Syntax errors found",
        syntax_errors=["ERROR at line 1"],
        graph_updated=False,
    )
    with patch("graphrag.mcp.server._safe_write_file_impl", return_value=mock_result):
        result = mcp_safe_write("test.py", "broken code")
    assert "success" in result
    assert "syntax_errors" in result
