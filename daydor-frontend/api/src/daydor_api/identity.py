from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from daydor.model.loader import ROLE_DB

from .state import get_engine

# The people-facing database roles (agents and the dispatcher never sign in).
HUMAN_ROLES = ("daydor_admin", "daydor_ops", "tenant_founder", "tenant_hr", "tenant_payroll",
               "tenant_it", "tenant_manager", "tenant_employee", "external_auditor")
ROLE_LETTER = {db: letter for letter, db in ROLE_DB.items()}
ROLE_LABEL = {
    "daydor_admin": "Daydor admin", "daydor_ops": "Daydor ops", "tenant_founder": "Founder",
    "tenant_hr": "HR admin", "tenant_payroll": "Payroll and finance", "tenant_it": "IT admin",
    "tenant_manager": "People manager", "tenant_employee": "Employee", "external_auditor": "External auditor",
}
# Roles that can read app_user at all (model table_acl). Payroll and managers cannot, so their
# identity row is confirmed when provisioned, not at every sign-in.
CAN_READ_APP_USER = {"daydor_admin", "daydor_ops", "tenant_founder", "tenant_hr", "tenant_it",
                     "tenant_employee", "external_auditor"}


# Roles the database lets read workflow instances, transitions and gate evaluations
# (migrations 0006 and 0009 in the backend). One place, used by every endpoint and the session payload.
WORKFLOW_READER_ROLES = frozenset({"daydor_ops", "tenant_founder", "tenant_hr", "tenant_payroll", "external_auditor"})
# Roles the database grants SELECT on the employee_directory view (migration 0004).
DIRECTORY_ROLES = frozenset({"daydor_ops", "tenant_founder", "tenant_hr", "tenant_payroll", "tenant_it", "tenant_manager", "tenant_employee"})
# Roles that may see colleagues' names on the audit trail: the ones that can already read app_user broadly.
NAME_VISIBLE_ROLES = frozenset({"daydor_ops", "tenant_founder", "tenant_hr", "tenant_it"})


@dataclass(frozen=True)
class Identity:
    id: UUID
    email: str
    display_name: str
    tenant_id: UUID | None
    tenant_name: str | None
    user_id: UUID | None
    employee_id: UUID | None
    role: str

    @property
    def letter(self) -> str:
        return ROLE_LETTER[self.role]

    def public(self) -> dict:
        return {
            "id": str(self.id), "email": self.email, "display_name": self.display_name,
            "role": self.role, "role_letter": self.letter, "role_label": ROLE_LABEL[self.role],
            "tenant_id": str(self.tenant_id) if self.tenant_id else None, "tenant_name": self.tenant_name,
            "user_id": str(self.user_id) if self.user_id else None,
            "employee_id": str(self.employee_id) if self.employee_id else None,
            "capabilities": {"workflow_timeline": self.role in WORKFLOW_READER_ROLES, "directory": self.role in DIRECTORY_ROLES},
        }


_COLS = "id, email, display_name, tenant_id, tenant_name, user_id, employee_id, role"


def _row(r) -> Identity:
    return Identity(r.id, str(r.email), r.display_name, r.tenant_id, r.tenant_name, r.user_id,
                    r.employee_id, r.role)


def find_by_email(email: str) -> Identity | None:
    with get_engine().begin() as conn:
        r = conn.execute(text(f"SELECT {_COLS} FROM api.identity WHERE email = :e AND is_active"),
                         {"e": email.strip()}).first()
    return _row(r) if r else None


def find_by_id(identity_id: UUID | str) -> Identity | None:
    with get_engine().begin() as conn:
        r = conn.execute(text(f"SELECT {_COLS} FROM api.identity WHERE id = :i AND is_active"),
                         {"i": str(identity_id)}).first()
    return _row(r) if r else None


def list_active() -> list[Identity]:
    with get_engine().begin() as conn:
        rows = conn.execute(text(f"SELECT {_COLS} FROM api.identity WHERE is_active ORDER BY role, display_name")).all()
    return [_row(r) for r in rows]


def create(*, email: str, display_name: str, role: str, tenant_id: UUID | None, tenant_name: str | None = None,
           user_id: UUID | None = None, employee_id: UUID | None = None) -> Identity:
    if role not in HUMAN_ROLES:
        raise ValueError(f"{role!r} is not a people-facing role")
    with get_engine().begin() as conn:
        r = conn.execute(text(
            "INSERT INTO api.identity (email, display_name, tenant_id, tenant_name, user_id, employee_id, role) "
            "VALUES (:e, :n, :t, :tn, :u, :emp, :r) "
            "ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name, tenant_id = EXCLUDED.tenant_id, "
            "tenant_name = EXCLUDED.tenant_name, user_id = EXCLUDED.user_id, employee_id = EXCLUDED.employee_id, "
            f"role = EXCLUDED.role, is_active = true RETURNING {_COLS}"),
            {"e": email, "n": display_name, "t": tenant_id, "tn": tenant_name, "u": user_id,
             "emp": employee_id, "r": role}).one()
    return _row(r)


def display_names(user_ids: list[UUID]) -> dict[str, str]:
    """user id -> display name, from this package's own identity table."""
    ids = [str(u) for u in user_ids if u]
    if not ids:
        return {}
    with get_engine().begin() as conn:
        rows = conn.execute(text("SELECT user_id, display_name FROM api.identity WHERE user_id = ANY(CAST(:ids AS uuid[]))"),
                            {"ids": ids}).all()
    return {str(r.user_id): r.display_name for r in rows}
