"""Phase 6C: reviewed link materials, score-based field matching, server-built search links,
tutor follow-up keywords and related links. Fake AI and in-memory store only.

Every URL the user can see is either a value of rag_documents.json or built by the server from a
fixed template - these tests also show that no AI-written URL has a path into a response.
"""

import json
import logging
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import clock
import rag
import resources_catalog
import tutor
from ai_client import MAX_RETRIES
from ai_schemas import AITutorAnswer
from prompts import TUTOR_SYSTEM_PROMPT
from resources_catalog import SEARCH_QUERY_MAX_CHARS, load_catalog, match_references, search_links
from store import get_store
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm as _confirm_base, _other_user

TODAY = date(2026, 10, 24)


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _confirm(client, headers, **kw):
    kw.setdefault("start", "2026-10-24")  # today is pinned to 2026-10-24
    return _confirm_base(client, headers, **kw)


def _ids(field, course=""):
    return [d["id"] for d in match_references(field, course)]


# ----------------------------------------------------------------------------- A. data
class TestLinkDocuments:
    def test_the_catalog_has_ten_old_and_thirty_one_link_only_documents(self):
        docs = load_catalog()
        link_docs = [d for d in docs if d.get("link_only")]
        assert len(docs) == 41 and len(link_docs) == 31
        assert [d["id"] for d in docs if not d.get("link_only")] == [f"doc_{i:03d}" for i in range(1, 11)]

    def test_link_documents_have_the_agreed_shape(self):
        for d in (d for d in load_catalog() if d.get("link_only")):
            assert d["verified"] is True and d["verified_at"] == "2026-10-24"
            assert d["license"] == "링크만 제공(원문 복제 없음)"
            assert d["chunks"] == [] and d["tags"] and d["url"].startswith("https://")
            assert " / " in d["category"] and d["source_name"] and d["title"]

    def test_urls_and_titles_match_the_reviewed_table(self):
        import os

        table = {}
        path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "phase6c_resource_links.md")
        for line in open(path, encoding="utf-8"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 7 and cells[0].startswith("link_"):
                table[cells[0]] = (cells[2], cells[4])
        got = {d["id"]: (d["title"], d["url"]) for d in load_catalog() if d.get("link_only")}
        assert len(table) == 31 and got == table

    def test_the_ten_old_documents_keep_their_data_and_gained_tags_in_the_fix(self):
        old = [d for d in load_catalog() if not d.get("link_only")]
        assert all(d["verified_at"] == "2026-10-19" and d["tags"] and "link_only" not in d for d in old)

    def test_link_only_documents_are_never_searchable_or_a_source(self, tmp_path, monkeypatch):
        chunks = [{"doc_id": "link_022", "chunks": [{"id": "link_022_c1", "text": "판다스 데이터프레임 설명", "keywords": ["판다스"], "verified": True}]}]
        path = tmp_path / "c.json"
        path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("RAG_CHUNKS_PATH", str(path))
        assert rag.search("판다스 데이터프레임") == []

    def test_the_shipped_chunk_file_still_only_points_at_the_ten_old_documents(self):
        entries = json.load(open(rag._DEFAULT_CHUNKS_PATH, encoding="utf-8"))
        assert all(e["doc_id"].startswith("doc_") for e in entries)


# ----------------------------------------------------------------------------- B. matching
class TestMatching:
    def test_free_text_web_field_finds_web_documents(self):
        ids = _ids("웹 프론트엔드 개발자")
        assert ids and all(i.startswith("link_") for i in ids) and len(ids) <= 5
        web = {d["id"] for d in load_catalog() if "프론트엔드" in d.get("tags", [])}
        assert set(ids) <= web

    def test_react_course_ranks_the_react_document_first(self):
        assert _ids("웹 프론트엔드 개발자", "React")[0] == "link_006"

    def test_english_speaking_finds_the_english_documents(self):
        assert _ids("영어 회화") == ["link_030", "link_031"]

    def test_korean_particle_after_a_tag_still_matches(self):
        assert _ids("영어를 공부", "듣기") == ["link_030", "link_031"]

    def test_data_analysis_beginner_finds_pandas_first(self):
        ids = _ids("데이터 분석 입문", "pandas")
        assert ids[0] == "link_022" and "doc_006" in ids

    def test_java_is_not_javascript_in_either_direction(self):
        assert set(_ids("Java")) == {"link_014", "link_015"}
        js = _ids("JavaScript", "비동기 프로그래밍")
        assert "doc_005" in js and "link_014" not in js

    def test_korean_java_is_not_the_javascript_word(self):
        # "자바" followed by four more characters is not "자바 + particle"
        assert resources_catalog._token_matches("자바스크립트", "자바") is False
        assert resources_catalog._token_matches("자바를", "자바") is True
        assert resources_catalog._token_matches("javascript", "java") is False

    def test_short_korean_fields_match_but_short_latin_ones_do_not(self):
        assert _ids("영어") == ["link_030", "link_031"]
        assert _ids("웹") and all(i.startswith("link_") for i in _ids("웹"))
        assert match_references("go", "") == [] and match_references("QQ", "") == []
        assert _ids("AI") == ["link_025"]  # allowed short Latin terms (ai, ui, ux, db, qa) match as whole tokens

    def test_generic_words_alone_never_match(self):
        for field in ("개발 입문", "코딩 기초", "공부 과정", "development basics"):
            assert match_references(field, "개발 기초") == []

    def test_unknown_or_vague_fields_do_not_match(self):
        for field, course in [("VIBE CODING", ""), ("우주공학", "로켓 설계"), ("UX 디자인", "기초"), ("a", ""), ("요리", "한식")]:
            assert match_references(field, course) == []

    def test_course_text_alone_never_matches_across_fields(self):
        # "기본문법" is the course of both a Python and a JavaScript document
        assert "doc_004" not in _ids("Python 개발", "기본문법")
        assert match_references("요리", "한식") == []

    def test_at_most_five_best_score_first_ties_by_id(self):
        docs = match_references("웹 개발", "React")
        assert len(docs) == 5 and docs[0]["id"] == "link_006"

        def score(doc):
            tags = {t for tag in doc.get("tags", []) for t in resources_catalog._topic_tokens(tag)}
            query = resources_catalog._topic_tokens("웹 개발 React")
            return resources_catalog._count_hits(query, tags) + resources_catalog._count_hits(
                query, resources_catalog._topic_tokens(doc["category"])
            )

        query = resources_catalog._topic_tokens("웹 개발 React")
        keys = [(-score(d), resources_catalog._first_tag_hit(query, d.get("tags", [])), d["id"]) for d in docs]
        assert keys == sorted(keys)

    def test_every_returned_document_is_reviewed_and_has_a_url(self):
        for field, course in [("Python 개발", "기본문법"), ("웹 개발", "CSS"), ("Git", "협업"), ("영어", "듣기")]:
            assert all(d["verified"] and d["url"].startswith("https://") for d in match_references(field, course))


# ----------------------------------------------------------------------------- C. search links
class TestSearchLinks:
    def test_three_template_links_with_the_review_warning_in_each_label(self):
        links = search_links("Python 개발", "반복문")
        assert len(links) == 3
        assert all(link["label"].endswith("(검토 전 외부 링크)") for link in links)
        hosts = [urlparse(link["url"]).netloc for link in links]
        assert hosts == ["www.google.com", "www.google.com", "www.youtube.com"]

    def test_query_is_course_then_field_and_the_docs_variant_adds_words(self):
        google, docs, youtube = (parse_qs(urlparse(link["url"]).query) for link in search_links("Python 개발", "반복문"))
        assert google["q"] == ["반복문 Python 개발"] and docs["q"] == ["반복문 Python 개발 공식 문서"]
        assert youtube["search_query"] == ["반복문 Python 개발"]

    def test_extra_terms_are_part_of_the_query(self):
        google = parse_qs(urlparse(search_links("Python 개발", "", ["리스트 컴프리헨션"])[0]["url"]).query)
        assert google["q"] == ["Python 개발 리스트 컴프리헨션"]

    @pytest.mark.parametrize("name", ['C&C++ #1 "고급"', "a&q=evil", "x#frag", 'say "hi"', "50% 할인?", "한글 & English"])
    def test_special_characters_cannot_break_or_inject_parameters(self, name):
        for link in search_links(name, name):
            parsed = urlparse(link["url"])
            assert parsed.fragment == "" and parsed.path in ("/search", "/results")
            params = parse_qs(parsed.query)
            assert list(params) in (["q"], ["search_query"])  # exactly one parameter, nothing injected
            assert name in params["q" if "q" in params else "search_query"][0]
            assert " " not in link["url"] and '"' not in link["url"]

    def test_the_query_is_cut_at_200_characters(self):
        for link in search_links("가" * 500, "나" * 500):
            params = parse_qs(urlparse(link["url"]).query)
            assert len(next(iter(params.values()))[0]) <= SEARCH_QUERY_MAX_CHARS + len(" 공식 문서")
        assert len(parse_qs(urlparse(search_links("가" * 500, "")[0]["url"]).query)["q"][0]) == SEARCH_QUERY_MAX_CHARS

    def test_nothing_to_search_gives_no_links(self):
        assert search_links("", "") == [] and search_links("  ", " ", []) == []


# ----------------------------------------------------------------------------- C. references API
class TestReferencesApi:
    def test_search_links_are_always_present_with_or_without_materials(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers).json()["goal"]
        body = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()
        assert body["references"] and len(body["search_links"]) == 3
        assert set(body["search_links"][0]) == {"label", "url"}
        assert len(body["references"]) <= 5

        other = _confirm(client, consented_headers, course="로켓 설계", field="우주공학").json()["goal"]
        body = client.get(f"/api/goals/{other['id']}/references", headers=consented_headers).json()
        assert body["references"] == [] and body["references_notice"] and len(body["search_links"]) == 3

    def test_the_links_use_the_goals_own_words(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers, field='웹 & "프론트"', course="C#").json()["goal"]
        links = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()["search_links"]
        assert parse_qs(urlparse(links[0]["url"]).query)["q"] == ['C# 웹 & "프론트"']

    def test_ownership_is_still_enforced(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers).json()["goal"]
        assert client.get(f"/api/goals/{goal['id']}/references", headers=_other_user(client)).status_code == 403


# ----------------------------------------------------------------------------- D. tutor
def _ai(answer="꾸준히 짧게 나누어 학습해 보세요.", used=None, keywords=None, relevant=True) -> str:
    return _raw({"relevant": relevant, "answer": answer, "used_source_ids": used or [], "search_keywords": keywords or []})


def _conv(client, headers) -> str:
    return client.post("/api/conversations", headers=headers).json()["id"]


def _ask(client, headers, conv_id, question="동기를 유지하는 요령이 있을까요?", key="k1"):
    return client.post(f"/api/conversations/{conv_id}/messages", json={"content": question, "client_request_id": key}, headers=headers)


@pytest.fixture
def chunk_file(tmp_path, monkeypatch):
    chunks = [
        {
            "doc_id": "doc_002",
            "chunks": [{"id": "doc_002_c1", "text": "리스트는 여러 값을 순서대로 담는 자료형입니다.", "keywords": ["리스트"], "verified": True}],
        }
    ]
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_CHUNKS_PATH", str(path))


class TestKeywordValidation:
    def _validate(self, **kw):
        tutor.validate_tutor_answer(AITutorAnswer(relevant=True, answer="답", **kw), [])

    def test_valid_keywords_pass(self):
        self._validate(search_keywords=["파이썬 반복문", "for 문"])
        self._validate(search_keywords=[])
        self._validate(search_keywords=["가" * 30])

    @pytest.mark.parametrize("bad", ["https://evil.example/x", "http", "www.evil.com", "go://x", "see HTTPS://a.b", "a://b", "WWW.x.y"])
    def test_urls_are_rejected(self, bad):
        from ai_client import AIRetryFeedback

        with pytest.raises(AIRetryFeedback) as caught:
            self._validate(search_keywords=["정상", bad])
        assert "URL" in caught.value.feedback["validation_error"]

    def test_count_and_length_limits(self):
        from ai_client import AIRetryFeedback

        for bad in (["a", "b", "c", "d"], ["가" * 31], [""], ["   "]):
            with pytest.raises(AIRetryFeedback):
                self._validate(search_keywords=bad)

    def test_irrelevant_answers_are_not_checked_and_keep_no_keywords(self):
        parsed = AITutorAnswer(relevant=False, search_keywords=["https://x.y"])
        tutor.validate_tutor_answer(parsed, [])
        assert tutor.keywords_for(parsed, has_sources=False) == []

    def test_keywords_are_trimmed_deduplicated_and_dropped_when_there_are_sources(self):
        parsed = AITutorAnswer(relevant=True, answer="a", search_keywords=[" 리스트  슬라이싱 ", "리스트 슬라이싱", "Dict"])
        assert tutor.keywords_for(parsed, has_sources=False) == ["리스트 슬라이싱", "Dict"]
        assert tutor.keywords_for(parsed, has_sources=True) == []


class TestTutorSendMessage:
    def test_answer_without_source_gets_the_keyword_line_before_the_notice_and_search_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["동기부여 방법", "학습 습관"])]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers)).json()["assistant_message"]
        content = msg["content"]
        assert content.index("더 찾아볼 키워드: 동기부여 방법, 학습 습관") < content.index(tutor.NO_SOURCE_NOTE)
        assert msg["search_keywords"] == ["동기부여 방법", "학습 습관"] and msg["sources"] == []
        assert len(msg["search_links"]) == 3 and msg["related_links"] == []
        query = parse_qs(urlparse(msg["search_links"][0]["url"]).query)["q"][0]
        assert "동기부여 방법" in query and "Python 개발" in query

    def test_links_are_built_at_response_time_and_only_keywords_are_stored(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["습관"])]))
        conv_id = _conv(client, consented_headers)
        _ask(client, consented_headers, conv_id)
        stored = get_store().get("conversations", conv_id)["messages"][1]
        assert stored["search_keywords"] == ["습관"]
        assert "search_links" not in stored and "related_links" not in stored
        detail = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"]
        assert len(detail[1]["search_links"]) == 3 and detail[0]["search_links"] == []

    def test_a_replayed_request_returns_the_same_message_with_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        fake = override_ai(FakeAIClient(raws=[_ai(keywords=["습관"])]))
        conv_id = _conv(client, consented_headers)
        first = _ask(client, consented_headers, conv_id).json()
        again = _ask(client, consented_headers, conv_id)
        assert again.status_code == 200 and fake.calls == 1
        assert again.json()["assistant_message"] == first["assistant_message"]

    def test_no_keywords_means_no_line_no_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai()]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers)).json()["assistant_message"]
        assert "더 찾아볼 키워드" not in msg["content"] and msg["search_links"] == [] and msg["search_keywords"] == []
        assert tutor.NO_SOURCE_NOTE in msg["content"]

    def test_url_in_keywords_is_retried_and_never_reaches_a_response_or_the_store(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        bad = _ai(keywords=["https://evil.example/phish"])
        fake = override_ai(FakeAIClient(raws=[bad] * (MAX_RETRIES + 1)))
        conv_id = _conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id)
        assert res.status_code == 502 and fake.calls == MAX_RETRIES + 1
        assert "URL" in fake.payloads_seen[1]["validation_error"]
        assert get_store().get("conversations", conv_id)["messages"] == []

    def test_url_then_valid_keywords_succeeds(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["www.evil.com"]), _ai(keywords=["좋은 키워드"])]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers)).json()["assistant_message"]
        assert msg["search_keywords"] == ["좋은 키워드"]

    def test_every_url_in_a_response_is_a_template_or_a_catalog_value(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["site google.com/evil", "a&b"])]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers)).json()["assistant_message"]
        for link in msg["search_links"]:
            assert link["url"].startswith(("https://www.google.com/search?q=", "https://www.youtube.com/results?search_query="))
            assert len(parse_qs(urlparse(link["url"]).query)) == 1
        assert "&b" not in msg["search_links"][0]["url"].replace("%26b", "")

    def test_answer_with_sources_shows_at_most_two_related_links_apart_from_the_sources(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)  # Python 개발 / 기본문법
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"], keywords=["무시될 키워드"])]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers), question="리스트에 값을 추가하는 방법").json()["assistant_message"]
        assert [s["doc_id"] for s in msg["sources"]] == ["doc_002"]
        assert 1 <= len(msg["related_links"]) <= 2
        assert all(set(link) == {"title", "source_name", "url"} for link in msg["related_links"])
        assert "Python 자료구조 공식 가이드" not in [link["title"] for link in msg["related_links"]]  # already a source
        assert msg["search_keywords"] == [] and msg["search_links"] == [] and "더 찾아볼 키워드" not in msg["content"]
        assert tutor.NO_SOURCE_NOTE not in msg["content"]

    def test_related_links_come_from_the_current_learning_and_only_from_the_catalog(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers, field="영어", course="영어 회화")
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        msg = _ask(client, consented_headers, _conv(client, consented_headers), question="리스트에 값을 추가하는 방법").json()["assistant_message"]
        catalog_urls = {d["url"] for d in load_catalog()}
        assert {link["url"] for link in msg["related_links"]} == {"https://www.bbc.co.uk/learningenglish", "https://learningenglish.voanews.com/"}
        assert {link["url"] for link in msg["related_links"]} <= catalog_urls

    def test_no_learning_means_no_related_links_and_search_links_only_from_keywords(self, client: TestClient, consented_headers, override_ai, chunk_file):
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"]), _ai(keywords=["습관"])]))
        conv_id = _conv(client, consented_headers)
        with_source = _ask(client, consented_headers, conv_id, question="리스트에 값을 추가하는 방법", key="a").json()["assistant_message"]
        assert with_source["related_links"] == []
        keyword_only = _ask(client, consented_headers, conv_id, key="b").json()["assistant_message"]
        assert parse_qs(urlparse(keyword_only["search_links"][0]["url"]).query)["q"] == ["습관"]

    def test_refused_answers_have_no_keywords_and_no_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(relevant=False, answer="", keywords=["https://x.y", "잡담"])]))
        res = _ask(client, consented_headers, _conv(client, consented_headers), question="오늘 점심 뭐 먹지?")
        msg = res.json()["assistant_message"]
        assert res.json()["refused"] is True and msg["content"] == tutor.REFUSAL_TEXT
        assert msg["search_keywords"] == [] and msg["search_links"] == [] and msg["related_links"] == []

    def test_old_stored_messages_without_the_new_field_still_load(self, client: TestClient, consented_headers):
        conv_id = _conv(client, consented_headers)
        get_store().update(
            "conversations",
            conv_id,
            {"messages": [{"role": "assistant", "content": "x", "timestamp": "t", "sources": [], "refused": False}]},
        )
        msg = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"][0]
        assert msg["search_keywords"] == [] and msg["search_links"] == [] and msg["related_links"] == []

    def test_keywords_never_reach_the_logs(self, client: TestClient, consented_headers, override_ai, chunk_file, caplog):
        _confirm(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["비밀키워드QWE"])]))
        with caplog.at_level(logging.DEBUG):
            _ask(client, consented_headers, _conv(client, consented_headers))
        assert "비밀키워드QWE" not in "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("pacemate"))


class TestTutorPrompt:
    def test_prompt_asks_for_two_or_three_keywords_without_urls_and_keeps_the_old_rules(self):
        assert '"search_keywords"' in TUTOR_SYSTEM_PROMPT and "2~3개" in TUTOR_SYSTEM_PROMPT
        assert "URL" in TUTOR_SYSTEM_PROMPT and "30자" in TUTOR_SYSTEM_PROMPT
        assert "자료를 근거로 든다고 말하지 않는다" in TUTOR_SYSTEM_PROMPT
        assert "used_source_ids" in TUTOR_SYSTEM_PROMPT
