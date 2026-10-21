"""온톨로지 항로 — 노트 쌍을 관계 연결과 노드 공유로 이어 점수를 매긴다.

설계: docs/superpowers/specs/2026-10-21-ontology-routes-design.md (4. 항로 계산)
"""
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

HUB_NOTES = 30                                   # 이보다 많은 노트에 쓰인 노드는 별자리가 맡는다
SHARE_WEIGHT = {"instance": 1.0, "class": 0.5}
PRED_WEIGHT = {"관련있다": 0.6}                  # 나머지 관계는 1.0
MAX_EVIDENCE = 3


@dataclass
class Pair:
    score: float = 0.0
    # (가중치, 근거) — 근거는 {"s","s_kind","p","o","o_kind"}
    evidence: dict[tuple[str, str, str], tuple[float, dict]] = field(default_factory=dict)

    def add(self, weight: float, rel: dict) -> None:
        key = (rel["s"], rel["p"], rel["o"])
        if key in self.evidence:
            return  # 같은 근거를 두 번 세지 않는다
        self.score += weight
        self.evidence[key] = (weight, rel)

    @property
    def relations(self) -> list[dict]:
        ranked = sorted(self.evidence.values(), key=lambda e: e[0], reverse=True)
        return [rel for _, rel in ranked[:MAX_EVIDENCE]]


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def ontology_pairs(conn) -> dict[tuple[str, str], Pair]:
    """(note_a, note_b) → Pair. literal과 허브 노드는 쓰지 않는다."""
    rows = conn.execute(
        "SELECT nc.note_id AS note_id, c.id AS cid, c.name AS name, c.kind AS kind "
        "FROM note_concepts nc JOIN concepts c ON c.id = nc.concept_id "
        "JOIN notes n ON n.id = nc.note_id "
        "WHERE n.is_archived = 0 AND c.kind != 'literal'"
    ).fetchall()
    notes_of: dict[str, set[str]] = defaultdict(set)
    node: dict[str, tuple[str, str]] = {}
    for r in rows:
        notes_of[r["cid"]].add(r["note_id"])
        node[r["cid"]] = (r["name"], r["kind"])
    usable = {cid for cid, ns in notes_of.items() if len(ns) <= HUB_NOTES}

    pairs: dict[tuple[str, str], Pair] = defaultdict(Pair)

    # 1. 같은 노드 공유
    for cid in usable:
        ns = notes_of[cid]
        if len(ns) < 2:
            continue
        name, kind = node[cid]
        rel = {"s": name, "s_kind": kind, "p": "공유", "o": name, "o_kind": kind}
        for a, b in combinations(sorted(ns), 2):
            pairs[(a, b)].add(SHARE_WEIGHT.get(kind, 0.5), rel)

    # 2. 관계 연결: X —p→ Y 에서 X를 가진 노트와 Y를 가진 노트를 잇는다
    # 보관한 노트에서 나온 관계는 쓰지 않는다
    for r in conn.execute(
        "SELECT DISTINCT r.subj_id, r.pred, r.obj_id FROM relations r "
        "JOIN notes n ON n.id = r.note_id WHERE n.is_archived = 0"
    ).fetchall():
        s, o = r["subj_id"], r["obj_id"]
        if s not in usable or o not in usable:
            continue
        (s_name, s_kind), (o_name, o_kind) = node[s], node[o]
        rel = {"s": s_name, "s_kind": s_kind, "p": r["pred"], "o": o_name, "o_kind": o_kind}
        weight = PRED_WEIGHT.get(r["pred"], 1.0)
        for a in notes_of[s]:
            for b in notes_of[o]:
                if a != b:
                    pairs[_key(a, b)].add(weight, rel)

    return dict(pairs)
