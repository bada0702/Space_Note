import re
from pathlib import Path

from config import settings

_SAFE = re.compile(r"[^\w \-]", re.UNICODE)


def clean_grounding_markers(text: str) -> str:
    if not text:
        return text
    # \ue200cite\ue202...\ue201 및 \ue200i\ue202...\ue201 등 구글 제미나이 참조 블록 제거
    cleaned = re.sub(r"[\ue200][a-zA-Z0-9]+[\ue202][^\ue201]*[\ue201]", "", text)
    # 개별 제미나이 제어 문자 \ue200 ~ \ue207 제거
    cleaned = re.sub(r"[\ue200-\ue207]", "", cleaned)
    return cleaned


def safe_filename(title: str) -> str:
    """파일명 안전화: 영숫자(유니코드)/공백/하이픈만 허용, 경로 구분자 제거."""
    cleaned = _SAFE.sub("", title).strip()
    return cleaned or "untitled"


def md_path(title: str) -> Path:
    return settings.VAULT_DIR / f"{safe_filename(title)}.md"


def write_md(title: str, content: str, tags: list[str], existing_path: str | None = None) -> str:
    """노트를 .md로 내보내기 (Obsidian 호환 frontmatter). 절대경로 문자열 반환.
    existing_path의 파일이 아직 있으면(제목 안 바뀐 일반 수정) 그 파일에 그대로 덮어쓴다 —
    safe_filename()이 원본 파일명(예: 점 포함)과 다른 이름을 만들어 새 파일이 생기는 걸 막기 위함.
    existing_path가 없거나 이미 삭제된 상태면(신규 노트 또는 제목 변경 후) 그 폴더(없으면 VAULT_DIR
    최상위)에 제목 기준으로 새 파일명을 만든다."""
    if existing_path and Path(existing_path).exists():
        path = Path(existing_path)
    else:
        parent = Path(existing_path).parent if existing_path else settings.VAULT_DIR
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / f"{safe_filename(title)}.md"
    # 항상 VAULT_DIR 내부인지 보장 (하위 폴더 포함)
    resolved = path.resolve()
    vault_resolved = settings.VAULT_DIR.resolve()
    if vault_resolved != resolved and vault_resolved not in resolved.parents:
        raise ValueError("path escapes vault")

    # 제미나이 citation/grounding 문자 제거
    content = clean_grounding_markers(content)

    tag_line = ", ".join(tags)
    frontmatter = f"---\ntags: [{tag_line}]\n---\n\n"
    path.write_text(frontmatter + content, encoding="utf-8")
    return str(path)


def delete_md(path: str) -> None:
    """저장된 노트의 실제 경로(하위 폴더 포함)를 받아 삭제한다."""
    p = Path(path)
    if p.exists():
        p.unlink()


def sync_db_with_vault() -> None:
    """
    VAULT_DIR 내의 모든 .md 파일을 스캔하여 SQLite DB와 동기화합니다.
    1. 디렉토리 내 모든 .md 파일 목록을 가져옴.
    2. 각 파일의 내용을 읽어 frontmatter와 본문을 파싱.
    3. DB에 해당 노트가 없으면 생성, 있으면 내용 비교 후 다르면 업데이트.
    4. DB에는 존재하지만 디렉토리에는 없는 노트는 삭제.
    """
    import uuid
    import json
    import logging
    from datetime import datetime, timezone
    from db import get_conn
    from services.tagparse import extract_tags
    from services.textnorm import norm_name
    
    logger = logging.getLogger(__name__)
    vault_dir = Path(settings.VAULT_DIR)
    if not vault_dir.exists():
        vault_dir.mkdir(parents=True, exist_ok=True)
        return

    logger.info(f"Starting DB sync with vault directory: {vault_dir}")

    # 1. 스캔할 파일들 (하위 폴더 포함 재귀 스캔)
    md_files = list(vault_dir.rglob("*.md"))
    scanned_paths = set()

    with get_conn() as conn:
        # 현재 DB에 있는 모든 노트를 가져옴
        db_notes = conn.execute("SELECT id, path, title, content, tags, category_id FROM notes").fetchall()
        db_notes_by_path = {}
        for row in db_notes:
            path_str = row["path"]
            if path_str not in db_notes_by_path:
                db_notes_by_path[path_str] = []
            db_notes_by_path[path_str].append(dict(row))

        # vault_dir 바로 아래 폴더명 = 카테고리명. 없는 카테고리는 여기서 만든다.
        category_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
        vault_dir_resolved = vault_dir.resolve()

        def _category_id_for(md_path: Path) -> str | None:
            try:
                rel_parts = md_path.resolve().relative_to(vault_dir_resolved).parts
            except ValueError:
                return None
            if len(rel_parts) < 2:
                return None  # vault 최상위에 바로 있는 파일은 카테고리 없음
            name = rel_parts[0]
            if name not in category_ids:
                cid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO categories (id, name, color, sort_order, created_at) "
                    "VALUES (?, ?, NULL, 0, ?)",
                    (cid, name, datetime.now(timezone.utc).isoformat()),
                )
                logger.info(f"Created category from vault folder: {name}")
                category_ids[name] = cid
            return category_ids[name]

        for path in md_files:
            abs_path = str(path.resolve())
            scanned_paths.add(abs_path)
            
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read file {path}: {e}")
                continue

            # 제미나이 control 문자 및 citation 제거 후 파일 재기록
            cleaned_content = clean_grounding_markers(content)
            if cleaned_content != content:
                try:
                    logger.info(f"Cleaning Gemini grounding markers in file: {path}")
                    path.write_text(cleaned_content, encoding="utf-8")
                    content = cleaned_content
                except Exception as e:
                    logger.error(f"Failed to rewrite cleaned file {path}: {e}")

            # Frontmatter 파싱
            tags = []
            body = content
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    body = parts[2].lstrip()
                    # tags: [a, b, c] 형식 파싱
                    list_match = re.search(r"tags:\s*\[(.*?)\]", frontmatter)
                    if list_match:
                        tags = [t.strip() for t in list_match.group(1).split(",") if t.strip()]

            title = path.stem
            word_count = len(body.split())
            category_id = _category_id_for(path)

            # 파일 수정 시간
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            ctime = datetime.fromtimestamp(path.stat().st_ctime, tz=timezone.utc).isoformat()

            if abs_path in db_notes_by_path:
                # 중복 항목이 있으면 첫 번째만 살리고 나머지는 제거
                notes_list = db_notes_by_path[abs_path]
                db_note = notes_list[0]
                
                # 중복 제거
                if len(notes_list) > 1:
                    logger.info(f"Removing duplicate DB entries for path: {abs_path}")
                    for dup in notes_list[1:]:
                        dup_id = dup["id"]
                        conn.execute("DELETE FROM notes WHERE id = ?", (dup_id,))
                        conn.execute("DELETE FROM entities WHERE note_id = ?", (dup_id,))
                        conn.execute("DELETE FROM tags WHERE note_id = ?", (dup_id,))
                        conn.execute("DELETE FROM routes WHERE note_a = ? OR note_b = ?", (dup_id, dup_id))

                # 카테고리가 아직 없는 노트(신규 임포트 등)만 폴더 기준으로 채워준다 —
                # 이미 지정된 카테고리(수동 변경 포함)는 재동기화로 덮어쓰지 않는다.
                if db_note["category_id"] is None and category_id is not None:
                    conn.execute(
                        "UPDATE notes SET category_id = ? WHERE id = ?",
                        (category_id, db_note["id"]),
                    )

                db_tags = json.loads(db_note["tags"])

                if (db_note["title"] != title or
                    db_note["content"] != body or 
                    set(db_tags) != set(tags)):
                    
                    logger.info(f"Updating note in DB: {title} ({abs_path})")
                    conn.execute(
                        "UPDATE notes SET title = ?, content = ?, tags = ?, word_count = ?, modified_at = ?, analysis_status = 'pending' "
                        "WHERE id = ?",
                        (title, body, json.dumps(tags), word_count, mtime, db_note["id"])
                    )
                    conn.execute("DELETE FROM tags WHERE note_id = ?", (db_note["id"],))
                    for tag in extract_tags(body):
                        conn.execute(
                            "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), db_note["id"], tag, norm_name(tag), mtime),
                        )
            else:
                # DB에 없는 파일이면 추가
                nid = str(uuid.uuid4())
                logger.info(f"Adding new note to DB: {title} ({abs_path})")
                conn.execute(
                    "INSERT INTO notes (id, path, title, content, category_id, tags, word_count, analysis_status, created_at, modified_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                    (nid, abs_path, title, body, category_id, json.dumps(tags), word_count, ctime, mtime)
                )
                for tag in extract_tags(body):
                    conn.execute(
                        "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), nid, tag, norm_name(tag), mtime),
                    )

        # 4. 파일시스템에서 사라진 노트를 DB에서 삭제 (대규모 데이터 유실 방지 오프라인 세이프가드 추가)
        if len(scanned_paths) > 0:
            for db_path, db_notes_list in db_notes_by_path.items():
                if db_path not in scanned_paths:
                    for db_note in db_notes_list:
                        nid = db_note["id"]
                        logger.info(f"Deleting note from DB (file not found): {db_note['title']} ({db_path})")
                        conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
                        conn.execute("DELETE FROM entities WHERE note_id = ?", (nid,))
                        conn.execute("DELETE FROM tags WHERE note_id = ?", (nid,))
                        conn.execute("DELETE FROM routes WHERE note_a = ? OR note_b = ?", (nid, nid))
        else:
            if len(db_notes_by_path) > 0:
                logger.warning("Vault directory is empty or scanned files count is 0. Skipping mass deletion of DB notes to prevent data loss.")
                
    logger.info("DB sync with vault directory completed.")
