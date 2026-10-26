"""Phase 8B step A: the read switch RESOURCE_READ_SOURCE, the allowed-domain file and the
candidate/document storage layer. With the switch at its default nothing a learner sees changes."""

import json
import logging
from pathlib import Path

import pytest

import rag
import resource_store
import resources_catalog
from resource_urls import allowed_domains, normalize_url
from resources_catalog import load_catalog, match_references
from store import USER_OWNED_COLLECTIONS, get_store

BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((BACKEND / "tests" / "fixtures" / "phase8b_golden_references.json").read_text(encoding="utf-8"))
CASES = [tuple(key.split(" / ")) for key in GOLDEN]

APPROVED_ID = "doc_a_0a1b2c3d"


def approved_doc(**overrides) -> dict:
    doc = {
        "id": APPROVED_ID,
        "title": "Rust 공식 북 — 소유권",
        "category": "Rust 개발 / 소유권",
        "source_name": "Rust 공식 문서",
        "url": "https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html",
        "tags": ["rust", "러스트", "소유권"],
        "summary": "소유권 개념 설명",
        "level_label": "입문",
        "license": "링크만 제공",
        "link_only": True,
        "verified": True,
        "verified_at": "2026-10-26",
        "chunks": [],
        "approved_by": "admin",
        "approved_at": "2026-10-26T00:00:00Z",
    }
    return {**doc, **overrides}


@pytest.fixture(autouse=True)
def clean_switch(monkeypatch):
    monkeypatch.delenv("RESOURCE_READ_SOURCE", raising=False)
    resources_catalog.invalidate_approved_cache()
    yield
    resources_catalog.invalidate_approved_cache()


@pytest.fixture
def merged(monkeypatch):
    monkeypatch.setenv("RESOURCE_READ_SOURCE", "file+approved")


def store_approved(**overrides) -> dict:
    return resource_store.create_document(approved_doc(**overrides))


def ids(field: str, course: str) -> list[str]:
    return [d["id"] for d in match_references(field, course)]


class TestSwitchValue:
    def test_default_is_file(self):
        assert resources_catalog.read_source() == "file"

    @pytest.mark.parametrize("value", ["file", "FILE", "", " ", "file+approve", "approved", "true", "1", "file + approved"])
    def test_anything_but_the_merged_value_means_file(self, monkeypatch, value):
        monkeypatch.setenv("RESOURCE_READ_SOURCE", value)
        assert resources_catalog.read_source() == "file"

    @pytest.mark.parametrize("value", ["file+approved", " File+Approved "])
    def test_the_merged_value_is_trimmed_and_case_insensitive(self, monkeypatch, value):
        monkeypatch.setenv("RESOURCE_READ_SOURCE", value)
        assert resources_catalog.read_source() == "file+approved"


class TestFileModeIsUnchanged:
    def test_results_equal_those_of_the_code_before_phase_8b(self):
        for field, course in CASES:
            assert ids(field, course) == GOLDEN[f"{field} / {course}"], (field, course)

    def test_approved_documents_in_the_store_change_nothing(self):
        store_approved()
        for field, course in CASES:
            assert ids(field, course) == GOLDEN[f"{field} / {course}"]
        assert ids("Rust 개발", "소유권") == []

    def test_the_catalog_is_the_cached_file_list_and_the_store_is_not_read(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("file mode must not touch the store")

        monkeypatch.setattr(resource_store, "list_approved_documents", boom)
        first = load_catalog()
        assert load_catalog() is first  # same list object, as with the old lru_cache
        assert len(first) == 41
        assert first == [d for d in json.loads((BACKEND / "data" / "rag_documents.json").read_text(encoding="utf-8")) if d.get("verified")]

    def test_switching_back_needs_no_restart(self, monkeypatch):
        store_approved()
        monkeypatch.setenv("RESOURCE_READ_SOURCE", "file+approved")
        assert ids("Rust 개발", "소유권") == [APPROVED_ID]
        monkeypatch.setenv("RESOURCE_READ_SOURCE", "file")
        assert ids("Rust 개발", "소유권") == []


class TestMergedMode:
    def test_an_approved_document_reaches_the_plan_references(self, merged):
        store_approved()
        assert ids("Rust 개발", "소유권") == [APPROVED_ID]
        doc = match_references("Rust", "소유권")[0]
        assert doc["url"].startswith("https://doc.rust-lang.org/") and doc["verified"] is True

    def test_file_documents_are_kept_first_and_unchanged(self, merged):
        store_approved()
        catalog = load_catalog()
        assert catalog[:41] == resources_catalog._load_file_catalog() and len(catalog) == 42
        for field, course in CASES:
            assert ids(field, course) == GOLDEN[f"{field} / {course}"]  # approved doc is about Rust: no other input changes

    def test_approved_documents_are_link_only_whatever_is_stored(self, merged):
        store_approved(link_only=True)
        doc = [d for d in load_catalog() if d["id"] == APPROVED_ID][0]
        assert doc["link_only"] is True and doc["chunks"] == []

    def test_a_stored_chunk_or_link_only_false_is_ignored(self, merged):
        get_store().set(
            "learning_documents",
            APPROVED_ID,
            {**{k: v for k, v in approved_doc().items() if k != "id"}, "link_only": False, "chunks": [{"id": "x", "text": "본문"}]},
        )
        doc = [d for d in load_catalog() if d["id"] == APPROVED_ID][0]
        assert doc["link_only"] is True and doc["chunks"] == []

    def test_approved_documents_are_never_rag_evidence(self, merged):
        store_approved()
        rag._load_index.cache_clear()
        assert APPROVED_ID not in {c.doc_id for c in rag._index()}
        assert all(c.doc_id != APPROVED_ID for c in rag.search("러스트 소유권이 뭐야"))
        rag._load_index.cache_clear()

    def test_the_file_document_wins_for_the_same_url(self, merged):
        file_doc = load_catalog()[0]
        store_approved(url=file_doc["url"].rstrip("/") + "/?utm_source=x")
        store_approved(id="doc_a_ffffffff", url=file_doc["url"].replace("docs.python.org", "DOCS.Python.org", 1))
        urls = [normalize_url(d["url"]) for d in load_catalog()]
        assert urls.count(normalize_url(file_doc["url"])) == 1
        assert not {APPROVED_ID, "doc_a_ffffffff"} & {d["id"] for d in load_catalog()}

    def test_an_id_that_exists_in_the_file_is_not_replaced(self, merged):
        get_store().set("learning_documents", "doc_001", {**{k: v for k, v in approved_doc().items() if k != "id"}})
        assert [d for d in load_catalog() if d["id"] == "doc_001"][0]["title"] == "Python 공식 튜토리얼 — 기본 문법"

    @pytest.mark.parametrize(
        "changes",
        [
            {"verified": False},
            {"url": "http://doc.rust-lang.org/book/"},
            {"url": ""},
            {"title": ""},
            {"tags": []},
            {"tags": "rust"},
            {"category": None},
        ],
    )
    def test_malformed_or_unverified_documents_are_skipped(self, merged, changes):
        get_store().set("learning_documents", APPROVED_ID, {**{k: v for k, v in approved_doc().items() if k != "id"}, **changes})
        assert APPROVED_ID not in {d["id"] for d in load_catalog()}

    def test_candidates_never_appear_to_learners(self, merged):
        resource_store.create_candidate({**approved_doc(), "status": "pending", "collector_type": "direct_link"})
        assert ids("Rust 개발", "소유권") == []
        assert len(load_catalog()) == 41

    def test_the_api_shows_an_approved_link_in_goal_references(self, client, consented_headers, merged):
        goal = client.post(
            "/api/goals",
            json={"field": "Rust 개발", "course": "소유권", "current_level_order": 1, "current_level_name": "입문",
                  "target_level_order": 2, "target_level_name": "기초", "weekly_hours": 5, "target_date": "2027-03-31"},
            headers=consented_headers,
        ).json()
        before = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()
        assert before["references"] == []
        store_approved()
        resources_catalog.invalidate_approved_cache()
        after = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers).json()
        assert [r["url"] for r in after["references"]] == [approved_doc()["url"]]


class TestCacheAndFailure:
    def test_new_approvals_wait_for_the_cache_or_an_invalidation(self, merged, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(resources_catalog, "_monotonic", lambda: now[0])
        assert len(load_catalog()) == 41
        store_approved()
        now[0] += 59
        assert len(load_catalog()) == 41  # still the cached answer
        now[0] += 2
        assert len(load_catalog()) == 42  # 60 seconds passed

    def test_an_approval_clears_the_cache_at_once(self, merged, monkeypatch):
        monkeypatch.setattr(resources_catalog, "_monotonic", lambda: 5.0)
        assert len(load_catalog()) == 41
        store_approved()
        assert len(load_catalog()) == 41
        resources_catalog.invalidate_approved_cache()
        assert len(load_catalog()) == 42

    def test_a_store_error_falls_back_to_the_file_without_an_error(self, merged, monkeypatch, caplog):
        def broken():
            raise RuntimeError("secret-detail-from-firestore")

        monkeypatch.setattr(resource_store, "list_approved_documents", broken)
        with caplog.at_level(logging.INFO):
            assert load_catalog() == resources_catalog._load_file_catalog()
            for field, course in CASES:
                assert ids(field, course) == GOLDEN[f"{field} / {course}"]
        assert "RuntimeError" in caplog.text and "secret-detail" not in caplog.text

    def test_a_failed_read_is_retried_after_ten_seconds_not_every_request(self, merged, monkeypatch):
        now = [10.0]
        monkeypatch.setattr(resources_catalog, "_monotonic", lambda: now[0])
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("down")
            return [approved_doc()]

        monkeypatch.setattr(resource_store, "list_approved_documents", flaky)
        assert len(load_catalog()) == 41 and len(load_catalog()) == 41
        assert len(calls) == 1
        now[0] += 11
        assert len(load_catalog()) == 42 and len(calls) == 2

    def test_the_api_works_while_the_store_is_down(self, client, consented_headers, merged, monkeypatch):
        monkeypatch.setattr(resource_store, "list_approved_documents", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        goal = client.post(
            "/api/goals",
            json={"field": "Python 개발", "course": "기본문법", "current_level_order": 1, "current_level_name": "입문",
                  "target_level_order": 2, "target_level_name": "기초", "weekly_hours": 5, "target_date": "2027-03-31"},
            headers=consented_headers,
        ).json()
        response = client.get(f"/api/goals/{goal['id']}/references", headers=consented_headers)
        assert response.status_code == 200 and len(response.json()["references"]) == 5


class TestAllowedDomains:
    def test_the_file_is_exactly_the_catalog_hosts(self):
        from urllib.parse import urlparse

        catalog = json.loads((BACKEND / "data" / "rag_documents.json").read_text(encoding="utf-8"))
        hosts = {urlparse(d["url"]).hostname for d in catalog}
        assert set(allowed_domains()) == hosts and len(hosts) == 34
        names = {d["source_name"] for d in catalog}
        assert set(allowed_domains().values()) <= names

    def test_hosts_are_lowercase_plain_names(self):
        for host in allowed_domains():
            assert host == host.lower() and "*" not in host and "/" not in host and ":" not in host and not host.endswith(".")

    def test_no_hosts_were_added_by_hand(self):
        entries = json.loads((BACKEND / "data" / "allowed_domains.json").read_text(encoding="utf-8"))
        assert all(set(e) == {"domain", "source_name"} for e in entries) and len(entries) == 34


class TestStorage:
    def test_candidates_live_outside_user_owned_and_documents_collections(self):
        assert "resource_candidates" not in USER_OWNED_COLLECTIONS
        assert "learning_documents" not in USER_OWNED_COLLECTIONS

    def test_a_candidate_is_never_written_to_learning_documents(self):
        candidate = resource_store.create_candidate({"url": "https://docs.python.org/3/", "status": "pending", "collector_type": "direct_link"})
        assert get_store().find("learning_documents") == []
        assert resource_store.get_candidate(candidate["id"])["url"] == "https://docs.python.org/3/"

    def test_a_candidate_never_carries_a_user_id(self):
        with pytest.raises(ValueError):
            resource_store.create_candidate({"user_id": "u", "status": "pending"})
        c = resource_store.create_candidate({"status": "pending", "url": "https://x.example/"})
        with pytest.raises(ValueError):
            resource_store.update_candidate(c["id"], {"user_id": "u"})

    def test_a_candidate_needs_a_known_status(self):
        with pytest.raises(ValueError):
            resource_store.create_candidate({"status": "approvedish"})
        c = resource_store.create_candidate({"status": "pending"})
        with pytest.raises(ValueError):
            resource_store.update_candidate(c["id"], {"status": "done"})

    def test_update_and_missing_candidate(self):
        c = resource_store.create_candidate({"status": "pending", "url": "https://a.example/"})
        assert resource_store.update_candidate(c["id"], {"status": "rejected"})["status"] == "rejected"
        assert resource_store.update_candidate("nope", {"status": "rejected"}) is None
        assert resource_store.get_candidate("nope") is None

    def test_list_is_newest_first_and_filters(self):
        a = resource_store.create_candidate({"status": "pending", "collector_type": "direct_link", "created_at": "2026-10-26T01:00:00Z"})
        b = resource_store.create_candidate({"status": "rejected", "collector_type": "ai_topic", "created_at": "2026-10-26T02:00:00Z"})
        c = resource_store.create_candidate({"status": "pending", "collector_type": "ai_topic", "created_at": "2026-10-26T03:00:00Z"})
        assert [x["id"] for x in resource_store.list_candidates()] == [c["id"], b["id"], a["id"]]
        assert [x["id"] for x in resource_store.list_candidates(status="pending")] == [c["id"], a["id"]]
        assert [x["id"] for x in resource_store.list_candidates(collector_type="ai_topic")] == [c["id"], b["id"]]

    def test_find_by_request_id(self):
        c = resource_store.create_candidate({"status": "pending", "client_request_id": "req-1"})
        assert resource_store.find_candidate_by_request_id("req-1")["id"] == c["id"]
        assert resource_store.find_candidate_by_request_id("req-2") is None

    def test_live_candidate_by_normalized_url_ignores_rejected(self):
        resource_store.create_candidate({"status": "rejected", "url": "https://docs.python.org/3/tutorial"})
        assert resource_store.find_live_candidate_by_url("https://docs.python.org/3/tutorial/") is None
        live = resource_store.create_candidate({"status": "pending", "url": "https://docs.python.org/3/tutorial"})
        found = resource_store.find_live_candidate_by_url("HTTPS://Docs.Python.org/3/tutorial/?utm_source=a#x")
        assert found["id"] == live["id"]

    def test_the_daily_count_uses_the_seoul_day_and_counts_rejected(self):
        from datetime import date

        # 2026-10-25T15:30Z is 2026-10-26 00:30 in Seoul; 2026-10-26T15:30Z is already the 27th there
        for stamp, status in [("2026-10-25T14:59:59Z", "pending"), ("2026-10-25T15:30:00Z", "rejected"), ("2026-10-26T14:59:59Z", "pending"), ("2026-10-26T15:30:00Z", "pending")]:
            resource_store.create_candidate({"status": status, "collector_type": "direct_link", "created_at": stamp})
        resource_store.create_candidate({"status": "pending", "collector_type": "ai_topic", "created_at": "2026-10-26T01:00:00Z"})
        assert resource_store.count_candidates_created_on(date(2026, 10, 26)) == 3
        assert resource_store.count_candidates_created_on(date(2026, 10, 26), "ai_topic") == 1
        assert resource_store.count_candidates_created_on(date(2026, 10, 27)) == 1

    def test_create_document_writes_the_given_id_and_lists_approved(self):
        created = resource_store.create_document(approved_doc())
        assert created["id"] == APPROVED_ID
        assert resource_store.get_document(APPROVED_ID)["title"].startswith("Rust")
        assert [d["id"] for d in resource_store.list_approved_documents()] == [APPROVED_ID]
        resource_store.create_document(approved_doc(title="수정됨"))  # same id again replaces, no duplicate
        assert len(resource_store.list_approved_documents()) == 1

    @pytest.mark.parametrize(
        "changes",
        [{"verified": False}, {"link_only": False}, {"approved_by": "system"}, {"id": "doc_001"}, {"url": "http://a.example/"}],
    )
    def test_create_document_refuses_anything_not_approved_and_link_only(self, changes):
        with pytest.raises(ValueError):
            resource_store.create_document(approved_doc(**changes))
        assert get_store().find("learning_documents") == []

    def test_create_document_needs_every_field(self):
        doc = approved_doc()
        del doc["approved_at"]
        with pytest.raises(ValueError, match="approved_at"):
            resource_store.create_document(doc)

    def test_new_ids_use_their_own_prefix(self):
        new_id = resource_store.new_document_id()
        assert new_id.startswith("doc_a_") and len(new_id) == len("doc_a_") + 8 and new_id != resource_store.new_document_id()
