from pathlib import Path


def test_independent_router_service_is_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "goal_interpretation").exists()
    assert not (root / "orchestrator/clients/router_client.py").exists()
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "chromie-router:" not in compose


def test_router_test_imports_follow_core_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in (root / "tests").glob("test_router*.py"):
        if path.name == "test_router_removal_r3_service_deleted.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "from router.app" not in source
