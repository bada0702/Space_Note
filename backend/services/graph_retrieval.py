"""지식 그래프 검색 — 질문에서 출발 개념을 찾고 관계를 따라 넓혀 노트 점수를 매긴다.

설계: docs/superpowers/specs/2026-10-03-knowledge-graph-rag-design.md (3. 검색)
"""
import math
import re
from dataclasses import dataclass, field

from services.textnorm import norm_name

MAX_HOPS = 2
HOP_DECAY = 0.5
CONTEXT_SEED_SCORE = 0.5
HUB_DEGREE = 50
FRONTIER_LIMIT = 30
PRED_WEIGHT = {"관련있다": 0.6}  # 나머지 관계는 1.0

_ASCII = re.compile(r"[a-z0-9]+")


@dataclass
class ConceptHit:
    score: float
    name: str
    # 출발 개념에서 이 개념까지의 경로: [(이전 개념 이름, 관계, 방향 '→' 또는 '←')]
    path: list[tuple[str, str, str]] = field(default_factory=list)
    seed_label: str = ""  # 출발 개념이 질문/현재 노트 어디서 왔는지


@dataclass
class NoteHit:
    score: float
    concept: ConceptHit


def _query_ngrams(query: str, max_n: int = 4) -> set[str]:
    """영문·숫자 토큰의 연속 n-gram(구분자 제거) — 'vector db' → {'vector','db','vectordb'}."""
    tokens = _ASCII.findall(query.casefold())
    grams: set[str] = set()
    for i in range(len(tokens)):
        for n in range(1, max_n + 1):
            if i + n <= len(tokens):
                grams.add("".join(tokens[i:i + n]))
    return grams


def match_seeds(conn, query: str) -> dict[str, ConceptHit]:
    """질문에 이름·동의어가 들어 있는 개념 → 출발 개념 (점수 1.0)."""
    if not query.strip():
        return {}
    qnorm = norm_name(query)
    grams = _query_ngrams(query)
    seeds: dict[str, ConceptHit] = {}
    rows = conn.execute(
        "SELECT a.norm AS norm, a.alias AS alias, c.id AS id, c.name AS name "
        "FROM concept_aliases a JOIN concepts c ON c.id = a.concept_id"
    ).fetchall()
    for r in rows:
        n = r["norm"]
        if _ASCII.fullmatch(n):
            hit = n in grams          # 영문은 단어 경계를 지킨다 ('ai'가 'mail'에 걸리지 않게)
        else:
            hit = len(n) >= 2 and n in qnorm
        if hit and r["id"] not in seeds:
            seeds[r["id"]] = ConceptHit(1.0, r["name"], [], seed_label=r["name"])
    return seeds


def context_seeds(conn, note_id: str | None) -> dict[str, ConceptHit]:
    """현재 열린 노트의 핵심 개념(weight ≥ 2) → 약한 출발 개념."""
    if not note_id:
        return {}
    rows = conn.execute(
        "SELECT c.id AS id, c.name AS name FROM note_concepts nc JOIN concepts c ON c.id = nc.concept_id "
        "WHERE nc.note_id = ? AND nc.weight >= 2",
        (note_id,),
    ).fetchall()
    return {r["id"]: ConceptHit(CONTEXT_SEED_SCORE, r["name"], [], seed_label=r["name"]) for r in rows}


def _degrees(conn, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT cid, COUNT(DISTINCT other) AS d FROM ("
        f" SELECT subj_id AS cid, obj_id AS other FROM relations WHERE subj_id IN ({ph})"
        f" UNION ALL SELECT obj_id, subj_id FROM relations WHERE obj_id IN ({ph})"
        f") GROUP BY cid",
        (*ids, *ids),
    ).fetchall()
    return {r["cid"]: r["d"] for r in rows}


def expand(conn, seeds: dict[str, ConceptHit]) -> dict[str, ConceptHit]:
    """관계를 방향 무관하게 최대 MAX_HOPS단계 따라가며 개념 점수를 퍼뜨린다."""
    hits = dict(seeds)
    frontier = list(seeds)
    for _ in range(MAX_HOPS):
        deg = _degrees(conn, frontier)
        frontier = [c for c in frontier if deg.get(c, 0) <= HUB_DEGREE]  # 허브는 넘어가지 않음
        if not frontier:
            break
        ph = ",".join("?" * len(frontier))
        rows = conn.execute(
            f"SELECT r.subj_id AS s, r.pred AS p, r.obj_id AS o, COUNT(*) AS n, "
            f" cs.name AS s_name, co.name AS o_name "
            f"FROM relations r JOIN concepts cs ON cs.id = r.subj_id JOIN concepts co ON co.id = r.obj_id "
            f"WHERE r.subj_id IN ({ph}) OR r.obj_id IN ({ph}) "
            f"GROUP BY r.subj_id, r.pred, r.obj_id",
            (*frontier, *frontier),
        ).fetchall()
        fset = set(frontier)
        updated: dict[str, ConceptHit] = {}
        for r in rows:
            conf = 1 + 0.2 * math.log(r["n"])
            weight = PRED_WEIGHT.get(r["p"], 1.0) * conf * HOP_DECAY
            # 양방향: s→o 와 o←s
            for src, dst, dst_name, arrow in (
                (r["s"], r["o"], r["o_name"], "→"),
                (r["o"], r["s"], r["s_name"], "←"),
            ):
                if src not in fset:
                    continue
                base = hits[src]
                score = base.score * weight
                cur = hits.get(dst)
                if cur is not None and cur.score >= score:
                    continue
                hit = ConceptHit(
                    score, dst_name,
                    [*base.path, (base.name, r["p"], arrow)],
                    seed_label=base.seed_label,
                )
                hits[dst] = hit
                updated[dst] = hit
        frontier = sorted(updated, key=lambda c: updated[c].score, reverse=True)[:FRONTIER_LIMIT]
    return hits


def _scope(category_id: str | None, exclude_id: str | None) -> tuple[str, list]:
    clause, params = "n.is_archived = 0", []
    if category_id:
        clause += " AND n.category_id = ?"
        params.append(category_id)
    if exclude_id:
        clause += " AND n.id != ?"
        params.append(exclude_id)
    return clause, params


def score_notes(conn, concepts: dict[str, ConceptHit],
                category_id: str | None = None, exclude_id: str | None = None) -> dict[str, NoteHit]:
    """개념 점수 → 노트 점수. 노트에서의 중요도(weight)와 개념의 희소성(IDF)을 곱한다."""
    if not concepts:
        return {}
    scope_n, scope_params = _scope(category_id, exclude_id)
    total = conn.execute(f"SELECT COUNT(*) FROM notes n WHERE {scope_n}", scope_params).fetchone()[0] or 1
    ids = list(concepts)
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT nc.note_id AS note_id, nc.concept_id AS cid, nc.weight AS w "
        f"FROM note_concepts nc JOIN notes n ON n.id = nc.note_id "
        f"WHERE nc.concept_id IN ({ph}) AND {scope_n}",
        (*ids, *scope_params),
    ).fetchall()
    df: dict[str, int] = {}
    for r in rows:
        df[r["cid"]] = df.get(r["cid"], 0) + 1
    notes: dict[str, NoteHit] = {}
    best: dict[str, float] = {}
    for r in rows:
        hit = concepts[r["cid"]]
        contrib = hit.score * (r["w"] / 3) * math.log(1 + total / df[r["cid"]])
        nh = notes.get(r["note_id"])
        if nh is None:
            notes[r["note_id"]] = NoteHit(contrib, hit)
            best[r["note_id"]] = contrib
        else:
            nh.score += contrib
            if contrib > best[r["note_id"]]:
                best[r["note_id"]] = contrib
                nh.concept = hit
    return notes


def format_path(hit: ConceptHit) -> str:
    """ConceptHit → "'RAG' —사용한다→ '임베딩'" (출발 개념만이면 "개념 'RAG'")."""
    if not hit.path:
        return f"개념 '{hit.name}'"
    parts = [f"'{hit.path[0][0]}'"]
    for i, (_, pred, arrow) in enumerate(hit.path):
        nxt = hit.path[i + 1][0] if i + 1 < len(hit.path) else hit.name
        parts.append(f"—{pred}→ '{nxt}'" if arrow == "→" else f"←{pred}— '{nxt}'")
    return " ".join(parts)


def path_terms(hit: ConceptHit) -> list[str]:
    """발췌 위치를 잡을 때 쓸 경로상의 개념 이름들 (노트에 들어 있는 개념이 먼저)."""
    return [hit.name, *[p[0] for p in reversed(hit.path)]]


def graph_note_scores(conn, query: str, category_id: str | None = None, exclude_id: str | None = None,
                      context_note_id: str | None = None) -> dict[str, NoteHit]:
    seeds = match_seeds(conn, query)
    for cid, hit in context_seeds(conn, context_note_id).items():
        seeds.setdefault(cid, hit)
    if not seeds:
        return {}
    return score_notes(conn, expand(conn, seeds), category_id, exclude_id)
