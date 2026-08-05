import pytest

from services import extraction


pytestmark = pytest.mark.skipif(
    extraction.kiwi is None, reason="kiwipiepy not installed"
)

COMPOUND_WORDS = [
    "프론트엔드", "백엔드", "마이크로서비스", "오픈소스",
    "다크모드", "라이트모드", "핫픽스", "빌드업", "엔드포인트",
    "메타데이터", "북마크",
]


@pytest.mark.parametrize("word", COMPOUND_WORDS)
def test_tech_compound_tokenizes_as_single_word(word):
    tokens = extraction.kiwi.tokenize(word)
    assert len(tokens) == 1
    assert tokens[0].form == word


def test_extract_entities_python_keeps_compounds_intact():
    content = (
        "프론트엔드와 백엔드 사이 엔드포인트를 정도 디버깅했고, "
        "다크모드/라이트모드 전환 버그를 핫픽스로 처리했다. "
        "오픈소스 마이크로서비스 빌드업 회고와 메타데이터 북마크 정리도 함께 진행."
    )
    names = [e["name"] for e in extraction.extract_entities_python(content)]
    for word in COMPOUND_WORDS:
        assert word in names
    # 조각난 단어가 별도 엔티티로 새어 나오면 안 된다
    broken_fragments = {"프론트", "엔드", "마이크로", "오픈", "다크", "라이트",
                         "핫", "빌", "드", "업", "픽스", "소스", "모드", "포인트"}
    assert not (broken_fragments & set(names))
