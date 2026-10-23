"""Phase 5E: admin identification, admin user list, feedback (collect + manage), terms v1.1.

Only fake dev UIDs are used; ADMIN_UIDS is injected through the environment per test.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import clock
import main
from store import get_store
from tests.conftest import auth_headers
from tests.test_phase5b_multi import _confirm

TODAY = date(2026, 10, 22)  # Thursday
ADMIN = "test-uid-admin"
CONSENT = {"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(clock, "today", lambda: TODAY)


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_UIDS", ADMIN)


def _user(client, uid):
    headers = auth_headers(uid)
    assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 201
    return headers


@pytest.fixture
def admin(client):
    return _user(client, ADMIN)


@pytest.fixture
def learner(client):
    return _user(client, "test-uid-learner")


def _set_last_active(uid, iso):
    get_store().update("users", uid, {"last_active_at": iso})


def _feedback(client, headers, key="fb-1", **overrides):
    body = {"usability": 4, "ai_usefulness": 3, "screen": "dashboard", "comment": "의견입니다", "client_request_id": key, **overrides}
    return client.post("/api/feedback", json=body, headers=headers)


# ----------------------------------------------------------------------------- identification
class TestAdminIdentification:
    ADMIN_GETS = ["/api/admin/users", "/api/admin/feedback", "/api/admin/feedback/summary"]

    def test_current_terms_version_is_1_1(self):
        assert main.CURRENT_TERMS_VERSION == "v1.1"

    @pytest.mark.parametrize("path", ADMIN_GETS)
    def test_non_admin_gets_403_and_no_token_401(self, client: TestClient, learner, admin, path):
        res = client.get(path, headers=learner)
        assert res.status_code == 403 and res.json()["detail"]["code"] == "FORBIDDEN"
        assert client.get(path).status_code == 401
        assert client.get(path, headers=admin).status_code == 200

    def test_patch_feedback_is_admin_only(self, client: TestClient, learner, admin):
        fid = _feedback(client, learner).json()["id"]
        assert client.patch(f"/api/admin/feedback/{fid}", json={"status": "seen"}, headers=learner).status_code == 403
        assert client.patch(f"/api/admin/feedback/{fid}", json={"status": "seen"}).status_code == 401
        assert client.patch(f"/api/admin/feedback/{fid}", json={"status": "seen"}, headers=admin).status_code == 200

    def test_admin_before_consent_gets_consent_required(self, client: TestClient):
        res = client.get("/api/admin/users", headers=auth_headers(ADMIN))
        assert res.status_code == 403 and res.json()["detail"]["code"] == "CONSENT_REQUIRED"

    def test_admin_with_the_old_terms_version_gets_consent_required(self, client: TestClient):
        get_store().set("users", ADMIN, {"uid": ADMIN, "role": "learner", "consent_version": "v1.0", "created_at": "2026-10-01T00:00:00Z", "last_active_at": "2026-10-01T00:00:00Z"})
        res = client.get("/api/admin/users", headers=auth_headers(ADMIN))
        assert res.status_code == 403 and res.json()["detail"]["code"] == "CONSENT_REQUIRED"

    @pytest.mark.parametrize("value", ["", "   ", ",,", None])
    def test_empty_admin_list_means_nobody_is_admin(self, client: TestClient, admin, monkeypatch, value):
        if value is None:
            monkeypatch.delenv("ADMIN_UIDS")
        else:
            monkeypatch.setenv("ADMIN_UIDS", value)
        assert client.get("/api/admin/users", headers=admin).status_code == 403
        assert client.get("/api/user/profile", headers=admin).json()["is_admin"] is False

    def test_commas_and_spaces_in_the_list(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("ADMIN_UIDS", " someone-else , test-uid-admin ,, ")
        headers = _user(client, ADMIN)
        assert client.get("/api/admin/users", headers=headers).status_code == 200
        assert main._admin_uids() == frozenset({"someone-else", "test-uid-admin"})

    def test_profile_reports_is_admin_read_only(self, client: TestClient, admin, learner):
        assert client.get("/api/user/profile", headers=admin).json()["is_admin"] is True
        assert client.get("/api/user/profile", headers=learner).json()["is_admin"] is False

    def test_requests_cannot_make_anyone_an_admin(self, client: TestClient, learner):
        res = client.patch("/api/user/profile", json={"is_admin": True, "role": "admin"}, headers=learner)
        assert res.status_code in (200, 422)
        profile = client.get("/api/user/profile", headers=learner).json()
        assert profile["is_admin"] is False and profile["role"] == "learner"
        stored = get_store().get("users", "test-uid-learner")
        assert stored["role"] == "learner" and "is_admin" not in stored
        # headers, query and body values are never part of the decision
        tricked = {**learner, "X-Admin": "true", "X-User-Role": "admin"}
        assert client.get("/api/admin/users?is_admin=true&role=admin&admin=1", headers=tricked).status_code == 403
        assert client.post("/api/feedback", json={"usability": 1, "ai_usefulness": 1, "screen": "other", "client_request_id": "k", "is_admin": True}, headers=learner).status_code == 201
        assert client.get("/api/admin/feedback", headers=learner).status_code == 403

    def test_no_uid_value_of_a_real_account_is_in_the_code(self):
        source = open(main.__file__, encoding="utf-8").read()
        assert "ADMIN_UIDS" in source and ADMIN not in source


# ----------------------------------------------------------------------------- user list
class TestAdminUsers:
    def test_masked_ids_and_no_learning_content_in_the_response(self, client: TestClient, admin, learner):
        _confirm(client, learner, course="비밀과정이름", start="2026-10-22")
        task = client.get("/api/tasks", headers=learner).json()[0]
        client.post("/api/study-logs", json={"task_id": task["id"], "study_date": "2026-10-21", "minutes": 30, "activity": "비밀활동", "reflection": {"content": "비밀회고내용", "tags": []}}, headers=learner)
        conv = client.post("/api/conversations", headers=learner).json()
        get_store().update("conversations", conv["id"], {"title": "비밀대화제목", "messages": [{"role": "user", "content": "비밀질문", "timestamp": "t"}]})
        text = client.get("/api/admin/users", headers=admin).text
        for secret in ("test-uid-learner", "test-uid-admin", "비밀과정이름", "비밀활동", "비밀회고내용", "비밀대화제목", "비밀질문", "dev-test"):
            assert secret not in text
        body = json.loads(text)
        masked = {i["user_id_masked"] for i in body["items"]}
        assert masked == {"test•••"}  # both test accounts start with "test"; only 4 characters are shown
        assert set(body["items"][0]) == {"user_id_masked", "user_type", "consented", "consent_version", "active_goal_count", "last_active_at", "status"}

    def test_mask_rule_for_short_ids(self):
        assert main._mask_uid("abcdef") == "abcd•••"
        assert main._mask_uid("abcd") == "a•••"
        assert main._mask_uid("ab") == "a•••"
        assert main._mask_uid("") == "•••"

    def test_row_values(self, client: TestClient, admin, learner):
        _confirm(client, learner, course="A", start="2026-10-22", target="2026-11-30")
        done = _confirm(client, learner, course="B", start="2026-10-22", target="2026-11-30").json()["goal"]
        client.patch(f"/api/goals/{done['id']}", json={"status": "completed"}, headers=learner)
        rows = client.get("/api/admin/users", headers=admin).json()["items"]
        learner_row = next(i for i in rows if i["active_goal_count"] == 1)  # only the active goal counts
        assert learner_row["user_type"] == "익명" and learner_row["consented"] is True and learner_row["consent_version"] == "v1.1"
        admin_row = next(i for i in rows if i["active_goal_count"] == 0)
        assert admin_row["status"] == "active"

    def test_old_terms_version_is_shown_as_not_consented(self, client: TestClient, admin):
        get_store().set("users", "old-user-1234", {"uid": "old-user-1234", "role": "learner", "consent_version": "v1.0", "created_at": "2026-10-01T00:00:00Z", "last_active_at": "2026-10-20T00:00:00Z"})
        item = next(i for i in client.get("/api/admin/users", headers=admin).json()["items"] if i["user_id_masked"] == "old-•••")
        assert item["consented"] is False and item["consent_version"] == "v1.0"

    @pytest.mark.parametrize(
        "last_active,expected",
        [
            ("2026-10-15T00:00:00Z", "active"),  # 10/15 09:00 KST: 7 days before 10/22 -> still active
            ("2026-10-14T15:30:00Z", "active"),  # 10/15 00:30 KST: first minutes of the 7th day back
            ("2026-10-14T14:59:00Z", "dormant"),  # 10/14 23:59 KST: just outside
            ("2026-10-01T00:00:00Z", "dormant"),
            ("2026-10-22T05:00:00Z", "active"),
            (None, "dormant"),
        ],
    )
    def test_active_window_is_seven_days_in_seoul_time(self, client: TestClient, admin, last_active, expected):
        store = get_store()
        doc = {"uid": "edge-user-9999", "role": "learner", "consent_version": "v1.1", "created_at": "2026-10-01T00:00:00Z"}
        if last_active:
            doc["last_active_at"] = last_active
        store.set("users", "edge-user-9999", doc)
        item = next(i for i in client.get("/api/admin/users", headers=admin).json()["items"] if i["user_id_masked"] == "edge•••")
        assert item["status"] == expected

    def test_status_filter_pages_and_order(self, client: TestClient, admin):
        store = get_store()
        for n in range(120):
            store.set("users", f"user-{n:04d}", {"uid": f"user-{n:04d}", "role": "learner", "consent_version": "v1.1", "created_at": "2026-10-01T00:00:00Z",
                                                  "last_active_at": f"2026-10-{(n % 20) + 1:02d}T12:00:{n % 60:02d}Z"})
        everything = client.get("/api/admin/users", headers=admin).json()
        assert everything["total"] == 121 and everything["page"] == 1 and everything["page_size"] == 50 and len(everything["items"]) == 50
        stamps = [i["last_active_at"] for i in everything["items"]]
        assert stamps == sorted(stamps, reverse=True)  # most recent activity first
        assert len(client.get("/api/admin/users?page=3", headers=admin).json()["items"]) == 21
        assert client.get("/api/admin/users?page=4", headers=admin).json()["items"] == []
        active = client.get("/api/admin/users?status=active", headers=admin).json()
        dormant = client.get("/api/admin/users?status=dormant", headers=admin).json()
        assert active["total"] + dormant["total"] == 121
        assert all(i["status"] == "active" for i in active["items"]) and all(i["status"] == "dormant" for i in dormant["items"])

    @pytest.mark.parametrize("query", ["status=bogus", "page=0", "page=-1", "page=x"])
    def test_bad_query_is_422(self, client: TestClient, admin, query):
        assert client.get(f"/api/admin/users?{query}", headers=admin).status_code == 422

    def test_users_and_goals_are_read_once_each_not_per_user(self, client: TestClient, admin, monkeypatch):
        store = get_store()
        for n in range(30):
            store.set("users", f"u{n:05d}", {"uid": f"u{n:05d}", "role": "learner", "consent_version": "v1.1", "created_at": "x", "last_active_at": "2026-10-20T00:00:00Z"})
        calls = []
        original = store.find

        def counting(collection, **filters):
            calls.append(collection)
            return original(collection, **filters)

        monkeypatch.setattr(store, "find", counting)
        assert client.get("/api/admin/users", headers=admin).status_code == 200
        assert calls.count("users") == 1 and calls.count("goals") == 1 and len(calls) == 2


# ----------------------------------------------------------------------------- last_active_at
class TestLastActiveTouch:
    def _iso(self, minutes_ago):
        return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds").replace("+00:00", "Z")

    def test_a_request_after_ten_minutes_refreshes_it(self, client: TestClient, learner):
        old = self._iso(11)
        _set_last_active("test-uid-learner", old)
        assert client.get("/api/goals", headers=learner).status_code == 200  # a read request counts too
        assert get_store().get("users", "test-uid-learner")["last_active_at"] > old

    def test_a_request_within_ten_minutes_does_not_write(self, client: TestClient, learner):
        recent = self._iso(5)
        _set_last_active("test-uid-learner", recent)
        client.get("/api/goals", headers=learner)
        client.get("/api/user/profile", headers=learner)
        assert get_store().get("users", "test-uid-learner")["last_active_at"] == recent

    def test_missing_value_is_filled_in(self, client: TestClient, learner):
        get_store().update("users", "test-uid-learner", {"last_active_at": None})
        client.get("/api/goals", headers=learner)
        assert get_store().get("users", "test-uid-learner")["last_active_at"]

    def test_user_doc_endpoints_touch_it_too(self, client: TestClient, learner):
        old = self._iso(30)
        _set_last_active("test-uid-learner", old)
        assert client.get("/api/dashboard/summary", headers=learner).status_code == 200
        assert get_store().get("users", "test-uid-learner")["last_active_at"] > old

    def test_an_unconsented_request_never_writes(self, client: TestClient):
        get_store().set("users", "stale-user", {"uid": "stale-user", "consent_version": "v1.0", "created_at": "x", "last_active_at": "2026-01-01T00:00:00Z"})
        assert client.get("/api/goals", headers=auth_headers("stale-user")).status_code == 403
        assert get_store().get("users", "stale-user")["last_active_at"] == "2026-01-01T00:00:00Z"


# ----------------------------------------------------------------------------- feedback (collect)
class TestFeedbackCollect:
    def test_stored_document_has_no_user_identification(self, client: TestClient, learner):
        res = _feedback(client, learner, comment="  좋아요  ")
        assert res.status_code == 201 and set(res.json()) == {"id", "created_at"}
        docs = get_store().find("feedback")
        assert len(docs) == 1
        doc = docs[0]
        assert set(doc) == {"id", "usability", "ai_usefulness", "screen", "comment", "status", "client_request_id", "created_at", "updated_at"}
        assert doc["status"] == "new" and doc["comment"] == "좋아요" and doc["usability"] == 4 and doc["ai_usefulness"] == 3
        blob = json.dumps(doc, ensure_ascii=False)
        assert "test-uid-learner" not in blob and "learner" not in blob and "user_id" not in doc and "uid" not in doc

    def test_comment_is_optional(self, client: TestClient, learner):
        body = {"usability": 5, "ai_usefulness": 5, "screen": "other", "client_request_id": "no-comment"}
        assert client.post("/api/feedback", json=body, headers=learner).status_code == 201
        assert get_store().find("feedback")[0]["comment"] == ""

    @pytest.mark.parametrize(
        "bad",
        [{"usability": 0}, {"usability": 6}, {"ai_usefulness": 0}, {"ai_usefulness": 6}, {"screen": "tutor"}, {"comment": "가" * 1001}, {"client_request_id": ""}, {"usability": "high"}],
    )
    def test_validation(self, client: TestClient, learner, bad):
        assert _feedback(client, learner, **bad).status_code == 422
        assert get_store().find("feedback") == []

    def test_a_1000_character_comment_is_accepted(self, client: TestClient, learner):
        assert _feedback(client, learner, comment="가" * 1000).status_code == 201

    def test_missing_client_request_id_is_422(self, client: TestClient, learner):
        res = client.post("/api/feedback", json={"usability": 3, "ai_usefulness": 3, "screen": "other"}, headers=learner)
        assert res.status_code == 422

    def test_idempotent_retry_is_200_and_does_not_count_twice(self, client: TestClient, learner):
        first = _feedback(client, learner, key="same")
        again = _feedback(client, learner, key="same", comment="다른 내용으로 재시도")
        assert (first.status_code, again.status_code) == (201, 200)
        assert again.json()["id"] == first.json()["id"]
        assert len(get_store().find("feedback")) == 1
        assert get_store().find("feedback")[0]["comment"] == "의견입니다"  # the stored one, not rewritten
        assert get_store().get("users", "test-uid-learner")["feedback_submitted_count"] == 1

    def test_the_eleventh_feedback_is_429_without_echoing_content(self, client: TestClient, learner):
        for n in range(10):
            assert _feedback(client, learner, key=f"k{n}").status_code == 201
        res = _feedback(client, learner, key="k10", comment="한도초과비밀의견")
        assert res.status_code == 429 and res.json()["detail"]["code"] == "FEEDBACK_LIMIT_REACHED"
        assert "한도초과비밀의견" not in res.text
        assert len(get_store().find("feedback")) == 10
        # a retry of something already accepted is still answered, not blocked
        assert _feedback(client, learner, key="k3").status_code == 200

    def test_the_limit_is_per_user(self, client: TestClient, learner, admin):
        for n in range(10):
            _feedback(client, learner, key=f"a{n}")
        assert _feedback(client, learner, key="a-extra").status_code == 429
        assert _feedback(client, admin, key="b0").status_code == 201

    def test_feedback_survives_the_data_deletion_request(self, client: TestClient, learner):
        fid = _feedback(client, learner).json()["id"]
        assert client.post("/api/user/delete-data", headers=learner).status_code == 200
        assert get_store().get("users", "test-uid-learner") is None  # the user document is gone
        assert get_store().get("feedback", fid) is not None  # the anonymous feedback stays
        assert "feedback" not in main.USER_OWNED_COLLECTIONS

    def test_requires_auth_and_current_consent(self, client: TestClient):
        body = {"usability": 3, "ai_usefulness": 3, "screen": "other", "client_request_id": "x"}
        assert client.post("/api/feedback", json=body).status_code == 401
        assert client.post("/api/feedback", json=body, headers=auth_headers("never-consented")).status_code == 403

    def test_comment_text_is_not_logged(self, client: TestClient, learner, caplog):
        with caplog.at_level(logging.DEBUG):
            assert _feedback(client, learner, comment="로그금지의견ZXC").status_code == 201
            assert client.get("/api/admin/feedback", headers=auth_headers("someone")).status_code == 403
        assert "로그금지의견ZXC" not in caplog.text


# ----------------------------------------------------------------------------- feedback (manage)
class TestFeedbackManage:
    def _seed(self, client, learner):
        ids = []
        for n, (u, a, status) in enumerate([(5, 4, "new"), (4, 4, "new"), (4, 5, "seen"), (2, 2, "candidate"), (3, 3, "done")]):
            res = _feedback(client, learner, key=f"s{n}", usability=u, ai_usefulness=a, comment=f"의견 {n}")
            ids.append(res.json()["id"])
            get_store().update("feedback", res.json()["id"], {"status": status, "created_at": f"2026-10-2{n}T00:00:00Z", "updated_at": f"2026-10-2{n}T00:00:00Z"})
        return ids

    def test_list_newest_first_with_only_the_listed_fields(self, client: TestClient, learner, admin):
        self._seed(client, learner)
        items = client.get("/api/admin/feedback", headers=admin).json()
        assert [i["comment"] for i in items] == [f"의견 {n}" for n in (4, 3, 2, 1, 0)]
        assert set(items[0]) == {"id", "created_at", "screen", "usability", "ai_usefulness", "comment", "status"}
        assert "test-uid" not in json.dumps(items)

    def test_status_filter_and_limit(self, client: TestClient, learner, admin):
        self._seed(client, learner)
        assert [i["status"] for i in client.get("/api/admin/feedback?status=new", headers=admin).json()] == ["new", "new"]
        assert len(client.get("/api/admin/feedback?status=candidate", headers=admin).json()) == 1
        assert len(client.get("/api/admin/feedback?limit=2", headers=admin).json()) == 2
        assert client.get("/api/admin/feedback?limit=200", headers=admin).status_code == 200
        for bad in ("limit=201", "limit=0", "status=bogus"):
            assert client.get(f"/api/admin/feedback?{bad}", headers=admin).status_code == 422

    def test_summary_numbers(self, client: TestClient, learner, admin):
        self._seed(client, learner)
        # done within 30 days of 2026-10-22 counts; an older one does not
        old = _feedback(client, learner, key="old-done").json()["id"]
        get_store().update("feedback", old, {"status": "done", "updated_at": "2026-09-01T00:00:00Z"})
        s = client.get("/api/admin/feedback/summary", headers=admin).json()
        assert s["unseen_count"] == 2 and s["candidate_count"] == 1 and s["done_last_30_days"] == 1
        # usability 5,4,4,2,3 + the extra default 4 -> 22/6 = 3.67 -> 3.7; ai 4,4,5,2,3 + 3 -> 21/6 = 3.5
        assert s["usability_count"] == 6 and s["usability_avg"] == 3.7
        assert s["ai_usefulness_count"] == 6 and s["ai_usefulness_avg"] == 3.5

    def test_done_window_boundary_is_30_days_in_seoul_time(self, client: TestClient, learner, admin):
        a = _feedback(client, learner, key="in").json()["id"]
        b = _feedback(client, learner, key="out").json()["id"]
        get_store().update("feedback", a, {"status": "done", "updated_at": "2026-09-21T15:00:00Z"})  # 09/22 00:00 KST = exactly 30 days back
        get_store().update("feedback", b, {"status": "done", "updated_at": "2026-09-21T14:59:00Z"})  # 09/21 23:59 KST
        assert client.get("/api/admin/feedback/summary", headers=admin).json()["done_last_30_days"] == 1

    def test_empty_summary_has_null_averages(self, client: TestClient, admin):
        s = client.get("/api/admin/feedback/summary", headers=admin).json()
        assert s == {"unseen_count": 0, "usability_avg": None, "usability_count": 0, "ai_usefulness_avg": None, "ai_usefulness_count": 0, "candidate_count": 0, "done_last_30_days": 0}
        assert client.get("/api/admin/feedback", headers=admin).json() == []

    def test_status_change_only_changes_the_status(self, client: TestClient, learner, admin):
        fid = _feedback(client, learner).json()["id"]
        before = get_store().get("feedback", fid)
        for new_status in ("seen", "candidate", "done"):
            res = client.patch(f"/api/admin/feedback/{fid}", json={"status": new_status}, headers=admin)
            assert res.status_code == 200 and res.json()["status"] == new_status
        after = get_store().get("feedback", fid)
        assert after["comment"] == before["comment"] and after["usability"] == before["usability"] and after["created_at"] == before["created_at"]
        assert after["updated_at"] >= before["updated_at"]

    @pytest.mark.parametrize("bad", ["new", "bogus", "", None])
    def test_invalid_status_is_422(self, client: TestClient, learner, admin, bad):
        fid = _feedback(client, learner).json()["id"]
        assert client.patch(f"/api/admin/feedback/{fid}", json={"status": bad}, headers=admin).status_code == 422
        assert get_store().get("feedback", fid)["status"] == "new"

    def test_unknown_id_is_404(self, client: TestClient, admin):
        assert client.patch("/api/admin/feedback/nope", json={"status": "seen"}, headers=admin).status_code == 404

    def test_there_is_no_way_to_edit_the_text_or_delete(self, client: TestClient, learner, admin):
        fid = _feedback(client, learner).json()["id"]
        assert client.delete(f"/api/admin/feedback/{fid}", headers=admin).status_code == 405
        client.patch(f"/api/admin/feedback/{fid}", json={"status": "seen", "comment": "바꿈", "usability": 1}, headers=admin)
        assert get_store().get("feedback", fid)["comment"] == "의견입니다" and get_store().get("feedback", fid)["usability"] == 4


# ----------------------------------------------------------------------------- terms v1.1
class TestTermsVersion:
    def _v10_user(self, client):
        """A learner who consented under v1.0 and has data (consent record + users doc + goal)."""
        uid = "test-uid-v10"
        headers = auth_headers(uid)
        main_version = main.CURRENT_TERMS_VERSION
        main.CURRENT_TERMS_VERSION = "v1.0"
        try:
            assert client.post("/api/consent", json={**CONSENT, "terms_version": "v1.0"}, headers=headers).status_code == 201
            assert _confirm(client, headers, course="옛 동의 학습", start="2026-10-22").status_code == 201
        finally:
            main.CURRENT_TERMS_VERSION = main_version
        return headers

    def test_v1_0_consent_is_no_longer_accepted(self, client: TestClient):
        res = client.post("/api/consent", json={**CONSENT, "terms_version": "v1.0"}, headers=auth_headers("x-user"))
        assert res.status_code == 400 and res.json()["detail"]["code"] == "TERMS_VERSION_MISMATCH"
        assert res.json()["detail"]["details"]["current_version"] == "v1.1"

    def test_v1_0_user_must_consent_again_and_keeps_the_data(self, client: TestClient):
        headers = self._v10_user(client)
        for path in ("/api/goals", "/api/user/profile", "/api/tasks", "/api/dashboard/summary", "/api/conversations"):
            res = client.get(path, headers=headers)
            assert res.status_code == 403 and res.json()["detail"]["code"] == "CONSENT_REQUIRED", path
        before = get_store().get("users", "test-uid-v10")
        assert before["consent_version"] == "v1.0"
        res = client.post("/api/consent", json=CONSENT, headers=headers)
        assert res.status_code == 201 and res.json()["terms_version"] == "v1.1"
        after = get_store().get("users", "test-uid-v10")
        assert after["consent_version"] == "v1.1" and after["last_active_at"] >= before["last_active_at"]
        goals = client.get("/api/goals", headers=headers).json()
        assert [g["course"] for g in goals] == ["옛 동의 학습"]  # the earlier data is still there
        assert len(get_store().find("consent_records", user_id="test-uid-v10")) == 2

    def test_reconsent_is_idempotent(self, client: TestClient):
        headers = self._v10_user(client)
        assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 201
        assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 200
