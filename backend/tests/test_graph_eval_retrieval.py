from tests.test_graph import _graph_fixture


def _conn():
    from config import settings
    from graph_eval.audit import open_ro
    return open_ro(settings.DB_PATH)


def test_evaluate_hit_and_mrr(client):
    from graph_eval import retrieval
    rag, emb, faiss, other = _graph_fixture(client)
    questions = [
        {"q": "검색 증강 생성은 어떻게 동작해?", "answers": [rag["id"]]},
        {"q": "점심 메뉴 추천", "answers": [faiss["id"]]},
    ]
    conn = _conn()
    res = retrieval.evaluate(conn, questions)
    conn.close()
    assert res["rows"][0]["ranks"] == [1]
    assert res["rows"][1]["ranks"] == [None]
    assert res["hit_at_5"] == 0.5
    assert res["mrr"] == 0.5


def test_missing_answer_ids_are_counted(client):
    from graph_eval import retrieval
    rag, emb, faiss, other = _graph_fixture(client)
    questions = [
        {"q": "검색 증강 생성은 어떻게 동작해?", "answers": [rag["id"]]},
        {"q": "없는 노트를 찾는 질문", "answers": ["없는-노트"]},
    ]
    conn = _conn()
    res = retrieval.evaluate(conn, questions)
    conn.close()
    assert res["missing_answers"] == 1
    assert res["hit_at_5"] == 1.0   # 정답이 모두 사라진 질문은 분모에서 뺀다


def test_load_questions(tmp_path):
    from graph_eval import retrieval
    path = tmp_path / "q.json"
    path.write_text('[{"q": "질문", "answers": ["a"]}]', encoding="utf-8")
    assert retrieval.load_questions(path) == [{"q": "질문", "answers": ["a"]}]
