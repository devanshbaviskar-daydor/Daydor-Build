"""People directory: the backend's employee_directory view (name, work email, department, location,
position for active employees), readable by more roles than the employee table itself."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from ..deps import get_identity
from ..identity import Identity
from ..sessions import human_session

router = APIRouter(tags=["directory"])


@router.get("/directory")
def directory(q: str | None = None, department_id: str | None = None, limit: int = Query(default=50, le=200),
              offset: int = 0, ident: Identity = Depends(get_identity)):
    where, binds = [], {"limit": limit, "offset": offset}
    if q:
        where.append("(full_name ILIKE :q OR work_email ILIKE :q)"); binds["q"] = f"%{q}%"
    if department_id:
        where.append("department_id = :d"); binds["d"] = department_id
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with human_session(ident) as conn:
        rows = conn.execute(text("SELECT id, full_name, work_email, department_id, location_id, position_id "
                                 f"FROM public.employee_directory{clause} ORDER BY full_name LIMIT :limit OFFSET :offset"),
                            binds).mappings().all()
        total = conn.execute(text(f"SELECT count(*) FROM public.employee_directory{clause}"), binds).scalar_one()
    return {"rows": jsonable_encoder([dict(r) for r in rows]), "total": total}
