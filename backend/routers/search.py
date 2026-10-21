from itertools import combinations
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter

from db import get_conn
from services.ontology_routes import ontology_pairs
from services.textnorm import norm_name

router = APIRouter()


@router.get("/search")
def search(q: str = ""):
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, category_id, created_at, modified_at FROM notes "
            "WHERE (title LIKE ? OR content LIKE ?) AND is_archived = 0 "
            "ORDER BY modified_at DESC LIMIT 50",
            (like, like),
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
    """엔티티/태그를 공유하는 노트들을 발견(discovery)으로 반환.

    note_id가 주어지면 해당 노트와 엔티티 또는 태그를 공유하는 다른 노트들을,
    없으면 엔티티·태그가 있는 모든 노트를 공유 항목 수 기준으로 반환한다.
    엔티티와 태그는 같은 텍스트라도 서로 다른 개념이므로 nkey에
    'e:'/'t:' 접두사를 붙여 네임스페이스를 분리한다.
    """
    with get_conn() as conn:
        if note_id:
            # 표기 차이를 흡수한 정규화 키(norm)로 매칭
            mine_e = conn.execute(
                "SELECT DISTINCT norm FROM entities WHERE note_id = ?", (note_id,)
            ).fetchall()
            mine_t = conn.execute(
                "SELECT DISTINCT norm FROM tags WHERE note_id = ?", (note_id,)
            ).fetchall()
            norms_e = [r["norm"] for r in mine_e if r["norm"]]
            norms_t = [r["norm"] for r in mine_t if r["norm"]]
            rows = []  # 키워드가 없어도 아래에서 온톨로지 연결은 찾는다
            if norms_e:
                placeholders = ",".join("?" for _ in norms_e)
                rows += conn.execute(
                    f"SELECT e.note_id AS note_id, e.name AS name, "
                    f"'e:' || e.norm AS nkey, n.title AS title, "
                    f"n.category_id AS category_id, n.modified_at AS modified_at "
                    f"FROM entities e JOIN notes n ON n.id = e.note_id "
                    f"WHERE e.norm IN ({placeholders}) AND e.note_id != ? "
                    f"AND n.is_archived = 0",
                    (*norms_e, note_id),
                ).fetchall()
            if norms_t:
                placeholders = ",".join("?" for _ in norms_t)
                rows += conn.execute(
                    f"SELECT t.note_id AS note_id, t.tag AS name, "
                    f"'t:' || t.norm AS nkey, n.title AS title, "
                    f"n.category_id AS category_id, n.modified_at AS modified_at "
                    f"FROM tags t JOIN notes n ON n.id = t.note_id "
                    f"WHERE t.norm IN ({placeholders}) AND t.note_id != ? "
                    f"AND n.is_archived = 0",
                    (*norms_t, note_id),
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.note_id AS note_id, e.name AS name, "
                "'e:' || e.norm AS nkey, n.title AS title, "
                "n.category_id AS category_id, n.modified_at AS modified_at "
                "FROM entities e JOIN notes n ON n.id = e.note_id "
                "WHERE n.is_archived = 0"
            ).fetchall() + conn.execute(
                "SELECT t.note_id AS note_id, t.tag AS name, "
                "'t:' || t.norm AS nkey, n.title AS title, "
                "n.category_id AS category_id, n.modified_at AS modified_at "
                "FROM tags t JOIN notes n ON n.id = t.note_id "
                "WHERE n.is_archived = 0"
            ).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        d = agg.setdefault(
            r["note_id"],
            {
                "note_id": r["note_id"],
                "title": r["title"],
                "category_id": r["category_id"],
                "modified_at": r["modified_at"],
                "_entities": {},
            },
        )
        # 같은 nkey(엔티티/태그 네임스페이스 + norm)는 하나로 취급, 표시는 최초 등장 이름으로
        d["_entities"].setdefault(r["nkey"], r["name"])

    out = {}
    for d in agg.values():
        ents = sorted(list(set(d["_entities"].values())))
        out[d["note_id"]] = {
            "note_id": d["note_id"],
            "title": d["title"],
            "category_id": d["category_id"],
            "shared_count": len(ents),
            "shared_entities": ents,
            "modified_at": d["modified_at"],
            "kind": "keyword",
            "relations": [],
        }
    scores: dict[str, float] = {}
    if note_id:
        # 온톨로지로 이어진 노트 — 키워드를 하나도 공유하지 않아도 포함
        with get_conn() as conn:
            for (a, b), pair in ontology_pairs(conn).items():
                if note_id not in (a, b):
                    continue
                other = b if a == note_id else a
                item = out.get(other)
                if item is None:
                    row = conn.execute(
                        "SELECT title, category_id, modified_at FROM notes WHERE id = ?", (other,)
                    ).fetchone()
                    item = out[other] = {
                        "note_id": other, "title": row["title"], "category_id": row["category_id"],
                        "shared_count": 0, "shared_entities": [], "modified_at": row["modified_at"],
                    }
                item["kind"] = "ontology"
                item["relations"] = pair.relations
                scores[other] = pair.score
    result = list(out.values())
    result.sort(
        key=lambda x: (scores.get(x["note_id"], 0.0), x["shared_count"], x["modified_at"]),
        reverse=True,
    )
    return result


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


@router.get("/discoveries/routes")
def discovery_routes():
    """엔티티/태그를 공유하는 노트 쌍을 항로(route)로 반환 — 성도의 연결선 렌더링용.

    엔티티와 태그는 같은 텍스트라도 서로 다른 개념이므로 'e:'/'t:' 접두사로
    네임스페이스를 분리한 뒤 합쳐서(union) 아래 상한 로직에 함께 태운다.
    """
    with get_conn() as conn:
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
        crows = conn.execute(
            "SELECT r.note_a AS note_a, r.note_b AS note_b FROM routes r "
            "JOIN notes na ON na.id = r.note_a AND na.is_archived = 0 "
            "JOIN notes nb ON nb.id = r.note_b AND nb.is_archived = 0"
        ).fetchall()
        onto = ontology_pairs(conn)

    norm_notes: dict[str, set[str]] = defaultdict(set)
    norm_display: dict[str, str] = {}
    for r in erows:
        key = f"e:{r['norm']}"
        norm_notes[key].add(r["note_id"])
        norm_display.setdefault(key, r["name"])
    for r in trows:
        key = f"t:{r['norm']}"
        norm_notes[key].add(r["note_id"])
        norm_display.setdefault(key, r["name"])

    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for norm, note_ids in norm_notes.items():
        if len(note_ids) < 2:
            continue
        display = norm_display[norm]
        for a, b in combinations(sorted(note_ids), 2):
            pairs[(a, b)].add(display)

    by_note: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in set(pairs) | set(onto):
        by_note[key[0]].append(key)
        by_note[key[1]].append(key)

    # 노트마다 온톨로지 항로(점수순)를 먼저, 남는 자리에 키워드 항로(공유 수순)
    keep: set[tuple[str, str]] = set()
    for note_id, keys in by_note.items():
        keys.sort(
            key=lambda k: (k in onto, onto[k].score if k in onto else 0.0, len(pairs.get(k, ()))),
            reverse=True,
        )
        keep.update(keys[:_MAX_ROUTES_PER_NOTE])

    confirmed = {(r["note_a"], r["note_b"]) for r in crows}
    # 확정 항로는 발견 쌍에서 사라져도 유지한다 — 사용자의 명시적 선택이므로
    # AI 재계산에 좌우되지 않는다.
    all_keys = sorted(keep | confirmed)
    return [
        {
            "note_a": a,
            "note_b": b,
            "shared_entities": sorted(pairs.get((a, b), set())),
            "confirmed": (a, b) in confirmed,
            "kind": "ontology" if (a, b) in onto else "keyword",
            "relations": onto[(a, b)].relations if (a, b) in onto else [],
        }
        for a, b in all_keys
    ]
