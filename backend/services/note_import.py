"""폴더·zip에서 .md 파일을 가져와 노트로 등록한다.

경로의 첫 번째 폴더 이름이 은하(카테고리)가 되고, 폴더 밖 파일은 미분류로 들어간다.
더 깊은 하위 폴더의 노트도 첫 번째 폴더의 은하로 들어간다.
같은 은하에 같은 제목의 노트가 이미 있으면 덮어쓰지 않고 건너뛴다.
"""
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

from config import settings
from db import get_conn
from services import vault
from services.tagparse import extract_tags
from services.textnorm import norm_name

# Obsidian 설정(.obsidian), macOS 압축 찌꺼기(__MACOSX, ._*) 같은 건 노트가 아니다
_JUNK_DIRS = {"__MACOSX"}


def decode_text(data: bytes) -> str:
    """UTF-8(BOM 포함)을 우선하고, 실패하면 레거시 한글 인코딩 cp949로 읽는다."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp949")


def read_zip(data: bytes) -> list[tuple[str, str]]:
    """zip 안의 .md 파일을 (압축 안 경로, 본문) 목록으로 돌려준다. 잘못된 zip이면 zipfile.BadZipFile."""
    files = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # UTF-8 플래그 없는 이름은 zipfile이 cp437로 읽는다 — Windows 기본 압축은 cp949라 되돌린다
            if not info.flag_bits & 0x800:
                try:
                    name = name.encode("cp437").decode("cp949")
                except UnicodeError:
                    pass
            if not name.lower().endswith(".md"):
                continue
            try:
                files.append((name, decode_text(zf.read(info))))
            except UnicodeDecodeError:
                files.append((name, None))
    return files


def import_md_files(files: list[tuple[str, str | None]]) -> dict:
    """(상대 경로, 본문) 목록을 노트로 등록한다. 본문이 None이면 읽기 실패로 건너뛴다."""
    now = datetime.now(timezone.utc).isoformat()
    imported = 0
    skipped: list[dict] = []

    with get_conn() as conn:
        category_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM categories")}
        taken = {
            (r["category_id"], r["title"])
            for r in conn.execute("SELECT category_id, title FROM notes")
        }

        for raw_path, text in files:
            parts = [p for p in PurePosixPath(raw_path.replace("\\", "/")).parts if p not in ("", ".", "..")]
            if (
                not parts
                or not parts[-1].lower().endswith(".md")
                or any(p.startswith(".") or p in _JUNK_DIRS for p in parts)
            ):
                continue
            if text is None:
                skipped.append({"path": raw_path, "reason": "인코딩을 읽을 수 없음"})
                continue

            title = PurePosixPath(parts[-1]).stem
            galaxy = parts[0] if len(parts) > 1 else None
            cid = category_ids.get(galaxy) if galaxy else None
            if (cid, title) in taken:
                skipped.append({"path": raw_path, "reason": "같은 은하에 같은 제목의 노트가 있음"})
                continue

            folder = settings.VAULT_DIR / vault.safe_filename(galaxy) if galaxy else settings.VAULT_DIR
            path = folder / f"{vault.safe_filename(title)}.md"
            if path.exists():
                # DB에 없는 파일이라도 덮어쓰면 원본이 사라진다
                skipped.append({"path": raw_path, "reason": "같은 이름의 파일이 vault에 있음"})
                continue

            if galaxy and cid is None:
                cid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO categories (id, name, color, sort_order, created_at) "
                    "VALUES (?, ?, NULL, 0, ?)",
                    (cid, galaxy, now),
                )
                category_ids[galaxy] = cid

            text = vault.clean_grounding_markers(text)
            tags, body = vault.parse_md(text)
            folder.mkdir(parents=True, exist_ok=True)
            # 원본 frontmatter를 살리도록 파일은 그대로 복사한다 (write_md는 frontmatter를 새로 쓴다)
            path.write_text(text, encoding="utf-8")

            nid = str(uuid.uuid4())
            # 대량 가져오기라 AI 추출은 바로 돌리지 않는다 — 일괄 분석에서 pending을 처리한다
            conn.execute(
                "INSERT INTO notes (id, path, title, content, category_id, tags, "
                "word_count, analysis_status, created_at, modified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (nid, str(path.resolve()), title, body, cid, json.dumps(tags),
                 len(body.split()), now, now),
            )
            for tag in extract_tags(body):
                conn.execute(
                    "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), nid, tag, norm_name(tag), now),
                )
            taken.add((cid, title))
            imported += 1

    return {"imported": imported, "skipped": skipped}
