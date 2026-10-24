"""Regression tests for P4-1 (verification report): field match must be mandatory
and short/generic strings must not produce false-positive matches."""

from resources_catalog import match_references


class TestMatchReferences:
    def test_unrelated_field_does_not_match_on_course_text_alone(self):
        # Repro: field="UX 디자인", course="기초" previously matched the SQL doc
        # (category "데이터 분석 / SQL 기초") purely because "기초" is a shared
        # course-name substring, even though the fields are unrelated.
        assert match_references("UX 디자인", "기초") == []

    def test_matching_field_does_not_pull_in_a_different_fields_course(self):
        # Repro: field="Python", course="기초" previously also matched the SQL doc.
        matches = match_references("Python", "기초")
        assert matches
        # Phase 6C: a document matches through its category or its tags, never through the course alone.
        assert all("python" in (m["category"] + " " + " ".join(m.get("tags", []))).lower() for m in matches)
        assert "doc_006" not in {m["id"] for m in matches}

    def test_single_character_field_does_not_match_anything(self):
        # Repro: field="a" previously matched 4 JavaScript/Next.js docs via substring.
        assert match_references("a", "") == []

    def test_two_character_field_does_not_match_anything(self):
        assert match_references("AI", "") == []

    def test_substring_of_an_unrelated_field_does_not_match(self):
        # Repro: field="Java" previously matched the "JavaScript" catalog entries
        # because "java" is a plain substring of "javascript". Since Phase 6C there are real Java
        # link documents, so "Java" matches those - and still never a JavaScript document.
        matches = match_references("Java", "")
        assert matches
        assert all("javascript" not in m["category"].lower() for m in matches)
        assert {m["id"] for m in matches} == {"link_014", "link_015"}

    def test_shared_generic_suffix_does_not_cross_match_unrelated_fields(self):
        # "Python 개발", "웹 개발", and "백엔드 개발" all share the generic word
        # "개발" ("development") - a naive shared-token check matched all three
        # for a "Python 개발" query. Only the Python docs should match.
        matches = match_references("Python 개발", "기본문법")
        assert 3 <= len(matches) <= 5
        assert {"doc_001", "doc_002", "doc_003"} <= {m["id"] for m in matches}
        assert all("python" in (m["category"] + " " + " ".join(m.get("tags", []))).lower() for m in matches)
        assert not {m["id"] for m in matches} & {"doc_004", "doc_005", "doc_006"}

    def test_real_field_still_matches_its_own_catalog_entries(self):
        matches = match_references("Python 개발", "기본문법")
        assert 3 <= len(matches) <= 5
        assert {"doc_001", "doc_002", "doc_003"} <= {m["id"] for m in matches}
        assert all("python" in (m["category"] + " " + " ".join(m.get("tags", []))).lower() for m in matches)
        assert not {m["id"] for m in matches} & {"doc_004", "doc_005", "doc_006"}

    def test_no_match_for_genuinely_unrelated_field(self):
        assert match_references("우주공학", "로켓 설계") == []
