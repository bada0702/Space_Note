import re
from itertools import combinations
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db import get_conn
from services.graph_extraction import predicate_strength
from services.graph_retrieval import idf
from services.textnorm import norm_name

router = APIRouter()


@router.get("/search")
def search(q: str = "", all_words: bool = False):
    term = (q or "").strip()
    if not term:
        return []
    if all_words:
        # 성도 검색: 띄어쓰기·밑줄·하이픈으로 나눈 단어가 제목이나 본문 한쪽에 모두 있으면 일치
        patterns = [
            "%" + w.replace("\\", "\\\\").replace("%", "\\%") + "%"
            for w in re.split(r"[_\-\s]+", term) if w
        ]
        if not patterns:
            return []
        every = lambda col: " AND ".join([f"{col} LIKE ? ESCAPE '\\'"] * len(patterns))  # noqa: E731
        where, params = f"(({every('title')}) OR ({every('content')}))", patterns * 2
    else:
        like = f"%{term}%"
        where, params = "(title LIKE ? OR content LIKE ?)", [like, like]
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, category_id, created_at, modified_at FROM notes "
            f"WHERE {where} AND is_archived = 0 "
            "ORDER BY modified_at DESC LIMIT 50",
            params,
        ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content_preview": (r["content"] or "")[:200],
            "category_id": r["category_id"],
            "created_at": r["created_at"],
            "modified_at": r["modified_at"],
        }
        for r in rows
    ]


@router.get("/discoveries")
def discoveries(note_id: Optional[str] = None):
    """노트 간 연결 후보를 발견(discovery)으로 반환 — 근거는 _PairEvidence 참고.

    note_id가 주어지면 그 노트와 이어지는 다른 노트들을, 없으면 다른 노트와 하나라도
    이어지는 모든 노트를 근거 점수 순으로 반환한다. 전체 보기에서 근거는 그 노트가 가진
    모든 연결의 근거를 합친 것이다.
    """
    with get_conn() as conn:
        ev = _PairEvidence(conn)
        rejected = {
            (r["note_a"], r["note_b"])
            for r in conn.execute("SELECT note_a, note_b FROM routes WHERE status = 'rejected'")
        }
        notes = {
            r["id"]: r for r in conn.execute(
                "SELECT id, title, category_id, modified_at FROM notes WHERE is_archived = 0"
            )
        }

    agg: dict[str, dict] = {}
    for key in ev.keys() - rejected:
        a, b = key
        if note_id:
            if note_id not in key:
                continue
            targets = [b if a == note_id else a]
        else:
            targets = [a, b]
        for t in targets:
            d = agg.setdefault(t, {"score": 0.0, "entities": set(), "concepts": set(), "relations": {}})
            d["score"] += ev.score(key)
            d["entities"] |= ev.keywords.get(key, set())
            d["concepts"] |= ev.concepts.get(key, {}).keys()
            for label, strength in ev.relations.get(key, {}).items():
                d["relations"][label] = max(strength, d["relations"].get(label, 0.0))

    out = []
    for nid, d in agg.items():
        n = notes.get(nid)
        if n is None:
            continue
        relations = ev.strongest_relations(d["relations"])
        out.append(
            {
                "note_id": nid,
                "title": n["title"],
                "category_id": n["category_id"],
                "shared_count": len(d["entities"] | d["concepts"]),
                "shared_entities": sorted(d["entities"]),
                "shared_concepts": sorted(d["concepts"]),
                "relations": relations,
                "evidence": ev.evidence_for(relations),
                "modified_at": n["modified_at"],
            }
        )
    out.sort(key=lambda x: (agg[x["note_id"]]["score"], x["modified_at"]), reverse=True)
    return out


@router.get("/entities/{note_id}")
def entities(note_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM entities WHERE note_id = ? ORDER BY created_at",
            (note_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/tags")
def list_tags():
    """전체 태그를 노트 수 내림차순으로 반환. 표기가 다르지만 norm이 같으면 하나로 묶는다."""
    with get_conn() as conn:
        rows = conn.execute("SELECT note_id, tag, norm FROM tags").fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        d = agg.setdefault(r["norm"], {"tag": r["tag"], "note_ids": set()})
        d["note_ids"].add(r["note_id"])

    out = [{"tag": d["tag"], "count": len(d["note_ids"])} for d in agg.values()]
    out.sort(key=lambda x: (x["count"], x["tag"]), reverse=True)
    return out


@router.get("/tags/{tag}/notes")
def notes_for_tag(tag: str):
    norm = norm_name(tag)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT n.id AS id, n.title AS title, n.category_id AS category_id, "
            "n.modified_at AS modified_at "
            "FROM tags t JOIN notes n ON n.id = t.note_id "
            "WHERE t.norm = ? ORDER BY n.modified_at DESC",
            (norm,),
        ).fetchall()
    return [dict(r) for r in rows]


_MAX_ROUTES_PER_NOTE = 5
_MAX_RELATIONS_PER_ROUTE = 5
# 노트의 이 비율보다 많이 나오는 개념은 허브로 보고 노트 쌍 근거에서 뺀다 — 거의 모든 노트를
# 잇는 개념은 연결을 설명하지 못하고, 노트 수의 제곱만큼 쌍을 만든다. 노트가 적을 때는 적용하지 않는다
_HUB_SHARE = 0.3
_HUB_MIN_NOTES = 10
_RELATION_WEIGHT = 1.0
_KEYWORD_WEIGHT = 0.5


def _hub_concepts(concept_notes: dict[str, set[str]], total: int) -> set[str]:
    limit = max(_HUB_MIN_NOTES, _HUB_SHARE * total)
    return {cid for cid, ns in concept_notes.items() if len(ns) > limit}


class _PairEvidence:
    """노트 쌍(note_a < note_b)마다 이어지는 근거 세 가지. literal(값) 노드는 노트마다 따로라 쓰지 않는다.

    concepts: 지식 그래프 개념 공유 (개념 이름 → 희소성 IDF), relations: 한 노트의 개념과
    다른 노트의 개념을 잇는 관계, keywords: 엔티티/태그 공유. 엔티티와 태그는 같은 텍스트라도
    서로 다른 개념이므로 'e:'/'t:' 접두사로 네임스페이스를 분리한다.
    두 노트 모두 그래프가 있으면 추출 키워드(엔티티)는 근거로 쓰지 않는다 — 그래프가 같은
    내용을 더 정확하게 담고 있다. 사용자가 직접 단 태그는 그래프가 있어도 근거로 남긴다.
    """

    def __init__(self, conn):
        erows = conn.execute(
            "SELECT e.note_id AS note_id, e.norm AS norm, e.name AS name "
            "FROM entities e JOIN notes n ON n.id = e.note_id "
            "WHERE e.norm IS NOT NULL AND e.norm != '' AND n.is_archived = 0"
        ).fetchall()
        trows = conn.execute(
            "SELECT t.note_id AS note_id, t.norm AS norm, t.tag AS name "
            "FROM tags t JOIN notes n ON n.id = t.note_id "
            "WHERE t.norm != '' AND n.is_archived = 0"
        ).fetchall()
        concept_rows = conn.execute(
            "SELECT nc.note_id AS note_id, c.id AS cid, c.name AS name FROM note_concepts nc "
            "JOIN concepts c ON c.id = nc.concept_id AND c.kind != 'literal' "
            "JOIN notes n ON n.id = nc.note_id AND n.is_archived = 0"
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT r.subj_id AS s, r.pred AS p, r.obj_id AS o, MAX(r.evidence) AS evidence "
            "FROM relations r JOIN notes n ON n.id = r.note_id AND n.is_archived = 0 "
            "JOIN concepts co ON co.id = r.obj_id AND co.kind != 'literal' "
            "GROUP BY r.subj_id, r.pred, r.obj_id"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM notes WHERE is_archived = 0").fetchone()[0] or 1

        concept_notes: dict[str, set[str]] = defaultdict(set)
        concept_name: dict[str, str] = {}
        for r in concept_rows:
            concept_notes[r["cid"]].add(r["note_id"])
            concept_name[r["cid"]] = r["name"]
        self.graph_notes: set[str] = {r["note_id"] for r in concept_rows}

        self.hubs = _hub_concepts(concept_notes, total)

        self.concepts: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for cid, note_ids in concept_notes.items():
            if cid in self.hubs:
                continue
            weight = idf(total, len(note_ids))
            for a, b in combinations(sorted(note_ids), 2):
                self.concepts[(a, b)][concept_name[cid]] = weight

        # 쌍 → {관계 라벨: 강도}, 라벨 → 근거 문장
        self.relations: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        self.evidence: dict[str, str] = {}
        for r in relation_rows:
            if r["s"] == r["o"] or r["s"] in self.hubs or r["o"] in self.hubs:
                continue
            s_notes, o_notes = concept_notes.get(r["s"], set()), concept_notes.get(r["o"], set())
            label = f"{concept_name[r['s']]} —{r['p']}→ {concept_name[r['o']]}"
            strength = predicate_strength(r["p"])
            if r["evidence"]:
                self.evidence[label] = r["evidence"]
            for a in s_notes:
                for b in o_notes:
                    if a != b:
                        self.relations[tuple(sorted((a, b)))][label] = strength

        norm_notes: dict[str, set[str]] = defaultdict(set)
        norm_display: dict[str, str] = {}
        for prefix, rows in (("e", erows), ("t", trows)):
            for r in rows:
                key = f"{prefix}:{r['norm']}"
                norm_notes[key].add(r["note_id"])
                norm_display.setdefault(key, r["name"])

        self.keywords: dict[tuple[str, str], set[str]] = defaultdict(set)
        for norm, note_ids in norm_notes.items():
            for a, b in combinations(sorted(note_ids), 2):
                if norm.startswith("e:") and a in self.graph_notes and b in self.graph_notes:
                    continue
                self.keywords[(a, b)].add(norm_display[norm])

    def keys(self) -> set[tuple[str, str]]:
        return set(self.keywords) | set(self.concepts) | set(self.relations)

    def score(self, k: tuple[str, str]) -> float:
        """희귀한 공유 개념일수록, 관계가 많을수록 높다. 키워드는 보조 근거."""
        return (sum(self.concepts.get(k, {}).values())
                + _RELATION_WEIGHT * sum(self.relations.get(k, {}).values())
                + _KEYWORD_WEIGHT * len(self.keywords.get(k, ())))

    def strongest_relations(self, relations: dict[str, float]) -> list[str]:
        return sorted(relations, key=lambda label: (-relations[label], label))[:_MAX_RELATIONS_PER_ROUTE]

    def evidence_for(self, labels: list[str]) -> dict[str, str]:
        return {label: self.evidence[label] for label in labels if label in self.evidence}

    def fields(self, k: tuple[str, str]) -> dict:
        concepts = self.concepts.get(k, {})
        relations = self.strongest_relations(self.relations.get(k, {}))
        return {
            "shared_entities": sorted(self.keywords.get(k, set())),
            "shared_concepts": sorted(concepts, key=lambda name: (-concepts[name], name)),
            "relations": relations,
            "evidence": self.evidence_for(relations),
            "kind": self.kind(k),
        }

    def kind(self, k: tuple[str, str]) -> str:
        """성도에서 선을 구분해 그릴 근거 종류: relation(타입 관계) > concept > keyword > none(확정만)."""
        if any(s >= 1.0 for s in self.relations.get(k, {}).values()):
            return "relation"
        if k in self.concepts or k in self.relations:
            return "concept"
        if k in self.keywords:
            return "keyword"
        return "none"


def ranked_routes(ev: _PairEvidence, rejected: set[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """노트 id → 그 노트의 상위 항로 쌍 키 (근거 점수 내림차순, 노트당 상한까지)."""
    by_note: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in ev.keys() - rejected:
        by_note[key[0]].append(key)
        by_note[key[1]].append(key)
    for keys in by_note.values():
        keys.sort(key=lambda k: (ev.score(k), k), reverse=True)
        del keys[_MAX_ROUTES_PER_NOTE:]
    return dict(by_note)


@router.get("/discoveries/routes")
def discovery_routes():
    """노트 쌍을 항로(route)로 반환 — 성도의 연결선 렌더링용. 근거는 _PairEvidence 참고.

    노트당 상한은 근거 점수가 높은 쌍부터 채운다.
    """
    with get_conn() as conn:
        ev = _PairEvidence(conn)
        crows = conn.execute(
            "SELECT r.note_a AS note_a, r.note_b AS note_b, r.status AS status FROM routes r "
            "JOIN notes na ON na.id = r.note_a AND na.is_archived = 0 "
            "JOIN notes nb ON nb.id = r.note_b AND nb.is_archived = 0"
        ).fetchall()
    confirmed = {(r["note_a"], r["note_b"]) for r in crows if r["status"] == "confirmed"}
    rejected = {(r["note_a"], r["note_b"]) for r in crows if r["status"] == "rejected"}

    keep: set[tuple[str, str]] = set()
    for keys in ranked_routes(ev, rejected).values():
        keep.update(keys)

    # 확정 항로는 발견 쌍에서 사라져도 유지한다 — 사용자의 명시적 선택이므로
    # AI 재계산에 좌우되지 않는다.
    all_keys = sorted(keep | confirmed)
    return [
        {"note_a": a, "note_b": b, **ev.fields((a, b)), "confirmed": (a, b) in confirmed}
        for a, b in all_keys
    ]


_MAX_PATH_EDGES = 8


@router.get("/routes/path")
def route_path(from_id: str = Query(alias="from"), to_id: str = Query(alias="to")):
    """두 노트를 잇는 가장 짧은 지식 그래프 경로 (노트 — 개념 — 관계 — 개념 — 노트 …).

    중간에 다른 노트를 거쳐도 된다. 허브 개념은 항로와 같은 기준으로 빼서 지름길을 막는다.
    경로는 nodes(노트/개념)와 그 사이 edges(포함/관계) 목록으로, 없으면 found=false.
    """
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="같은 노트입니다")
    with get_conn() as conn:
        notes = {
            r["id"]: r["title"]
            for r in conn.execute("SELECT id, title FROM notes WHERE is_archived = 0")
        }
        if from_id not in notes or to_id not in notes:
            raise HTTPException(status_code=404, detail="노트를 찾을 수 없습니다")
        concept_rows = conn.execute(
            "SELECT nc.note_id AS note_id, c.id AS cid, c.name AS name FROM note_concepts nc "
            "JOIN concepts c ON c.id = nc.concept_id AND c.kind != 'literal' "
            "JOIN notes n ON n.id = nc.note_id AND n.is_archived = 0"
        ).fetchall()
        relation_rows = conn.execute(
            "SELECT r.subj_id AS s, r.pred AS p, r.obj_id AS o, MAX(r.evidence) AS evidence "
            "FROM relations r JOIN notes n ON n.id = r.note_id AND n.is_archived = 0 "
            "JOIN concepts co ON co.id = r.obj_id AND co.kind != 'literal' "
            "GROUP BY r.subj_id, r.pred, r.obj_id"
        ).fetchall()

    concept_notes: dict[str, set[str]] = defaultdict(set)
    concept_name: dict[str, str] = {}
    for r in concept_rows:
        concept_notes[r["cid"]].add(r["note_id"])
        concept_name[r["cid"]] = r["name"]
    hubs = _hub_concepts(concept_notes, len(notes))

    # 그래프 노드 키: ("n", note_id) / ("c", concept_id). 이웃마다 그 간선의 설명을 붙인다
    adj: dict[tuple[str, str], list[tuple[tuple[str, str], dict]]] = defaultdict(list)
    for cid, note_ids in concept_notes.items():
        if cid in hubs:
            continue
        for nid in note_ids:
            adj[("n", nid)].append((("c", cid), {"kind": "contains"}))
            adj[("c", cid)].append((("n", nid), {"kind": "contains"}))
    for r in relation_rows:
        s, o = r["s"], r["o"]
        if s == o or s in hubs or o in hubs or s not in concept_notes or o not in concept_notes:
            continue
        rel = {"kind": "relation", "pred": r["p"], "subject": concept_name[s],
               "object": concept_name[o], "evidence": r["evidence"]}
        adj[("c", s)].append((("c", o), rel))
        adj[("c", o)].append((("c", s), rel))

    start, goal = ("n", from_id), ("n", to_id)
    prev: dict[tuple[str, str], tuple[tuple[str, str], dict] | None] = {start: None}
    frontier = [start]
    for _ in range(_MAX_PATH_EDGES):
        if goal in prev or not frontier:
            break
        nxt = []
        for node in frontier:
            for neighbor, edge in sorted(adj[node], key=lambda x: x[0]):
                if neighbor not in prev:
                    prev[neighbor] = (node, edge)
                    nxt.append(neighbor)
        frontier = nxt
    if goal not in prev:
        return {"found": False, "nodes": [], "edges": []}

    chain = [goal]
    edges = []
    while prev[chain[-1]] is not None:
        node, edge = prev[chain[-1]]
        edges.append(edge)
        chain.append(node)
    chain.reverse()
    edges.reverse()

    def describe(node: tuple[str, str]) -> dict:
        kind, key = node
        if kind == "n":
            return {"kind": "note", "id": key, "title": notes[key]}
        return {"kind": "concept", "id": key, "name": concept_name[key]}

    return {"found": True, "nodes": [describe(n) for n in chain], "edges": edges}
