"""Test database lifecycle and a seeded two-tenant org.

Org in tenant A (manager tree):
    founder
     |-- manager
     |    `-- report
     |         `-- deep_report
     `-- peer
Tenant B has one employee, used to prove isolation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from daydor.config import test_database_url
from tests.factories import insert
from tests import role_mode  # noqa: F401  (DAYDOR_TEST_ROLES=worker runs queue handlers on worker roles)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _recreate_database(url: str) -> None:
    u = make_url(url)
    admin = psycopg.connect(host=u.host, port=u.port, user=u.username, password=u.password,
                            dbname="postgres", autocommit=True)
    admin.execute(f'DROP DATABASE IF EXISTS "{u.database}" WITH (FORCE)')
    admin.execute(f'CREATE DATABASE "{u.database}" OWNER "{u.username}"')
    admin.close()


@pytest.fixture(scope="session")
def db_url() -> str:
    url = test_database_url()
    _recreate_database(url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    return url


@pytest.fixture(scope="session")
def engine(db_url):
    eng = create_engine(db_url)
    yield eng
    eng.dispose()


@dataclass
class Org:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    emp: dict[str, uuid.UUID] = field(default_factory=dict)
    user: dict[str, uuid.UUID] = field(default_factory=dict)
    emp_b: uuid.UUID | None = None
    legal_entity_a: uuid.UUID | None = None


def _seed_tenant(conn, name: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant = insert(conn, "tenant", legal_name=name, status="active")
    le = insert(conn, "legal_entity", tenant_id=tenant, name=f"{name} Pvt Ltd", country_code="IN")
    dept = insert(conn, "department", tenant_id=tenant, name="Engineering")
    loc = insert(conn, "location", tenant_id=tenant, name="Bengaluru", country_code="IN",
                 state_code="KA", legal_entity_id=le)
    return tenant, le, dept, loc


@pytest.fixture(scope="session")
def org(engine) -> Org:
    with engine.begin() as conn:
        ta, le_a, dept_a, loc_a = _seed_tenant(conn, "Acme")
        tb, le_b, dept_b, loc_b = _seed_tenant(conn, "Globex")
        o = Org(tenant_a=ta, tenant_b=tb, legal_entity_a=le_a)
        for key in ["founder", "manager", "report", "deep_report", "peer"]:
            o.emp[key] = insert(conn, "employee", tenant_id=ta, full_name=key.title(),
                                legal_entity_id=le_a, department_id=dept_a, location_id=loc_a,
                                hire_event_id=f"hire-{key}", personal_address="12 MG Road, Bengaluru",
                                date_of_birth=__import__("datetime").date(1990, 5, 17))
            o.user[key] = insert(conn, "app_user", tenant_id=ta, role="employee", employee_id=o.emp[key])
        o.emp_b = insert(conn, "employee", tenant_id=tb, full_name="Other Co Person", legal_entity_id=le_b,
                         department_id=dept_b, location_id=loc_b, hire_event_id="hire-b")
        # Approvers in tenant A, distinct from employees above where it matters for maker-checker.
        for key, role in [("hr_admin", "hr"), ("payroll_lead", "payroll"), ("founder_user", "founder")]:
            o.user[key] = insert(conn, "app_user", tenant_id=ta, role=role)
        for emp, mgr in [("manager", "founder"), ("report", "manager"), ("deep_report", "report"),
                         ("peer", "founder")]:
            insert(conn, "reporting_line", tenant_id=ta, employee_id=o.emp[emp],
                   manager_employee_id=o.emp[mgr], relation="solid", effective_from="2026-01-01")
    return o


@pytest.fixture
def hire_org(engine):
    """A tenant of its own, for hire-flow tests (tests/test_hire*.py) that create employees,
    requisitions etc. without perturbing the row counts other tests (e.g. test_queue.py) assert
    against the shared `org` fixture's tenant."""
    with engine.begin() as conn:
        tenant = insert(conn, "tenant", legal_name="Hire Co", status="active")
        le = insert(conn, "legal_entity", tenant_id=tenant, name="Hire Co Pvt Ltd", country_code="IN")
        dept = insert(conn, "department", tenant_id=tenant, name="Engineering")
        loc = insert(conn, "location", tenant_id=tenant, name="Bengaluru", country_code="IN",
                    state_code="KA", legal_entity_id=le)
        job_profile = insert(conn, "job_profile", tenant_id=tenant, title="Engineer",
                             job_family="Engineering", level="L3", flsa_default="exempt",
                             description="Builds things")
        hiring_manager = insert(conn, "employee", tenant_id=tenant, full_name="Hiring Manager",
                                legal_entity_id=le, department_id=dept, location_id=loc,
                                hire_event_id="hire-org-manager")
        founder_user = insert(conn, "app_user", tenant_id=tenant, role="founder")
        hr_user = insert(conn, "app_user", tenant_id=tenant, role="hr")
        position = insert(conn, "position", tenant_id=tenant, department_id=dept, job_profile_id=job_profile,
                          status="open", budgeted_fte="1.0", budgeted_cost="1200000", opened_at="2026-01-01")
    return {"tenant": tenant, "legal_entity": le, "department": dept, "location": loc,
            "job_profile": job_profile, "hiring_manager": hiring_manager, "founder_user": founder_user,
            "hr_user": hr_user, "position": position}
