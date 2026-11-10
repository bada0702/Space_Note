"""지식 그래프 검색 — 질문에서 출발 개념을 찾고 관계를 따라 넓혀 노트 점수를 매긴다.

설계: docs/superpowers/specs/2026-10-03-knowledge-graph-rag-design.md (3. 검색)
"""
import math
import re
from dataclasses import dataclass, field

from services.graph_extraction import VALID_STRUCT_SQL
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


def mentions(norm: str, qnorm: str, grams: set[str]) -> bool:
    """정규화한 이름 norm이 본문(qnorm, 영문 n-gram grams)에 나오는가.

    영문·숫자만인 이름은 단어 경계를 지킨다 ('ai'가 'mail'에 걸리지 않게), 그 외는 2자 이상 부분 일치.
    """
    if _ASCII.fullmatch(norm):
        return norm in grams
    return len(norm) >= 2 and norm in qnorm


def match_seeds(conn, query: str) -> dict[str, ConceptHit]:
    """질문에 이름·동의어가 들어 있는 개념 → 출발 개념 (점수 1.0)."""
    if not query.strip():
        return {}
    qnorm = norm_name(query)
    grams = _query_ngrams(query)
    rows = conn.execute(
        "SELECT a.norm AS norm, a.alias AS alias, c.id AS id, c.name AS name "
        "FROM concept_aliases a JOIN concepts c ON c.id = a.concept_id"
    ).fetchall()
    matched = [r for r in rows if mentions(r["norm"], qnorm, grams)]
    seeds: dict[str, ConceptHit] = {}
    for r in matched:
        # 더 긴 일치('그래프 DB')에 포함된 짧은 동의어('DB')는 다른 개념을 가리키면 버린다
        if any(r["norm"] != o["norm"] and r["norm"] in o["norm"] and r["id"] != o["id"] for o in matched):
            continue
        if r["id"] not in seeds:
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
            f"WHERE (r.subj_id IN ({ph}) OR r.obj_id IN ({ph})) "
            f"AND cs.kind != 'literal' AND co.kind != 'literal' "  # 값 노드는 노트 안 정보일 뿐
            f"AND {VALID_STRUCT_SQL} "
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


def idf(total: int, df: int) -> float:
    """개념의 희소성 — 노트 total개 중 df개에 나오면 log(1 + total/df)."""
    return math.log(1 + total / df)


def score_notes(conn, concepts: dict[str, ConceptHit],
                category_id: str | None = None, exclude_id: str | None = None) -> dict[str, NoteHit]:
    """개념 점수 → 노트 점수. 노트에서의 중요도(weight)와 개념의 희소성(IDF)을 곱한다.

    출발 개념 기여는 모두 더하고, 관계로 넓힌 개념은 가장 큰 하나만 더한다.
    이웃 개념을 여럿 가진 노트가 합산만으로 질문 개념을 직접 다룬 노트를 앞지르지 않게.
    """
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
    seed_sum: dict[str, float] = {}
    expanded_max: dict[str, float] = {}
    best: dict[str, tuple[float, ConceptHit]] = {}
    for r in rows:
        hit = concepts[r["cid"]]
        nid = r["note_id"]
        contrib = hit.score * (r["w"] / 3) * idf(total, df[r["cid"]])
        if hit.path:
            expanded_max[nid] = max(expanded_max.get(nid, 0.0), contrib)
        else:
            seed_sum[nid] = seed_sum.get(nid, 0.0) + contrib
        if nid not in best or contrib > best[nid][0]:
            best[nid] = (contrib, hit)
    return {
        nid: NoteHit(seed_sum.get(nid, 0.0) + expanded_max.get(nid, 0.0), hit)
        for nid, (_, hit) in best.items()
    }


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


def aliases_of(conn, names: list[str]) -> list[str]:
    """개념 이름들의 동의어 — 노트 본문에는 이름 대신 동의어('Embedding' → '임베딩')로 적혀 있을 수 있다."""
    if not names:
        return []
    ph = ",".join("?" * len(names))
    rows = conn.execute(
        f"SELECT DISTINCT a.alias AS alias FROM concept_aliases a JOIN concepts c ON c.id = a.concept_id "
        f"WHERE c.name IN ({ph})",
        names,
    ).fetchall()
    return [r["alias"] for r in rows]


def graph_note_scores(conn, query: str, category_id: str | None = None, exclude_id: str | None = None,
                      context_note_id: str | None = None) -> dict[str, NoteHit]:
    seeds = match_seeds(conn, query)
    for cid, hit in context_seeds(conn, context_note_id).items():
        seeds.setdefault(cid, hit)
    if not seeds:
        return {}
    return score_notes(conn, expand(conn, seeds), category_id, exclude_id)
