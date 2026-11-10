import sqlite3

import pytest

from tests.conftest import AUTH
from tests.test_graph import _graph_fixture, _note, _store, _store_onto


def _audit():
    from config import settings
    from graph_eval.audit import audit, open_ro
    conn = open_ro(settings.DB_PATH)
    try:
        return audit(conn)
    finally:
        conn.close()


def test_audit_counts_kind_violations(client):
    from db import get_conn
    a = _note(client, "A", "본문")
    _store_onto(a["id"], [("FAISS", "instance"), ("벡터DB", "class")], [("FAISS", "인스턴스이다", "벡터DB")])
    assert _audit()["kind_violations"]["인스턴스이다"] == 0
    with get_conn() as conn:
        conn.execute("UPDATE concepts SET kind = 'instance' WHERE name = '벡터DB'")
    assert _audit()["kind_violations"]["인스턴스이다"] == 1


def test_audit_tail_concepts(client):
    a = _note(client, "긴 노트", "a" * 40_001 + " Zeta")
    _store(a["id"], [("Zeta", "개념", 2, [])])
    res = _audit()
    assert res["long_notes"] == 1
    assert res["tail_concepts"] == 1


def test_audit_lines_match_discovery_routes(client):
    _graph_fixture(client)
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert _audit()["lines"] == len(routes)


def test_open_ro_rejects_writes(client):
    from config import settings
    from graph_eval.audit import open_ro
    conn = open_ro(settings.DB_PATH)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM notes")
    conn.close()
