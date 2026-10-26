"""Phase 8B step E: GET /api/admin/resources/field-demand (off by default, minimum user count, no personal data)."""

import json
import logging

import pytest

import field_demand
from resources_catalog import match_references
from store import get_store
from tests.conftest import auth_headers

ADMIN = "test-uid-admin"
CONSENT = {"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}
URL = "/api/admin/resources/field-demand"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_UIDS", ADMIN)
    monkeypatch.delenv("FIELD_STATS_ENABLED", raising=False)
    monkeypatch.delenv("FIELD_STATS_MIN_USERS", raising=False)


@pytest.fixture
def admin(client):
    headers = auth_headers(ADMIN)
    assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 201
    return headers


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("FIELD_STATS_ENABLED", "true")


def goal(user, field, status="active", **extra):
    return get_store().create(
        "goals",
        {"user_id": user, "field": field, "course": f"비밀과정-{user}", "title": f"비밀목표-{user}", "status": status, **extra},
    )


def seed(field, users, **kw):
    for u in users:
        goal(u, field, **kw)


class TestSwitch:
    def test_it_is_off_by_default_and_looks_like_a_missing_route(self, client, admin):
        seed("Python 개발", ["u1", "u2", "u3", "u4"])
        r = client.get(URL, headers=admin)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "NOT_FOUND"

    @pytest.mark.parametrize("value", ["", "false", "0", "no", "off", "banana", " "])
    def test_only_a_true_value_turns_it_on(self, client, admin, monkeypatch, value):
        monkeypatch.setenv("FIELD_STATS_ENABLED", value)
        assert client.get(URL, headers=admin).status_code == 404

    @pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "on"])
    def test_true_values_turn_it_on(self, client, admin, monkeypatch, value):
        monkeypatch.setenv("FIELD_STATS_ENABLED", value)
        assert client.get(URL, headers=admin).status_code == 200

    def test_it_is_admin_only_even_when_on(self, client, on):
        assert client.get(URL).status_code == 401
        learner = auth_headers("test-uid-learner")
        client.post("/api/consent", json=CONSENT, headers=learner)
        assert client.get(URL, headers=learner).status_code == 403
        assert client.get(URL, headers=auth_headers(ADMIN)).status_code == 403  # not consented yet


class TestMinimumUsers:
    def test_a_field_with_fewer_than_three_users_is_not_in_the_answer(self, client, admin, on):
        seed("Python 개발", ["u1", "u2"])
        seed("Rust", ["u3", "u4", "u5"])
        body = client.get(URL, headers=admin).json()
        assert [i["field"] for i in body["items"]] == ["Rust"] and body["min_users"] == 3
        assert "Python" not in json.dumps(body, ensure_ascii=False)  # not even its name

    def test_one_user_with_many_goals_counts_once(self, client, admin, on):
        for _ in range(5):
            goal("u1", "Python 개발")
        seed("Python 개발", ["u2"])
        assert client.get(URL, headers=admin).json()["items"] == []

    def test_goals_of_every_status_are_counted_per_distinct_user(self, client, admin, on):
        goal("u1", "Rust", "active")
        goal("u2", "Rust", "completed")
        goal("u3", "Rust", "archived")
        assert client.get(URL, headers=admin).json()["items"][0]["user_count"] == 3

    def test_spelling_differences_are_one_field(self, client, admin, on):
        goal("u1", "Python 개발")
        goal("u2", "  python   개발 ")
        goal("u3", "PYTHON 개발")
        items = client.get(URL, headers=admin).json()["items"]
        assert len(items) == 1 and items[0]["user_count"] == 3 and items[0]["field"] in ("Python 개발", "python 개발", "PYTHON 개발")

    def test_the_shown_name_is_the_most_common_spelling(self, client, admin, on):
        goal("u1", "Python 개발")
        goal("u2", "python 개발")
        goal("u3", "python 개발")
        assert client.get(URL, headers=admin).json()["items"][0]["field"] == "python 개발"

    def test_the_minimum_is_configurable_but_never_below_two(self, client, admin, on, monkeypatch):
        seed("Rust", ["u1", "u2"])
        goal("u9", "Go")
        monkeypatch.setenv("FIELD_STATS_MIN_USERS", "2")
        assert [i["field"] for i in client.get(URL, headers=admin).json()["items"]] == ["Rust"]
        monkeypatch.setenv("FIELD_STATS_MIN_USERS", "1")  # would expose single learners: held at 2
        body = client.get(URL, headers=admin).json()
        assert [i["field"] for i in body["items"]] == ["Rust"] and body["min_users"] == 2
        monkeypatch.setenv("FIELD_STATS_MIN_USERS", "nonsense")
        assert client.get(URL, headers=admin).json()["min_users"] == 3
        monkeypatch.setenv("FIELD_STATS_MIN_USERS", "5")
        assert client.get(URL, headers=admin).json()["items"] == []

    def test_sorted_by_users_then_name_and_empty_fields_are_ignored(self, client, admin, on):
        seed("b분야", ["u1", "u2", "u3"])
        seed("a분야", ["u4", "u5", "u6"])
        seed("c분야", ["u1", "u2", "u3", "u4"])
        seed("   ", ["u1", "u2", "u3"])
        assert [(i["field"], i["user_count"]) for i in client.get(URL, headers=admin).json()["items"]] == [("c분야", 4), ("a분야", 3), ("b분야", 3)]


class TestLinkedDocuments:
    def test_it_uses_the_same_matching_function_as_the_plan(self, client, admin, on):
        seed("Python 개발", ["u1", "u2", "u3"])
        seed("전혀없는희귀분야", ["u4", "u5", "u6"])
        items = {i["field"]: i for i in client.get(URL, headers=admin).json()["items"]}
        assert items["Python 개발"]["linked_document_count"] == len(match_references("Python 개발", "")) > 0
        assert items["전혀없는희귀분야"]["linked_document_count"] == 0  # a gap in the material

    def test_a_field_gap_shows_up_after_the_material_arrives(self, client, admin, on, monkeypatch):
        import resource_store
        import resources_catalog

        monkeypatch.setenv("RESOURCE_READ_SOURCE", "file+approved")
        resources_catalog.invalidate_approved_cache()
        seed("러스트", ["u1", "u2", "u3"])
        assert client.get(URL, headers=admin).json()["items"][0]["linked_document_count"] == 0
        resource_store.create_document({
            "id": "doc_a_0000abcd", "title": "러스트 북", "category": "러스트 / 소유권", "source_name": "s", "url": "https://doc.rust-lang.org/book/",
            "tags": ["rust", "러스트", "소유권"], "verified": True, "link_only": True, "approved_by": "admin", "approved_at": "2026-10-26T00:00:00Z",
        })
        resources_catalog.invalidate_approved_cache()
        assert client.get(URL, headers=admin).json()["items"][0]["linked_document_count"] == 1
        resources_catalog.invalidate_approved_cache()


class TestNoPersonalData:
    def test_the_answer_has_only_names_and_numbers(self, client, admin, on):
        seed("Python 개발", ["alice-uid-1", "bob-uid-2", "carol-uid-3"])
        r = client.get(URL, headers=admin)
        assert set(r.json()) == {"min_users", "items"}
        assert all(set(i) == {"field", "user_count", "linked_document_count"} for i in r.json()["items"])
        for forbidden in ("alice", "bob", "carol", "uid", "비밀과정", "비밀목표", "user_id", "course", "title"):
            assert forbidden not in r.text, forbidden

    def test_it_reads_the_goals_once_however_many_users_there_are(self, client, admin, on, monkeypatch):
        for n in range(30):
            goal(f"u{n}", f"분야{n % 3}")
        store = get_store()
        real_find, calls = store.find, []
        monkeypatch.setattr(store, "find", lambda collection, **f: calls.append((collection, f)) or real_find(collection, **f))
        assert client.get(URL, headers=admin).status_code == 200
        assert [c for c in calls if c[0] == "goals"] == [("goals", {})]  # one read, no per-user query
        assert [c for c in calls if c[0] == "users"] == []

    def test_nothing_is_stored_and_nothing_is_logged(self, client, admin, on, caplog):
        seed("비밀분야9931", ["alice-uid-1", "bob-uid-2", "carol-uid-3"])
        before = {name: len(get_store().find(name)) for name in ("goals", "users", "resource_candidates", "learning_documents")}
        with caplog.at_level(logging.DEBUG):
            assert client.get(URL, headers=admin).status_code == 200
        assert "9931" not in caplog.text and "alice" not in caplog.text
        assert {name: len(get_store().find(name)) for name in before} == before

    def test_goals_with_no_user_or_field_are_skipped(self, client, admin, on):
        get_store().create("goals", {"field": "Rust", "status": "active"})
        get_store().create("goals", {"user_id": "u1", "status": "active"})
        assert client.get(URL, headers=admin).json()["items"] == []


class TestComputeFunction:
    def test_pure_grouping(self):
        goals = [{"user_id": u, "field": f} for u, f in [("a", "X"), ("b", "x "), ("c", "x"), ("a", "Y"), ("b", "Y")]]
        assert field_demand.compute(goals, lambda f: 2, 3) == [{"field": "x", "user_count": 3, "linked_document_count": 2}]
        assert [r["field"] for r in field_demand.compute(goals, lambda f: 0, 2)] == ["x", "Y"]
