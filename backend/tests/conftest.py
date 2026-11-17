"""Test harness. Runs ONLY against the isolated test database in TEST_DATABASE_URL (.env.test),
never the development database. Schema comes from the real Alembic migrations."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    env_file = ROOT / ".env.test"
    if not url and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("TEST_DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    if not url:
        pytest.exit("Set TEST_DATABASE_URL (see README, 'Running tests').", 2)
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.exit("Refusing to run: the test database name must end with _test.", 2)
    return url


TEST_URL = _test_url()
os.environ["DATABASE_URL"] = TEST_URL  # app settings now point at the test DB only
os.environ.setdefault("APP_ENV", "test")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.database import set_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.seed import create_user, seed_demo, seed_reference  # noqa: E402

PASSWORD = "Correct-Horse-9"
APPEND_ONLY = ("audit_logs", "inventory_transactions")


TEST_USERS = [("owner", ["OWNER"], "4821"), ("gm", ["GM"], "5937"), ("admin", ["SYSADMIN"], None), ("supv", ["SUPV"], "7314"),
              ("cashier", ["CASHIER"], "2468"), ("cashier2", ["CASHIER"], "1357"), ("waiter", ["WAITER"], "8642"), ("kmgr", ["KMGR"], "9753"),
              ("cook", ["COOK"], "3691"), ("invoff", ["INVOFF"], "1593"), ("acct", ["ACCT"], "7539"), ("auditor", ["AUDITOR"], None)]
_SEED: dict = {}
TABLES = [t.name for t in Base.metadata.sorted_tables]


def _raw(eng, *statements: str) -> None:
    """Test-only maintenance. session_replication_role=replica skips FK and append-only triggers for the reset."""
    with eng.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for s in statements:
            conn.execute(text(s))


@pytest.fixture(scope="session")
def engine():
    subprocess.run([sys.executable, "-m", "alembic", "-x", f"db_url={TEST_URL}", "upgrade", "head"], cwd=ROOT, check=True, capture_output=True)
    eng = create_engine(TEST_URL, pool_size=10, max_overflow=10)
    set_engine(eng)
    # Seed once, then keep a copy in schema "test_snapshot" that every test restores from.
    _raw(eng, *[f'DELETE FROM "{t}"' for t in reversed(TABLES)])
    from app.core.database import session_factory

    with session_factory()() as db:
        ref = seed_reference(db)
        seed_demo(db, ref)
        users = {u: create_user(db, u, u.title(), PASSWORD, roles, ref["branch"], pin=pin).id for u, roles, pin in TEST_USERS}
        db.commit()
        info = {"branch_id": ref["branch"].id, "users": users}
    _raw(eng, "DROP SCHEMA IF EXISTS test_snapshot CASCADE", "CREATE SCHEMA test_snapshot",
         *[f'CREATE TABLE test_snapshot."{t}" AS SELECT * FROM public."{t}"' for t in TABLES])
    _SEED.update(info)
    yield eng
    eng.dispose()


@pytest.fixture()
def seeded(engine):
    _raw(engine, *[f'DELETE FROM public."{t}"' for t in reversed(TABLES)], *[f'INSERT INTO public."{t}" SELECT * FROM test_snapshot."{t}"' for t in TABLES],
         "SELECT setval(pg_get_serial_sequence('audit_logs','id'), 1, false)")
    yield _SEED


@pytest.fixture()
def client(seeded):
    with TestClient(app) as c:
        yield c


class Api:
    """A signed-in test client for one user."""

    def __init__(self, client: TestClient, username: str):
        self.c = client
        self.username = username
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.token = r.json()["access_token"]

    def _h(self, headers: dict | None, idem: bool | str) -> dict:
        h = {"Authorization": f"Bearer {self.token}", **(headers or {})}
        if idem:
            h["Idempotency-Key"] = idem if isinstance(idem, str) else str(uuid.uuid4())
        return h

    def get(self, url, **kw):
        return self.c.get("/api/v1" + url, headers=self._h(kw.pop("headers", None), False), **kw)

    def post(self, url, json=None, idem: bool | str = False, **kw):
        return self.c.post("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None), idem), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None), False), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put("/api/v1" + url, json=json, headers=self._h(kw.pop("headers", None), False), **kw)

    def delete(self, url, **kw):
        return self.c.delete("/api/v1" + url, headers=self._h(kw.pop("headers", None), False), **kw)


@pytest.fixture()
def api(client):
    cache: dict[str, Api] = {}

    def get(username: str) -> Api:
        if username not in cache:
            cache[username] = Api(client, username)
        return cache[username]

    return get
