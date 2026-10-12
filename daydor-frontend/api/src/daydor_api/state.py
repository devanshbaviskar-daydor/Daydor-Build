from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine

from daydor.db.session import make_engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine()


def reset_engine() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
