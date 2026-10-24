"""Phase 6C fix 2: `related_links` for every answered question, ordered by the server against the
question (exact word overlap with a link's tags or title), still built at response time."""

import json

from fastapi.testclient import TestClient

import tutor
from resources_catalog import load_catalog, match_references
from store import get_store
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase6c import _ask, _confirm, _conv, chunk_file, pinned_today  # noqa: F401

HTML_CSS_QUESTION = "HTML과 CSS는 각각 무슨 역할이에요?"
WEB_DEV = "web.dev: 웹 개발 학습하기"
MDN_HTML = "MDN: HTML 구조 만들기 (한국어)"
MDN_CSS = "MDN: CSS 스타일링 기초 (한국어)"


def _ai(used=None, keywords=None, relevant=True):
    return _raw({"relevant": relevant, "answer": "답" if relevant else "", "used_source_ids": used or [], "search_keywords": keywords or []})


def _learn(client, headers, field="VIBE CODING", course="웹 개발의 기초"):
    return _confirm(client, headers, field=field, course=course)


def _ask_msg(client, headers, question, key="k1", conv_id=None):
    conv_id = conv_id or _conv(client, headers)
    return _ask(client, headers, conv_id, question=question, key=key).json()["assistant_message"]


def _titles(msg):
    return [link["title"] for link in msg["related_links"]]


class TestRelatedLinksWithoutSources:
    def test_the_pm_scenario_gets_links_and_the_overlapping_ones_come_first(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(keywords=["HTML 기초", "CSS 선택자"])]))
        msg = _ask_msg(client, consented_headers, HTML_CSS_QUESTION)
        assert msg["sources"] == [] and msg["search_keywords"] and len(msg["search_links"]) == 3
        # web.dev carries both tags (html, css) so it leads; the MDN HTML page follows in match order
        assert _titles(msg) == [WEB_DEV, MDN_HTML]
        by_title = {d["title"]: d["url"] for d in load_catalog()}
        assert all(link["url"] == by_title[link["title"]] for link in msg["related_links"])

    def test_a_css_only_question_brings_the_css_material_in_and_leaves_html_out(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai()]))
        assert _titles(_ask_msg(client, consented_headers, "css 에서 색상을 바꾸는 방법")) == [WEB_DEV, MDN_CSS]

    def test_an_html_only_question_brings_the_html_material(self):
        titles = [link["title"] for link in tutor.related_links_for("VIBE CODING", "웹 개발의 기초", [], "html 태그 종류")]
        assert titles == [WEB_DEV, MDN_HTML]

    def test_overlap_beats_match_order(self):
        # match order is web.dev, Odin, MDN HTML, MDN CSS, MDN HTTP; a question about http moves MDN HTTP up
        plain = [l["title"] for l in tutor.related_links_for("VIBE CODING", "웹 개발의 기초", [])]
        http = [l["title"] for l in tutor.related_links_for("VIBE CODING", "웹 개발의 기초", [], "http 요청이 뭐예요")]
        assert plain == [WEB_DEV, "The Odin Project: 웹 개발 커리큘럼"]
        assert http == ["MDN: HTTP (한국어)", WEB_DEV]  # the overlapping link first, then the best of the rest

    def test_without_any_overlap_the_matching_order_is_kept(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai()]))
        msg = _ask_msg(client, consented_headers, "동기를 유지하는 요령이 있을까요?")
        assert _titles(msg) == [d["title"] for d in match_references("VIBE CODING", "웹 개발의 기초")][:2]

    def test_a_source_document_is_never_repeated_as_a_related_link(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _confirm(client, consented_headers)  # Python 개발 / 기본문법 (doc_002 has a chunk in the test file)
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        msg = _ask_msg(client, consented_headers, "리스트에 값을 추가하는 방법")
        assert [s["doc_id"] for s in msg["sources"]] == ["doc_002"]
        assert 1 <= len(msg["related_links"]) <= 2 and "Python 자료구조 공식 가이드" not in _titles(msg)

    def test_refused_questions_get_none(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(relevant=False)]))
        conv_id = _conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id, question="점심 뭐 먹지?").json()
        assert res["refused"] is True and res["assistant_message"]["related_links"] == []

    def test_a_learning_without_matching_materials_gets_none(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers, field="요리", course="한식")
        override_ai(FakeAIClient(raws=[_ai()]))
        assert _ask_msg(client, consented_headers, "간장 양념 비율이 궁금해요")["related_links"] == []

    def test_no_learning_means_no_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        override_ai(FakeAIClient(raws=[_ai()]))
        assert _ask_msg(client, consented_headers, HTML_CSS_QUESTION)["related_links"] == []

    def test_at_most_two_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai()]))
        assert len(_ask_msg(client, consented_headers, HTML_CSS_QUESTION)["related_links"]) == 2


class TestBuiltAtResponseTime:
    def test_nothing_new_is_stored(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai()]))
        conv_id = _conv(client, consented_headers)
        _ask(client, consented_headers, conv_id, question=HTML_CSS_QUESTION)
        stored = get_store().get("conversations", conv_id)["messages"][1]
        assert "related_links" not in stored and "search_links" not in stored

    def test_history_and_replay_use_the_question_before_each_answer(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        override_ai(FakeAIClient(raws=[_ai(), _ai()]))
        conv_id = _conv(client, consented_headers)
        first = _ask_msg(client, consented_headers, HTML_CSS_QUESTION, "a", conv_id)
        second = _ask_msg(client, consented_headers, "동기를 유지하는 요령이 있을까요?", "b", conv_id)
        history = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"]
        assert history[1]["related_links"] == first["related_links"] and history[3]["related_links"] == second["related_links"]
        assert first["related_links"] != second["related_links"]
        replay = _ask(client, consented_headers, conv_id, question=HTML_CSS_QUESTION, key="a")
        assert replay.status_code == 200 and replay.json()["assistant_message"]["related_links"] == first["related_links"]


class TestOrdering:
    @staticmethod
    def _doc(**kw):
        return {"id": "x", "title": "", "tags": [], "url": "https://e.x", **kw}

    def test_overlap_counts_exact_words_only(self):
        tokens = {"css", "선택자"}
        assert tutor._question_overlap(tokens, self._doc(tags=["css", "html"])) == 1
        assert tutor._question_overlap(tokens, self._doc(tags=["cssx"], title="선택자 가이드")) == 1
        assert tutor._question_overlap({"java"}, self._doc(tags=["javascript"])) == 0  # no prefix matching

    def test_ai_text_has_no_path_into_the_links(self, client: TestClient, consented_headers, override_ai, chunk_file):
        _learn(client, consented_headers)
        evil = {
            "relevant": True,
            "answer": "https://evil.example 링크를 보세요",
            "used_source_ids": [],
            "search_keywords": ["css"],
            "related_links": [{"title": "x", "url": "https://evil.example"}],
        }
        override_ai(FakeAIClient(raws=[json.dumps(evil, ensure_ascii=False)]))
        msg = _ask_msg(client, consented_headers, "css 가 뭐예요?")
        catalog = {d["url"] for d in load_catalog()}
        assert msg["related_links"] and all(link["url"] in catalog for link in msg["related_links"])
