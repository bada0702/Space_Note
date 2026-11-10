import csv

from tests.test_graph import _graph_fixture


def _conn():
    from config import settings
    from graph_eval.audit import open_ro
    return open_ro(settings.DB_PATH)


def _label_all(path, value="1"):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["label"] = value
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_export_then_score(client, tmp_path):
    from graph_eval import links
    rag, emb, faiss, other = _graph_fixture(client)
    labels = tmp_path / "labels.csv"
    sample = [rag["id"], emb["id"]]
    conn = _conn()
    added = links.export_unlabeled(conn, labels, sample)
    assert added >= 2
    before = links.score(conn, labels, sample)
    # 정밀도@5는 노트별로 센다 — 표본 두 노트가 서로의 상위 항로면 같은 쌍이 두 번 집계된다
    assert before["all"]["unlabeled"] >= added and before["all"]["precision"] is None
    _label_all(labels)
    res = links.score(conn, labels, sample)
    assert res["all"]["precision"] == 1.0
    assert res["all"]["unlabeled"] == 0
    assert links.export_unlabeled(conn, labels, sample) == 0
    conn.close()


def test_score_skips_missing_sample_notes(client, tmp_path):
    from graph_eval import links
    rag, emb, faiss, other = _graph_fixture(client)
    labels = tmp_path / "labels.csv"
    sample = [rag["id"], "없는-노트"]
    conn = _conn()
    links.export_unlabeled(conn, labels, sample)
    res = links.score(conn, labels, sample)
    assert res["missing_notes"] == 1
    conn.close()


def test_csv_is_utf8_sig(client, tmp_path):
    from graph_eval import links
    rag, emb, faiss, other = _graph_fixture(client)
    labels = tmp_path / "labels.csv"
    conn = _conn()
    links.export_unlabeled(conn, labels, [rag["id"]])
    conn.close()
    assert labels.read_bytes()[:3] == b"\xef\xbb\xbf"
