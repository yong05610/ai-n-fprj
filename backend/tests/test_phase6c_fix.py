"""Phase 6C fix: free-text fields fall back to the course, Korean aliases live in `tags`,
short Latin allow list. Real catalog data, no AI except the fake one in the tutor test."""

import json

import pytest
from fastapi.testclient import TestClient

import resources_catalog
from resources_catalog import load_catalog, match_references
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase6c import _ask, _confirm, _conv, chunk_file, pinned_today  # noqa: F401


def _ids(field, course=""):
    return [d["id"] for d in match_references(field, course)]


WEB = {"link_001", "link_002", "link_003", "link_004", "link_006", "link_010"}


class TestCourseFallback:
    @pytest.mark.parametrize("field,course", [("VIBE CODING", "웹 개발의 기초"), ("VIBE CODING", "웹 개발")])
    def test_free_text_field_uses_the_course(self, field, course):
        ids = _ids(field, course)
        assert 1 <= len(ids) <= 5 and set(ids) <= {d["id"] for d in load_catalog() if "웹" in d.get("tags", [])}
        assert "link_001" in ids

    @pytest.mark.parametrize("field,course", [("웹 개발", "기초"), ("웹 개발의 기초", ""), ("프론트엔드 개발자", "웹 개발의 기초")])
    def test_fields_that_already_match_behave_as_before(self, field, course):
        ids = _ids(field, course)
        assert len(ids) == 5 and set(ids) <= WEB

    def test_a_field_that_matches_is_not_overridden_by_the_course(self):
        assert "link_014" in _ids("Java", "웹 개발") and "link_001" not in _ids("Java", "웹 개발")

    def test_fallback_needs_a_domain_tag_not_just_generic_words(self):
        for course in ("기초", "개발의 기초", "입문 과정", "코딩 학습", "개발 입문"):
            assert match_references("VIBE CODING", course) == []

    def test_fallback_is_exact_so_java_is_not_javascript(self):
        assert set(_ids("VIBE CODING", "Java")) == {"link_014", "link_015"}
        assert "link_014" not in _ids("VIBE CODING", "JavaScript")

    def test_unrelated_field_and_course_stay_empty(self):
        assert match_references("요리", "한식") == []
        assert match_references("요리", "") == [] and match_references("", "한식") == []

    def test_one_letter_korean_domain_word_is_allowed(self):
        assert "link_001" in _ids("VIBE CODING", "웹")

    def test_course_sql_now_finds_sql_documents_changed_expectation(self):
        # was empty before the fix; "UX 디자인" matches nothing, so the course decides
        assert _ids("UX 디자인", "SQL 기초") == ["doc_006", "link_018", "link_017"]
        assert match_references("UX 디자인", "기초") == []  # no domain word in the course


class TestKoreanAliases:
    def test_python_in_korean(self):
        ids = _ids("파이썬", "기초")
        assert {"doc_001", "doc_002", "doc_003"} <= set(ids)
        assert _ids("파이썬 개발", "자료구조")[0] == "doc_002"

    def test_python_documents_rank_above_pandas_and_other_data_documents(self):
        for ids in (_ids("파이썬", "기초"), _ids("Python 개발", "기본문법"), _ids("python")):
            assert ids[:3] and all(i.startswith("doc_") or i == "link_026" for i in ids[:3])
            if "link_022" in ids:
                assert ids.index("link_022") > ids.index("doc_001")

    def test_javascript_in_korean(self):
        assert {"doc_004", "doc_005", "doc_010"} <= set(_ids("자바스크립트", "기초"))
        assert {"doc_004", "doc_005", "doc_010"} <= set(_ids("VIBE CODING", "JS"))  # two-letter "JS" as a field is blocked

    def test_other_aliases(self):
        assert _ids("깃") == ["doc_007", "link_029"]
        assert "doc_008" in _ids("넥스트") and "doc_009" in _ids("fastapi")
        assert "link_006" in _ids("리액트")
        assert "link_012" in _ids("노드") and "link_016" in _ids("도커")

    def test_every_document_has_tags_and_link_tags_keep_the_reviewed_order(self):
        assert all(d["tags"] for d in load_catalog())
        table = {}
        import os

        for line in open(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "phase6c_resource_links.md"), encoding="utf-8"):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) == 7 and c[0].startswith("link_"):
                table[c[0]] = [t.strip() for t in c[5].split(",")]
        for d in load_catalog():
            if d["id"] in table:
                assert d["tags"][: len(table[d["id"]])] == table[d["id"]]  # only aliases were appended

    def test_korean_java_is_still_not_javascript(self):
        assert "doc_004" not in _ids("자바") and "link_014" in _ids("자바")


class TestShortLatinAllowList:
    @pytest.mark.parametrize("field", ["AI", "ai", " AI "])
    def test_ai_matches_the_machine_learning_material(self, field):
        assert _ids(field, "머신러닝") == ["link_025"]

    def test_other_two_letter_latin_fields_stay_blocked(self):
        for field in ("go", "QQ", "js", "a", "c"):
            assert match_references(field, "") == []

    def test_allowed_term_matches_only_as_a_whole_token(self):
        assert resources_catalog._token_matches("aim", "ai") is False
        assert "link_025" not in _ids("AIM")


class TestStopwordParticles:
    def test_generic_word_with_a_particle_is_still_generic(self):
        for token in ("개발의", "기초를", "입문은", "과정에서", "코딩으로"):
            assert resources_catalog._is_stopword(token)
        assert not resources_catalog._is_stopword("기본문법")  # a course name, not "기본" + particle

    def test_stopword_list_is_the_documented_one(self):
        assert resources_catalog.STOPWORDS == frozenset(
            {"개발", "개발자", "기초", "입문", "코딩", "학습", "공부", "과정", "기본", "초급", "강의",
             "development", "developer", "basic", "basics", "beginner", "coding", "study", "course", "learn"}
        )


class TestTutorUsesTheFallback:
    def test_related_links_for_a_free_text_learning(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers, field="VIBE CODING", course="웹 개발의 기초")
        override_ai(FakeAIClient(raws=[_raw({"relevant": True, "answer": "답", "used_source_ids": ["doc_002"], "search_keywords": []})]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers), question="리스트에 값을 추가하는 방법").json()["assistant_message"]
        assert 1 <= len(msg["related_links"]) <= 2
        assert {link["url"] for link in msg["related_links"]} <= {d["url"] for d in load_catalog()}

    def test_references_endpoint_for_a_free_text_learning(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers, field="VIBE CODING", course="웹 개발의 기초").json()["goal"]
        body = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()
        assert body["references"] and body["references_notice"] is None and len(body["search_links"]) == 3
