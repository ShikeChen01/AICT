import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings
from backend.db.models import Agent, Base, Project
from backend.db.session import get_db
from backend.main import app


@pytest_asyncio.fixture
async def internal_client(tmp_path: Path, monkeypatch):
    spec_root = tmp_path / "specs"
    code_root = tmp_path / "code"
    spec_root.mkdir(parents=True, exist_ok=True)
    code_root.mkdir(parents=True, exist_ok=True)
    (spec_root / "GrandSpecification.tex").write_text("grand spec", encoding="utf-8")
    (spec_root / "API&Schema.tex").write_text("api schema", encoding="utf-8")

    monkeypatch.setattr(settings, "spec_repo_path", str(spec_root))
    monkeypatch.setattr(settings, "code_repo_path", str(code_root))

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        project = Project(
            id=uuid.uuid4(),
            name="p",
            description="d",
            spec_repo_path=str(spec_root),
            code_repo_url="https://example.com/repo.git",
            code_repo_path=str(code_root),
        )
        gm = Agent(
            id=uuid.uuid4(),
            project_id=project.id,
            role="manager",
            display_name="GM",
            model="m",
            status="sleeping",
            sandbox_persist=True,
        )
        cto = Agent(
            id=uuid.uuid4(),
            project_id=project.id,
            role="cto",
            display_name="CTO",
            model="m",
            status="sleeping",
            sandbox_persist=True,
        )
        engineer = Agent(
            id=uuid.uuid4(),
            project_id=project.id,
            role="engineer",
            display_name="E1",
            model="m",
            status="sleeping",
            sandbox_persist=False,
        )
        session.add_all([project, gm, cto, engineer])
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, gm, cto, engineer, spec_root, code_root

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_lifecycle_wake_sleep_engineer_sandbox(internal_client):
    client, gm, _, engineer, _, _ = internal_client
    wake_resp = await client.post(
        "/internal/agent/lifecycle/wake",
        headers={"X-Agent-ID": str(gm.id)},
        json={"target_agent_id": str(engineer.id)},
    )
    assert wake_resp.status_code == 200
    wake_body = wake_resp.json()
    assert wake_body["status"] == "active"
    assert wake_body["sandbox_id"] is not None

    sleep_resp = await client.post(
        "/internal/agent/lifecycle/sleep",
        headers={"X-Agent-ID": str(gm.id)},
        json={"target_agent_id": str(engineer.id)},
    )
    assert sleep_resp.status_code == 200
    sleep_body = sleep_resp.json()
    assert sleep_body["status"] == "sleeping"
    assert sleep_body["sandbox_id"] is None


@pytest.mark.asyncio
async def test_internal_files_access_matrix(internal_client):
    client, gm, cto, engineer, _, code_root = internal_client

    gm_read = await client.post(
        "/internal/agent/files/read",
        headers={"X-Agent-ID": str(gm.id)},
        json={"path": "GrandSpecification.tex"},
    )
    assert gm_read.status_code == 200
    assert "grand spec" in gm_read.json()["content"]

    cto_forbidden = await client.post(
        "/internal/agent/files/read",
        headers={"X-Agent-ID": str(cto.id)},
        json={"path": "GrandSpecification.tex"},
    )
    assert cto_forbidden.status_code == 403

    engineer_write_ok = await client.post(
        "/internal/agent/files/write",
        headers={"X-Agent-ID": str(engineer.id)},
        json={
            "path": "src/feature/work.py",
            "content": "print('ok')\n",
            "module_path": str(code_root / "src" / "feature"),
        },
    )
    assert engineer_write_ok.status_code == 200

    engineer_write_blocked = await client.post(
        "/internal/agent/files/write",
        headers={"X-Agent-ID": str(engineer.id)},
        json={
            "path": "src/other/work.py",
            "content": "print('blocked')\n",
            "module_path": str(code_root / "src" / "feature"),
        },
    )
    assert engineer_write_blocked.status_code == 403

