"""Phase 6: AI tutor (reference search, learning summary + reflections, conversations).

Only fake AI clients and the in-memory store are used. Chunk files are temporary copies
so these tests never depend on the PM review state of backend/data/rag_chunks.json.
"""

import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

import clock
import rag
import tutor
from ai_client import MAX_RETRIES, AIRetryableError
from store import get_store
from tests.conftest import auth_headers
from tests.test_phase4_plan import FakeAIClient, _raw, override_ai  # noqa: F401  (fixture re-export)
from tests.test_phase5b_multi import _confirm, _other_user

TODAY = date(2026, 10, 21)

TEST_CHUNKS = [
    {
        "doc_id": "doc_002",
        "chunks": [
            {
                "id": "doc_002_c1",
                "text": "리스트는 여러 값을 순서대로 담는 변경 가능한 자료형입니다. append 는 끝에 추가하고 pop 은 꺼냅니다.",
                "keywords": ["리스트", "append", "pop"],
                "verified": True,
            },
            {
                "id": "doc_002_c2",
                "text": "딕셔너리는 키와 값을 짝지어 저장하는 자료형입니다.",
                "keywords": ["딕셔너리", "dict"],
                "verified": True,
            },
            {
                "id": "doc_002_c9",
                "text": "아직 검토되지 않은 조각입니다. 튜플 언패킹 설명.",
                "keywords": ["튜플", "언패킹"],
                "verified": False,
            },
        ],
    },
    {
        "doc_id": "doc_007",
        "chunks": [
            {
                "id": "doc_007_c1",
                "text": "브랜치는 작업 흐름을 갈라 독립적으로 개발하는 기능입니다. git merge 로 합칩니다.",
                "keywords": ["브랜치", "merge", "git"],
                "verified": True,
            }
        ],
    },
]


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


@pytest.fixture(autouse=True)
def chunk_file(tmp_path, monkeypatch):
    path = tmp_path / "chunks.json"
    path.write_text(json.dumps(TEST_CHUNKS, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("RAG_CHUNKS_PATH", str(path))
    return path


def _ai(relevant=True, answer="좋은 질문이에요. 리스트는 append 로 항목을 추가합니다.", used=None) -> str:
    return _raw({"relevant": relevant, "answer": answer, "used_source_ids": used or []})


def _new_conv(client, headers) -> str:
    res = client.post("/api/conversations", headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def _ask(client, headers, conv_id, question="리스트에 값을 추가하는 방법을 알려줘", key="k1"):
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": question, "client_request_id": key},
        headers=headers,
    )


# ----------------------------------------------------------------------------- retrieval
class TestRetrieval:
    def test_keyword_hit_returns_the_reviewed_document_with_its_metadata(self):
        hits = rag.search("리스트에 값을 추가하려면 append 를 어떻게 쓰나요?")
        assert [h.chunk_id for h in hits] == ["doc_002_c1"]
        assert hits[0].doc_id == "doc_002" and hits[0].url.startswith("https://docs.python.org")
        assert hits[0].title == "Python 자료구조 공식 가이드" and hits[0].source_name == "Python 공식 문서"

    def test_unverified_chunks_are_never_searchable(self):
        assert rag.search("튜플 언패킹이 뭐야") == []

    def test_korean_particles_still_match(self):
        assert rag.search("딕셔너리에서 키를 읽는 법")[0].chunk_id == "doc_002_c2"
        assert rag.search("브랜치를 합치는 방법")[0].doc_id == "doc_007"

    def test_below_threshold_or_unrelated_returns_nothing(self):
        assert rag.search("오늘 점심 뭐 먹을까") == []
        assert rag.search("어떻게 알려줘 설명") == []  # only generic question words
        assert rag.search("") == []

    def test_at_most_three_chunks_best_first(self, tmp_path, monkeypatch):
        many = [
            {
                "doc_id": "doc_002",
                "chunks": [
                    {"id": f"doc_002_c{i}", "text": "리스트 설명 " * i, "keywords": ["리스트"] + ["파이썬"] * (i % 2), "verified": True}
                    for i in range(1, 6)
                ],
            }
        ]
        path = tmp_path / "many.json"
        path.write_text(json.dumps(many, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("RAG_CHUNKS_PATH", str(path))
        hits = rag.search("파이썬 리스트")
        assert len(hits) == 3
        assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)

    def test_missing_chunk_file_means_no_hits_not_an_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RAG_CHUNKS_PATH", str(tmp_path / "nope.json"))
        assert rag.search("리스트 append") == []

    def test_chunks_of_unknown_documents_are_ignored(self, tmp_path, monkeypatch):
        path = tmp_path / "unknown.json"
        path.write_text(
            json.dumps([{"doc_id": "doc_999", "chunks": [{"id": "x", "text": "리스트", "keywords": ["리스트"], "verified": True}]}]),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_CHUNKS_PATH", str(path))
        assert rag.search("리스트") == []

    def test_shipped_chunk_file_is_well_formed_and_fully_approved(self, monkeypatch):
        monkeypatch.delenv("RAG_CHUNKS_PATH")
        data = json.load(open(rag._DEFAULT_CHUNKS_PATH, encoding="utf-8"))
        docs = {d["id"] for d in json.load(open(rag.os.path.join(rag.os.path.dirname(rag._DEFAULT_CHUNKS_PATH), "rag_documents.json"), encoding="utf-8"))}
        assert {e["doc_id"] for e in data} <= docs
        total = 0
        for entry in data:
            assert 4 <= len(entry["chunks"]) <= 6
            for c in entry["chunks"]:
                total += 1
                assert c["id"].startswith(entry["doc_id"] + "_c") and c["text"].strip() and c["keywords"]
                assert c["verified"] is True  # approved in docs/phase6_chunk_review.md (53 of 53)
        assert total == 53

    def test_default_chunk_file_makes_search_work(self, monkeypatch):
        """With no RAG_CHUNKS_PATH override, the shipped (PM-approved) file is what is searched."""
        monkeypatch.delenv("RAG_CHUNKS_PATH")
        hits = rag.search("파이썬 리스트에 값을 추가하려면 append 를 어떻게 쓰나요?")
        assert hits and hits[0].chunk_id == "doc_002_c1"
        assert hits[0].doc_id == "doc_002" and hits[0].url == "https://docs.python.org/3/tutorial/datastructures.html"
        assert len(hits) <= 3
        assert rag.search("저녁에 먹을 파스타 레시피를 알려줘") == []  # unrelated: still no hit

# ----------------------------------------------------------------------------- conversations
class TestConversationApi:
    def test_create_lists_and_gets_without_messages_in_the_list(self, client: TestClient, consented_headers):
        res = client.post("/api/conversations", headers=consented_headers)
        assert res.status_code == 201
        body = res.json()
        assert body["title"] == "새 대화" and body["messages"] == [] and body["user_id"] == "test-uid-alice"
        listed = client.get("/api/conversations", headers=consented_headers).json()
        assert [c["id"] for c in listed] == [body["id"]]
        assert set(listed[0]) == {"id", "title", "created_at", "updated_at"}  # no messages
        assert client.get(f"/api/conversations/{body['id']}", headers=consented_headers).json()["id"] == body["id"]

    def test_create_is_idempotent_with_client_request_id(self, client: TestClient, consented_headers):
        first = client.post("/api/conversations", json={"client_request_id": "c-1"}, headers=consented_headers)
        second = client.post("/api/conversations", json={"client_request_id": "c-1"}, headers=consented_headers)
        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"]
        assert len(client.get("/api/conversations", headers=consented_headers).json()) == 1

    def test_list_is_most_recently_updated_first_and_capped_at_50(self, client: TestClient, consented_headers):
        store = get_store()
        for n in range(52):
            store.create(
                "conversations",
                {
                    "user_id": "test-uid-alice",
                    "title": f"t{n}",
                    "messages": [],
                    "created_at": f"2026-10-01T00:{n // 60:02d}:{n % 60:02d}Z",
                    "updated_at": f"2026-10-01T00:{n // 60:02d}:{n % 60:02d}Z",
                },
            )
        listed = client.get("/api/conversations", headers=consented_headers).json()
        assert len(listed) == 50
        assert listed[0]["title"] == "t51" and listed[-1]["title"] == "t2"

    def test_other_users_conversation_is_403_and_unknown_is_404(self, client: TestClient, consented_headers):
        conv_id = _new_conv(client, consented_headers)
        bob = _other_user(client)
        for res in (
            client.get(f"/api/conversations/{conv_id}", headers=bob),
            client.post(f"/api/conversations/{conv_id}/messages", json={"content": "q", "client_request_id": "x"}, headers=bob),
        ):
            assert res.status_code == 403
            assert res.json()["detail"]["code"] == "FORBIDDEN"  # ErrorResponse shape
        assert client.get("/api/conversations/nope", headers=consented_headers).status_code == 404
        assert client.get("/api/conversations", headers=bob).json() == []  # not listed for the other user

    def test_goal_delete_keeps_conversations_and_data_delete_removes_them(self, client: TestClient, consented_headers):
        goal = _confirm(client, consented_headers).json()["goal"]
        conv_id = _new_conv(client, consented_headers)
        client.delete(f"/api/goals/{goal['id']}", headers=consented_headers)
        assert client.get(f"/api/conversations/{conv_id}", headers=consented_headers).status_code == 200
        client.post("/api/user/delete-data", headers=consented_headers)
        assert get_store().find("conversations", user_id="test-uid-alice") == []


# ----------------------------------------------------------------------------- sending messages
class TestSendMessage:
    def test_answer_with_sources_built_by_the_server(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id)
        assert res.status_code == 201
        body = res.json()
        assert body["refused"] is False
        assert body["assistant_message"]["sources"] == [
            {
                "doc_id": "doc_002",
                "title": "Python 자료구조 공식 가이드",
                "source_name": "Python 공식 문서",
                "url": "https://docs.python.org/3/tutorial/datastructures.html",
            }
        ]
        assert "참고한 등록 자료가 없어요" not in body["assistant_message"]["content"]
        assert fake.calls == 1  # one AI call, no separate classification call
        sent = fake.payloads_seen[0]
        assert sent["reference_chunks"][0]["source_id"] == "doc_002"
        assert sent["question"].startswith("리스트에 값을")
        # persisted as a user/assistant pair
        detail = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][1]["sources"][0]["doc_id"] == "doc_002"

    def test_question_without_material_says_so_and_has_no_sources(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(answer="꾸준히 짧게 나누어 학습해 보세요.", used=[])]))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id, question="공부가 지루할 때 동기를 유지하는 요령이 있을까요?")
        msg = res.json()["assistant_message"]
        assert msg["sources"] == []
        assert tutor.NO_SOURCE_NOTE in msg["content"]
        assert fake.payloads_seen[0]["reference_chunks"] == []

    def test_unrelated_question_is_refused_with_the_fixed_text(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(relevant=False, answer="오늘 날씨는 맑아요.", used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id, question="오늘 서울 날씨 어때?")
        body = res.json()
        assert body["refused"] is True
        assert body["assistant_message"]["content"] == tutor.REFUSAL_TEXT  # the model's text is discarded
        assert body["assistant_message"]["sources"] == []
        assert "다시 질문" in tutor.REFUSAL_TEXT  # tells the user how to retry a wrongly refused question
        detail = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()
        assert len(detail["messages"]) == 2  # the refusal is stored too

    @pytest.mark.parametrize(
        "bad",
        [
            _ai(used=["doc_999"]),  # a source the server never sent
            _ai(used=["doc_007"]),  # a real document, but not among this question's results
            _ai(answer="", used=["doc_002"]),
            _ai(answer="가" * 2001, used=["doc_002"]),
        ],
    )
    def test_rule_violations_are_retried_then_rejected_and_nothing_is_saved(
        self, client: TestClient, consented_headers, override_ai, bad
    ):
        fake = override_ai(FakeAIClient(raws=[bad] * (MAX_RETRIES + 1)))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id)
        assert res.status_code == 502 and res.json()["detail"]["code"] == "AI_SCHEMA_ERROR"
        assert fake.calls == MAX_RETRIES + 1
        detail = client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()
        assert detail["messages"] == [] and detail["title"] == "새 대화"

    def test_sources_claimed_when_nothing_was_retrieved_is_a_violation(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])] * (MAX_RETRIES + 1)))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id, question="공부 계획을 어떻게 세우면 좋을까요?")
        assert res.status_code == 502 and fake.calls == MAX_RETRIES + 1

    def test_violation_then_valid_answer_succeeds_and_tells_the_model_why(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_999"]), _ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        res = _ask(client, consented_headers, conv_id)
        assert res.status_code == 201 and fake.calls == 2
        assert "validation_error" in fake.payloads_seen[1] and "validation_error" not in fake.payloads_seen[0]
        assert len(client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"]) == 2

    def test_timeout_saves_nothing_and_allows_a_retry_with_the_same_key(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raises=[AIRetryableError("t")] * (MAX_RETRIES + 1)))
        conv_id = _new_conv(client, consented_headers)
        assert _ask(client, consented_headers, conv_id).status_code == 504
        assert client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"] == []
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        assert _ask(client, consented_headers, conv_id).status_code == 201  # same client_request_id, now succeeds

    def test_same_client_request_id_returns_the_saved_pair_without_a_second_call(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        first = _ask(client, consented_headers, conv_id)
        again = _ask(client, consented_headers, conv_id)
        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json()["assistant_message"]["content"] == first.json()["assistant_message"]["content"]
        assert fake.calls == 1
        assert len(client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["messages"]) == 2

    def test_title_is_the_first_question_up_to_30_characters_and_set_once(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"]), _ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        long_question = "리스트 " + "에 값을 아주 많이 추가하는 방법 " * 5
        res = _ask(client, consented_headers, conv_id, question=long_question, key="a")
        assert res.json()["conversation_title"] == " ".join(long_question.split())[:30]
        assert len(res.json()["conversation_title"]) <= 30
        _ask(client, consented_headers, conv_id, question="딕셔너리는 어떻게 써요?", key="b")
        assert client.get(f"/api/conversations/{conv_id}", headers=consented_headers).json()["title"] == res.json()["conversation_title"]
        assert fake.calls == 2

    def test_updated_at_moves_and_list_order_follows(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        older = _new_conv(client, consented_headers)
        newer = _new_conv(client, consented_headers)
        get_store().update("conversations", older, {"updated_at": "2026-01-01T00:00:00Z"})
        get_store().update("conversations", newer, {"updated_at": "2026-02-01T00:00:00Z"})
        _ask(client, consented_headers, older)
        assert [c["id"] for c in client.get("/api/conversations", headers=consented_headers).json()] == [older, newer]

    def test_only_the_last_ten_messages_are_sent_as_history(self, client: TestClient, consented_headers, override_ai):
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])] * 8))
        conv_id = _new_conv(client, consented_headers)
        for n in range(7):
            assert _ask(client, consented_headers, conv_id, question=f"리스트 질문 {n}", key=f"k{n}").status_code == 201
        assert len(fake.payloads_seen[-1]["conversation_history"]) == 10
        assert len(fake.payloads_seen[0]["conversation_history"]) == 0
        assert _ask(client, consented_headers, conv_id, question="리스트 마지막", key="last").status_code == 201
        assert len(fake.payloads_seen[-1]["conversation_history"]) == 10

    def test_conversation_size_cap(self, client: TestClient, consented_headers, override_ai, monkeypatch):
        monkeypatch.setattr(tutor, "MAX_MESSAGES_PER_CONVERSATION", 2)
        override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        assert _ask(client, consented_headers, conv_id, key="a").status_code == 201
        res = _ask(client, consented_headers, conv_id, key="b")
        assert res.status_code == 409 and res.json()["detail"]["code"] == "CONVERSATION_FULL"

    @pytest.mark.parametrize(
        "body",
        [
            {"content": "", "client_request_id": "k"},
            {"content": "   ", "client_request_id": "k"},
            {"content": "가" * 1001, "client_request_id": "k"},
            {"content": "질문"},
            {"content": "질문", "client_request_id": ""},
        ],
    )
    def test_request_validation(self, client: TestClient, consented_headers, override_ai, body):
        fake = override_ai(FakeAIClient(raws=[]))
        conv_id = _new_conv(client, consented_headers)
        res = client.post(f"/api/conversations/{conv_id}/messages", json=body, headers=consented_headers)
        assert res.status_code == 422 and fake.calls == 0

    def test_a_1000_character_question_is_accepted(self, client: TestClient, consented_headers, override_ai):
        override_ai(FakeAIClient(raws=[_ai(used=[])]))
        conv_id = _new_conv(client, consented_headers)
        assert _ask(client, consented_headers, conv_id, question="가" * 1000).status_code == 201

    def test_question_answer_and_reflection_text_never_reach_the_logs(self, client: TestClient, consented_headers, override_ai, caplog):
        goal = _confirm(client, consented_headers).json()
        task_id = goal["tasks"][0]["id"]
        client.post(
            "/api/study-logs",
            json={"task_id": task_id, "study_date": "2026-10-21", "minutes": 30, "activity": "활동기록XYZ",
                  "reflection": {"content": "비밀회고QWE", "tags": []}},
            headers=consented_headers,
        )
        override_ai(FakeAIClient(raws=[_ai(answer="답변본문ASD", used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        with caplog.at_level(logging.DEBUG):
            assert _ask(client, consented_headers, conv_id, question="리스트 질문본문ZXC").status_code == 201
        assert "질문본문ZXC" not in caplog.text and "답변본문ASD" not in caplog.text and "비밀회고QWE" not in caplog.text


# ----------------------------------------------------------------------------- summary / memory
def _log(client, headers, task_id, text, day="2026-10-21", minutes=30, key=None):
    body = {"task_id": task_id, "study_date": day, "minutes": minutes, "activity": "활동"}
    if text is not None:
        body["reflection"] = {"content": text, "tags": ["복습"]}
    if key:
        body["client_request_id"] = key
    res = client.post("/api/study-logs", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


class TestLearningContext:
    def test_summary_lists_every_active_learning_not_only_the_current_one(self, client: TestClient, consented_headers):
        _confirm(client, consented_headers, course="A과정", start="2026-10-21", target="2026-11-30")
        _confirm(client, consented_headers, course="B과정", start="2026-10-21", target="2026-11-30")
        done = _confirm(client, consented_headers, course="C과정", start="2026-12-07", target="2026-12-20").json()["goal"]
        client.patch(f"/api/goals/{done['id']}", json={"status": "completed"}, headers=consented_headers)
        body = client.get("/api/data/summary", headers=consented_headers).json()
        assert "A과정" in body["learning_summary"] and "B과정" in body["learning_summary"]
        assert "C과정" not in body["learning_summary"]  # completed learnings are not part of the context
        assert body["user_id"] == "test-uid-alice"
        assert body["active_course"] in ("A과정", "B과정")  # the current one

    def test_empty_state(self, client: TestClient, consented_headers):
        body = client.get("/api/data/summary", headers=consented_headers).json()
        assert body["learning_summary"] == "진행 중인 학습이 없습니다." and body["recent_reflections"] == []
        assert body["active_field"] is None and body["active_course"] is None

    def test_reflections_max_five_newest_first_without_keywords(self, client: TestClient, consented_headers):
        task = _confirm(client, consented_headers).json()["tasks"][0]
        for n in range(7):
            _log(client, consented_headers, task["id"], f"회고 {n}", day=f"2026-10-{10 + n:02d}")
        body = client.get("/api/data/summary", headers=consented_headers).json()
        assert [r["content"] for r in body["recent_reflections"]] == [f"회고 {n}" for n in (6, 5, 4, 3, 2)]
        assert body["recent_reflections"][0]["task_title"] == task["title"]

    def test_matching_reflections_come_first_then_newest_fill_the_rest(self, client: TestClient, consented_headers):
        task = _confirm(client, consented_headers).json()["tasks"][0]
        _log(client, consented_headers, task["id"], "딕셔너리 키가 헷갈렸어요", day="2026-10-01")
        for n in range(6):
            _log(client, consented_headers, task["id"], f"일반 회고 {n}", day=f"2026-10-{10 + n:02d}")
        got = client.get("/api/data/summary", params={"keywords": "딕셔너리 질문"}, headers=consented_headers).json()["recent_reflections"]
        assert len(got) == 5
        assert got[0]["content"] == "딕셔너리 키가 헷갈렸어요"  # old but matching -> first
        assert [r["content"] for r in got[1:]] == [f"일반 회고 {n}" for n in (5, 4, 3, 2)]  # then newest

    def test_edited_reflection_shows_latest_text_and_deleted_one_disappears(self, client: TestClient, consented_headers):
        task = _confirm(client, consented_headers).json()["tasks"][0]
        log = _log(client, consented_headers, task["id"], "처음 회고")
        client.patch(f"/api/study-logs/{log['id']}", json={"reflection": {"content": "고친 회고", "tags": []}}, headers=consented_headers)
        got = client.get("/api/data/summary", headers=consented_headers).json()["recent_reflections"]
        assert [r["content"] for r in got] == ["고친 회고"]
        client.patch(f"/api/study-logs/{log['id']}", json={"delete_reflection": True}, headers=consented_headers)
        assert client.get("/api/data/summary", headers=consented_headers).json()["recent_reflections"] == []
        log2 = _log(client, consented_headers, task["id"], "지울 기록의 회고")
        client.delete(f"/api/study-logs/{log2['id']}", headers=consented_headers)
        assert client.get("/api/data/summary", headers=consented_headers).json()["recent_reflections"] == []

    def test_reflections_of_other_users_and_of_inactive_learnings_are_excluded(self, client: TestClient, consented_headers):
        mine = _confirm(client, consented_headers, course="내 학습").json()
        _log(client, consented_headers, mine["tasks"][0]["id"], "내 회고")
        old = _confirm(client, consented_headers, course="끝난 학습", start="2026-12-07", target="2026-12-20").json()
        _log(client, consented_headers, old["tasks"][0]["id"], "끝난 학습의 회고")
        client.patch(f"/api/goals/{old['goal']['id']}", json={"status": "archived"}, headers=consented_headers)
        bob = _other_user(client)
        bob_task = _confirm(client, bob, course="밥 학습").json()["tasks"][0]
        _log(client, bob, bob_task["id"], "밥의 회고")
        got = [r["content"] for r in client.get("/api/data/summary", headers=consented_headers).json()["recent_reflections"]]
        assert got == ["내 회고"]
        assert [r["content"] for r in client.get("/api/data/summary", headers=bob).json()["recent_reflections"]] == ["밥의 회고"]

    def test_keywords_length_is_capped(self, client: TestClient, consented_headers):
        assert client.get("/api/data/summary", params={"keywords": "가" * 201}, headers=consented_headers).status_code == 422

    def test_the_tutor_receives_all_active_learnings_and_matching_reflections(self, client: TestClient, consented_headers, override_ai):
        a = _confirm(client, consented_headers, course="A과정", start="2026-10-21", target="2026-11-30").json()
        _confirm(client, consented_headers, course="B과정", start="2026-10-21", target="2026-11-30")
        _log(client, consented_headers, a["tasks"][0]["id"], "딕셔너리가 어려웠어요")
        fake = override_ai(FakeAIClient(raws=[_ai(used=["doc_002"])]))
        conv_id = _new_conv(client, consented_headers)
        assert _ask(client, consented_headers, conv_id, question="딕셔너리 복습 방법").status_code == 201
        sent = fake.payloads_seen[0]
        assert "A과정" in sent["learning_summary"] and "B과정" in sent["learning_summary"]
        assert sent["recent_reflections"][0]["content"] == "딕셔너리가 어려웠어요"
        assert set(sent["recent_reflections"][0]) == {"study_date", "task_title", "content", "tags"}  # no ids or UID
