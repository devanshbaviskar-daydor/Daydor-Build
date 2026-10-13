"""API tests run against a real Postgres with the backend's own migrations applied, then this
package's schema and a seeded demo tenant. Nothing is mocked: sign-in, row security, gates and the
workflow engine are the real ones."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

import daydor

BACKEND_ROOT = Path(os.environ.get("DAYDOR_BACKEND_ROOT", Path(daydor.__file__).resolve().parents[2]))
TEST_URL = os.environ.get("DAYDOR_API_TEST_DATABASE_URL",
                          "postgresql+psycopg://daydor_owner:dev@localhost:5432/daydor_api_test")


def _recreate(url: str) -> None:
    u = make_url(url)
    admin = psycopg.connect(host=u.host, port=u.port, user=u.username, password=u.password,
                            dbname="postgres", autocommit=True)
    admin.execute(f'DROP DATABASE IF EXISTS "{u.database}" WITH (FORCE)')
    admin.execute(f'CREATE DATABASE "{u.database}" OWNER "{u.username}"')
    admin.close()


@pytest.fixture(scope="session")
def seeded():
    _recreate(TEST_URL)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.attributes["database_url"] = TEST_URL
    command.upgrade(cfg, "head")
    os.environ["DAYDOR_DATABASE_URL"] = TEST_URL
    os.environ["DAYDOR_API_ENV"] = "dev"
    from daydor_api import seed_dev, state
    state.reset_engine()
    info = seed_dev.run()
    assert info["seeded"]
    yield info
    state.reset_engine()


@pytest.fixture(scope="session")
def client(seeded):
    from daydor_api.app import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="session")
def engine(seeded):
    from daydor_api.state import get_engine
    return get_engine()


def sign_in(client: TestClient, email: str) -> dict:
    r = client.post("/api/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def people(client):
    emails = {
        "founder": "rohan.mehta@acme.test", "hr": "kavya.menon@acme.test", "payroll": "dev.patel@acme.test",
        "it": "sana.qureshi@acme.test", "manager": "meera.iyer@acme.test", "employee": "arjun.rao@acme.test",
        "ops": "ops@daydor.test", "admin": "admin@daydor.test", "auditor": "imran.khan@audit.test",
    }
    return {k: sign_in(client, e) for k, e in emails.items()}


def run_workers(rounds: int = 4) -> dict:
    from daydor_api import worker
    return worker.tick_all(worker.build_workers(name="test"), rounds=rounds)


def hire_start_fields(client: TestClient, hr_headers: dict, manager_employee_id: str,
                      proposed_base: int = 2400000) -> dict:
    """Every field `POST /hire/start` requires beyond position/manager/dates/pay range: the interview
    and offer inputs plus the new-hire details later steps read. For tests that exercise only the
    early steps and just need the request to be accepted, not to drive a hire to completion."""
    loc = client.get("/api/tables/location", headers=hr_headers).json()["rows"][0]
    band = client.get("/api/tables/comp_band", headers=hr_headers).json()["rows"][0]["id"]
    retention = client.get("/api/tables/retention_policy", headers=hr_headers).json()["rows"][0]["id"]
    return {
        "interviewer_employee_id": manager_employee_id, "scheduled_at": "2026-11-10T10:00:00",
        "comp_band_id": band, "proposed_base": proposed_base,
        "legal_entity_id": loc["legal_entity_id"], "location_id": loc["id"],
        "state_code": loc["state_code"] or "KA", "employment_type": "full_time",
        "date_of_birth": "1995-04-12", "personal_address": "1 MG Road, Bengaluru", "aadhaar_last4": "1234",
        "basic_da_monthly": 50000, "tax_regime_election": "new", "retention_class_id": retention,
        "pay_frequency": "monthly", "payment_method": "bank_transfer", "work_state": "KA", "tax_state": "KA",
    }
