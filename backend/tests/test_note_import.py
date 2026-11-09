import io
import zipfile

from config import settings
from conftest import AUTH


def _cats(client):
    return {c["name"]: c["id"] for c in client.get("/categories", headers=AUTH).json()}


def _notes(client):
    return [client.get(f"/notes/{n['id']}", headers=AUTH).json() for n in client.get("/notes", headers=AUTH).json()]


def test_import_files_galaxy_from_first_folder(client):
    files = [
        {"path": "우주/별.md", "content": "---\ntags: [a, b]\n---\n\n본문 #태그"},
        {"path": "우주/깊은/행성.md", "content": "깊은 폴더"},
        {"path": "밖.md", "content": "미분류"},
        {"path": "우주/그림.png", "content": "x"},
        {"path": ".obsidian/설정.md", "content": "숨김"},
    ]
    r = client.post("/notes/import/files", json={"files": files}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 3
    assert body["skipped"] == []

    cats = _cats(client)
    assert set(cats) == {"우주"}
    by_title = {n["title"]: n for n in _notes(client)}
    assert by_title["별"]["category_id"] == cats["우주"]
    assert by_title["별"]["content"] == "본문 #태그"
    assert by_title["별"]["tags"] == ["a", "b"]
    assert by_title["행성"]["category_id"] == cats["우주"]
    assert by_title["밖"]["category_id"] is None
    assert (settings.VAULT_DIR / "우주" / "별.md").exists()
    assert (settings.VAULT_DIR / "밖.md").exists()


def test_import_skips_same_title_in_same_galaxy(client):
    cat = client.post("/categories", json={"name": "우주"}, headers=AUTH).json()
    client.post("/notes", json={"title": "별", "category_id": cat["id"], "content": "원본"}, headers=AUTH)
    client.post("/notes", json={"title": "밖", "content": "원본"}, headers=AUTH)

    files = [
        {"path": "우주/별.md", "content": "새것"},
        {"path": "다른/별.md", "content": "다른 은하는 들어간다"},
        {"path": "밖.md", "content": "미분류 중복"},
        {"path": "다른/x/별.md", "content": "같은 묶음 안 중복"},
    ]
    body = client.post("/notes/import/files", json={"files": files}, headers=AUTH).json()
    assert body["imported"] == 1
    assert sorted(s["path"] for s in body["skipped"]) == ["다른/x/별.md", "밖.md", "우주/별.md"]

    cats = _cats(client)
    assert cats["우주"] == cat["id"]  # 기존 은하 재사용
    contents = sorted(n["content"] for n in _notes(client))
    assert contents == ["다른 은하는 들어간다", "원본", "원본"]


class _Cp949Info(zipfile.ZipInfo):
    __slots__ = ()

    def _encodeFilenameFlags(self):
        return self.filename.encode("cp949"), self.flag_bits


def test_import_zip_with_cp949_names_and_content(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("은하/노트.md", "utf8 본문")
        # Windows 기본 압축: 파일명 UTF-8 플래그 없이 cp949, 본문도 cp949
        # (zipfile은 비ASCII 이름에 UTF-8 플래그를 켜므로 인코딩 함수를 바꿔 cp949 바이트를 그대로 쓴다)
        zf.writestr(_Cp949Info("은하/옛날.md"), "한글 본문".encode("cp949"))
        zf.writestr("__MACOSX/은하/._노트.md", "junk")
    r = client.post(
        "/notes/import/zip", content=buf.getvalue(), headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 2
    by_title = {n["title"]: n for n in _notes(client)}
    assert by_title["옛날"]["content"] == "한글 본문"
    assert set(_cats(client)) == {"은하"}


def test_import_zip_rejects_bad_archive(client):
    r = client.post("/notes/import/zip", content=b"not a zip", headers=AUTH)
    assert r.status_code == 400


def test_import_requires_auth(client):
    assert client.post("/notes/import/files", json={"files": []}).status_code == 401
