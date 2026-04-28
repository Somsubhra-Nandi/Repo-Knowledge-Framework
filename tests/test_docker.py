def test_dockerfile_exists():
    from pathlib import Path

    assert Path("Dockerfile").exists()


def test_docker_compose_exists():
    from pathlib import Path

    assert Path("docker-compose.yml").exists()


def test_docker_compose_has_three_services():
    import yaml
    from pathlib import Path

    data = yaml.safe_load(Path("docker-compose.yml").read_text())
    assert set(data["services"].keys()) == {"neo4j", "app", "mcp"}


def test_docker_compose_neo4j_has_healthcheck():
    import yaml
    from pathlib import Path

    data = yaml.safe_load(Path("docker-compose.yml").read_text())
    assert "healthcheck" in data["services"]["neo4j"]


def test_mcp_config_generator_runs():
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/generate_mcp_config.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert Path("mcp_config.json").exists()


def test_env_example_has_all_keys():
    from pathlib import Path

    content = Path(".env.example").read_text()
    for key in [
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "REPO_ROOT_PATH",
        "LOG_LEVEL",
        "NEO4J_DATABASE",
    ]:
        assert key in content, f"Missing {key} in .env.example"
