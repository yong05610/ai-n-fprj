"""CR-005: continue on another device with a password (docs/cr005_password_login_dev_prompt.md §5)."""

import json
import logging
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import clock
import password_auth
from store import get_store
from tests.conftest import auth_headers

CONSENT = {"terms_version": "v1.1", "privacy_agreed": True, "ai_use_agreed": True}
PEPPER = "test-pepper-0123456789-abcdefghijklmnop"  # a throw-away test value
GOOD = "Tb7#kq2Lm"
OTHER = "Zx9$wv4Nr"
GOAL = {
    "field": "Python 개발",
    "course": "기본문법",
    "current_level_order": 1,
    "current_level_name": "입문",
    "target_level_order": 3,
    "target_level_name": "실무 기초",
    "weekly_hours": 7,
    "target_date": (clock.today() + timedelta(days=120)).isoformat(),
}
SAME_MESSAGE = "이 암호는 쓸 수 없어요. 다른 암호를 정해 주세요."


@pytest.fixture
def on(monkeypatch):
    """Password login switched on with a test pepper; counters empty; no real waiting after a failure."""
    monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
    monkeypatch.setenv("AUTH_PEPPER", PEPPER)
    monkeypatch.setattr(password_auth, "FAILED_LOGIN_DELAY_SECONDS", 0)
    password_auth.limits.reset()
    yield
    password_auth.limits.reset()


@pytest.fixture
def clock_now(monkeypatch):
    """A movable service clock for the attempt counters."""
    state = {"now": 1_800_000_000.0}
    monkeypatch.setattr(password_auth, "clock_now", lambda: state["now"])
    return state


def user(client: TestClient, uid: str) -> dict:
    headers = auth_headers(uid)
    assert client.post("/api/consent", json=CONSENT, headers=headers).status_code == 201
    return headers


def register(client, headers, password=GOOD, request_id="req-1"):
    return client.post("/api/auth/password", json={"password": password, "client_request_id": request_id}, headers=headers)


def login(client, password=GOOD, ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post("/api/auth/password/login", json={"password": password}, headers=headers)


def credential_docs():
    return get_store().find("credentials")


# 1. off by default
class TestOffByDefault:
    def test_new_routes_are_404_and_health_says_false(self, client, consented_headers, monkeypatch):
        monkeypatch.delenv("PASSWORD_LOGIN_ENABLED", raising=False)
        assert client.get("/health").json()["password_login_enabled"] is False
        assert register(client, consented_headers).status_code == 404
        assert client.delete("/api/auth/password", headers=consented_headers).status_code == 404
        assert login(client).status_code == 404
        assert credential_docs() == []

    @pytest.mark.parametrize("value", ["false", "", "0", "no", "off", "maybe"])
    def test_anything_but_a_true_value_is_off(self, client, monkeypatch, value):
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", value)
        assert login(client).status_code == 404

    def test_health_true_when_on(self, client, on):
        assert client.get("/health").json()["password_login_enabled"] is True

    def test_profile_fields_exist_when_off(self, client, consented_headers, monkeypatch):
        monkeypatch.delenv("PASSWORD_LOGIN_ENABLED", raising=False)
        body = client.get("/api/user/profile", headers=consented_headers).json()
        assert body["password_enabled"] is False and body["password_set_at"] is None


# 2. register -> another "device" logs in -> same UID, same data
class TestRegisterAndLogin:
    def test_login_without_a_token_reaches_the_same_uid_and_data(self, client, on):
        a = user(client, "alice-uid-001")
        goal = client.post("/api/goals", json=GOAL, headers=a)
        assert goal.status_code == 201
        assert register(client, a).status_code == 200

        # a new device: no Authorization header at all
        response = login(client)
        assert response.status_code == 200
        token = response.json()["custom_token"]
        assert token == "dev-alice-uid-001"

        # the token then works like any other token: the UID comes from it and the old data is there
        again = {"Authorization": f"Bearer {token}"}
        profile = client.get("/api/user/profile", headers=again).json()
        assert profile["uid"] == "alice-uid-001" and profile["password_enabled"] is True
        assert [g["id"] for g in client.get("/api/goals", headers=again).json()] == [goal.json()["id"]]

    def test_profile_after_registration(self, client, on):
        a = user(client, "alice-uid-001")
        body = register(client, a).json()
        assert body["password_enabled"] is True and body["password_set_at"]
        profile = client.get("/api/user/profile", headers=a).json()
        assert profile["password_enabled"] is True and profile["password_set_at"] == body["password_set_at"]

    def test_registration_needs_consent_and_a_token(self, client, on):
        assert client.post("/api/auth/password", json={"password": GOOD, "client_request_id": "r"}).status_code == 401
        no_consent = auth_headers("nobody-uid-01")
        assert register(client, no_consent).status_code == 403
        assert credential_docs() == []

    def test_the_credential_document_holds_only_uid_and_time(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        (doc,) = credential_docs()
        assert set(doc) == {"id", "uid", "created_at"}
        assert doc["uid"] == "alice-uid-001"
        assert doc["id"] == password_auth.make_key(GOOD) and len(doc["id"]) == 64
        assert GOOD not in json.dumps(doc)

    def test_the_login_response_has_only_the_token(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        assert set(login(client).json()) == {"custom_token"}

    def test_a_login_for_a_deleted_user_document_fails(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        get_store().delete("users", "alice-uid-001")
        assert login(client).status_code == 401

    def test_the_login_token_comes_from_the_stored_uid_not_the_request(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        response = client.post("/api/auth/password/login", json={"password": GOOD, "uid": "someone-else-1", "user_id": "x"})
        assert response.json()["custom_token"] == "dev-alice-uid-001"


# 3. rules
class TestRules:
    @pytest.mark.parametrize(
        "password",
        [
            "Ab1#xyz",          # 7 characters
            "12345678#!",       # no letter
            "Abcdefgh#!",       # no digit
            "Abcdefgh12",       # no symbol
            "Tb7# kq2Lm",       # a space
            "Tb7#kq2L한",        # non-ASCII
            "Tb7#kq2Lm" * 8,    # 72 characters
            "Tb7#kq2L" + "m" * 57,  # 65 characters
            "",
            "Tb7#kq2L\tm",      # a tab
        ],
    )
    def test_rule_breaking_passwords_are_422(self, client, on, password):
        a = user(client, "alice-uid-001")
        response = register(client, a, password)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "PASSWORD_RULE"
        assert credential_docs() == []

    def test_the_boundary_lengths_pass(self, client, on):
        a = user(client, "alice-uid-001")
        assert register(client, a, "Tb7#kq2L").status_code == 200  # 8
        long64 = "Tb7#kq2L" + "xw9Z" * 14                          # 64, no repeated or sequential runs
        assert len(long64) == 64
        assert register(client, a, long64, "req-2").status_code == 200

    @pytest.mark.parametrize(
        "password",
        ["Password1!", "P@ssw0rd1", "Qwer1234!", "Abcd1234!", "Pacemate1!", "Aaaa1111!!", "xx!PACEMATE9", "Zxcv!9876k", "P@$$w0rd1"],
    )
    def test_common_passwords_and_patterns_are_409_with_the_same_sentence(self, client, on, password):
        a = user(client, "alice-uid-001")
        response = register(client, a, password)
        assert response.status_code == 409, password
        assert response.json()["detail"]["code"] == "PASSWORD_UNAVAILABLE"
        assert response.json()["detail"]["message"] == SAME_MESSAGE

    def test_a_random_looking_password_passes(self, client, on):
        a = user(client, "alice-uid-001")
        assert register(client, a, "Tb7#kq2Lm").status_code == 200

    def test_the_comparison_ignores_case(self, client, on):
        a = user(client, "alice-uid-001")
        assert register(client, a, "pAsSwOrD1!").status_code == 409

    def test_list_size_and_licence_header(self):
        from pathlib import Path

        text = (Path(password_auth.__file__).parent / "data" / "common_passwords.txt").read_text(encoding="utf-8")
        entries = [l for l in text.splitlines() if l and not l.startswith("#")]
        assert len(entries) >= 1000
        assert "MIT License" in text and "SecLists" in text
        # every entry could pass the rules (so each one is a real refusal), and the list has no blanks
        assert all(not password_auth.rule_problems(e) for e in entries)

    @pytest.mark.parametrize("password", ["Tb7#kq2Lm", "Zx9$wv4Nr", "mK3!pQ8vLx", "Hy6&dR2tWc"])
    def test_pure_checks_accept_random_passwords(self, password):
        assert password_auth.rule_problems(password) == [] and not password_auth.is_common(password)

    def test_sequences_and_repeats(self):
        for bad in ("abcd#9Xk", "dcba#9Xk", "1234#xKq", "4321#xKq", "qwer#9Xk", "asdf#9Xk", "rewq#9Xk", "Zk#9aaaaB", "Zk#99999B"):
            assert password_auth.is_common(bad), bad
        assert not password_auth.is_common("Zk#9aaaB7")  # three in a row is fine


# 4. overlap
class TestOverlap:
    def test_a_password_used_by_someone_else_is_refused_with_the_common_sentence(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        assert register(client, a).status_code == 200
        common = register(client, b, "Password1!")
        overlap = register(client, b, GOOD, "req-b")
        assert overlap.status_code == 409
        assert overlap.text == common.text  # letter for letter the same answer
        assert overlap.json()["detail"]["message"] == SAME_MESSAGE
        assert overlap.json()["detail"]["details"] is None
        # nothing of A or B changed
        (doc,) = credential_docs()
        assert doc["uid"] == "alice-uid-001"
        assert client.get("/api/user/profile", headers=b).json()["password_enabled"] is False
        assert client.get("/api/user/profile", headers=a).json()["password_enabled"] is True
        assert login(client).json()["custom_token"] == "dev-alice-uid-001"


# 5. change / switch off
class TestChangeAndOff:
    def test_change_replaces_the_key(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        assert register(client, a, OTHER, "req-2").status_code == 200
        assert login(client, GOOD).status_code == 401
        assert login(client, OTHER).status_code == 200
        (doc,) = credential_docs()
        assert doc["id"] == password_auth.make_key(OTHER)

    def test_switch_off(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        first = client.delete("/api/auth/password", headers=a)
        assert first.status_code == 200 and first.json()["password_enabled"] is False
        assert login(client).status_code == 401
        assert credential_docs() == []
        profile = client.get("/api/user/profile", headers=a).json()
        assert profile["password_enabled"] is False and profile["password_set_at"] is None
        assert client.delete("/api/auth/password", headers=a).status_code == 200  # nothing to remove: still 200

    def test_the_freed_password_can_be_taken_by_another_user(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        register(client, a)
        client.delete("/api/auth/password", headers=a)
        assert register(client, b).status_code == 200
        assert login(client).json()["custom_token"] == "dev-bob-uid-00002"


# 6. idempotency
class TestIdempotency:
    def test_the_same_request_twice_leaves_one_key_and_one_result(self, client, on):
        a = user(client, "alice-uid-001")
        first = register(client, a, GOOD, "same-id")
        second = register(client, a, GOOD, "same-id")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(credential_docs()) == 1

    def test_typing_the_current_password_again_changes_nothing(self, client, on):
        a = user(client, "alice-uid-001")
        first = register(client, a, GOOD, "id-1").json()
        again = register(client, a, GOOD, "id-2").json()
        assert again == first and len(credential_docs()) == 1


# 7. attempt limits
class TestAttemptLimits:
    @pytest.fixture(autouse=True)
    def _behind_the_render_proxy(self, monkeypatch):
        monkeypatch.setenv("RENDER", "true")  # the IP then comes from X-Forwarded-For (rightmost value)

    def test_the_sixth_failure_from_one_ip_is_blocked_other_ips_continue(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        register(client, a)
        for _ in range(5):
            assert login(client, "Wrong1!xYz", "10.0.0.1").status_code == 401
        # the 6th failure is still answered 401 (it is the one that trips the block) ...
        assert login(client, "Wrong1!xYz", "10.0.0.1").status_code == 401
        # ... and now that IP is blocked, even with the right password
        blocked = login(client, GOOD, "10.0.0.1")
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS"
        assert blocked.json()["detail"]["message"] == "잠시 후 다시 시도해 주세요."
        assert login(client, GOOD, "10.0.0.2").status_code == 200  # another IP keeps working

    def test_the_block_ends_after_ten_minutes(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        register(client, a)
        for _ in range(6):
            login(client, "Wrong1!xYz", "10.0.0.1")
        assert login(client, GOOD, "10.0.0.1").status_code == 429
        clock_now["now"] += 599
        assert login(client, GOOD, "10.0.0.1").status_code == 429
        clock_now["now"] += 2
        assert login(client, GOOD, "10.0.0.1").status_code == 200

    def test_failures_older_than_ten_minutes_do_not_count(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        register(client, a)
        for _ in range(5):
            login(client, "Wrong1!xYz", "10.0.0.1")
        clock_now["now"] += 601
        for _ in range(5):
            assert login(client, "Wrong1!xYz", "10.0.0.1").status_code == 401
        assert login(client, GOOD, "10.0.0.1").status_code == 200

    def test_the_31st_failure_pauses_every_login_for_fifteen_minutes(self, client, on, clock_now, caplog):
        a = user(client, "alice-uid-001")
        register(client, a)
        with caplog.at_level(logging.WARNING, logger="pacemate.password"):
            for i in range(31):  # 31 different IPs, one failure each: no IP limit is reached
                assert login(client, "Wrong1!xYz", f"10.1.0.{i}").status_code == 401
            # everybody is stopped now, also a fresh IP with the right password
            stopped = login(client, GOOD, "10.9.9.9")
            assert stopped.status_code == 429
        warnings = [r for r in caplog.records if r.name == "pacemate.password"]
        assert len(warnings) == 1  # one line, counts only
        assert "10.1.0" not in warnings[0].getMessage() and GOOD not in warnings[0].getMessage()
        clock_now["now"] += 899
        assert login(client, GOOD, "10.9.9.9").status_code == 429
        clock_now["now"] += 2
        assert login(client, GOOD, "10.9.9.9").status_code == 200

    def test_the_thirtieth_failure_alone_does_not_pause(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        register(client, a)
        for i in range(30):
            login(client, "Wrong1!xYz", f"10.1.0.{i}")
        assert login(client, GOOD, "10.9.9.9").status_code == 200

    def test_register_limit_per_uid(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        for i in range(5):
            assert register(client, a, f"Tb7#kq2L{i}z", f"r{i}").status_code in (200, 409, 422)
        blocked = register(client, a, OTHER, "r-6")
        assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS"
        clock_now["now"] += 3601
        assert register(client, a, OTHER, "r-7").status_code == 200

    def test_register_limit_per_ip(self, client, on, clock_now):
        # 11 different users from the same client address: the 11th attempt is stopped by the IP limit
        results = []
        for i in range(11):
            headers = user(client, f"user-uid-{i:04d}")
            results.append(register(client, headers, f"Tb7#kq2L{i}z", "r").status_code)
        assert results[:10] == [200] * 10
        assert results[10] == 429

    def test_a_refused_attempt_does_not_extend_the_lockout(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        for i in range(5):
            register(client, a, f"Tb7#kq2L{i}z", f"r{i}")
        for _ in range(20):
            assert register(client, a, OTHER, "again").status_code == 429
        clock_now["now"] += 3601
        assert register(client, a, OTHER, "later").status_code == 200

    def test_the_counters_forget_expired_entries(self, client, on, clock_now):
        a = user(client, "alice-uid-001")
        register(client, a)
        for i in range(5):
            login(client, "Wrong1!xYz", f"10.2.0.{i}")
        clock_now["now"] += 700
        login(client, "Wrong1!xYz", "10.3.0.1")
        assert set(password_auth.limits._login_fails) == {"10.3.0.1"}

    def test_ip_choice(self, monkeypatch):
        class Req:
            def __init__(self, xff, host="1.2.3.4"):
                self.headers = {"x-forwarded-for": xff} if xff else {}
                self.client = type("C", (), {"host": host})()

        monkeypatch.delenv("RENDER", raising=False)
        assert password_auth.client_ip(Req("9.9.9.9, 8.8.8.8")) == "1.2.3.4"  # a header is not trusted off Render
        monkeypatch.setenv("RENDER", "true")
        assert password_auth.client_ip(Req("6.6.6.6, 7.7.7.7")) == "7.7.7.7"  # the rightmost one, set by the proxy
        assert password_auth.client_ip(Req("")) == "1.2.3.4"


# 8. timing
class TestTiming:
    def test_a_failed_login_waits_the_fixed_delay_and_a_success_does_not(self, client, on, monkeypatch):
        a = user(client, "alice-uid-001")
        register(client, a)
        calls = []
        monkeypatch.setattr(password_auth, "fixed_failure_delay", lambda: calls.append(1))
        login(client, "Wrong1!xYz")
        login(client, GOOD)
        assert calls == [1]  # exactly once: only the failure

    def test_the_hash_is_computed_for_every_attempt(self, client, on, monkeypatch):
        a = user(client, "alice-uid-001")
        register(client, a)
        keys = []
        real = password_auth.make_key
        monkeypatch.setattr(password_auth, "make_key", lambda p: keys.append(1) or real(p))
        login(client, GOOD)
        login(client, "Wrong1!xYz")
        login(client, "short")        # breaks the rules: still hashed
        login(client, "한글" * 50)     # not ASCII: still hashed (cut to the maximum length)
        assert len(keys) == 4

    def test_the_failure_delay_is_real_time_with_the_default(self, client, on, monkeypatch):
        monkeypatch.setattr(password_auth, "FAILED_LOGIN_DELAY_SECONDS", 0.3)
        start = time.perf_counter()
        login(client, "Wrong1!xYz")
        assert time.perf_counter() - start >= 0.3

    def test_rule_breaking_input_gets_the_same_401(self, client, on):
        a = user(client, "alice-uid-001")
        register(client, a)
        wrong = login(client, "Wrong1!xYz")
        for bad in ("short", "", "x" * 500, "한글한글한글한글", "has space 1!"):
            response = login(client, bad)
            assert response.status_code == 401
            assert response.text == wrong.text


# 9. deletion
class TestDeletion:
    def test_delete_data_removes_the_key(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        register(client, a)
        register(client, b, OTHER, "rb")
        assert client.post("/api/user/delete-data", headers=a).status_code == 200
        assert login(client, GOOD).status_code == 401
        assert [d["uid"] for d in credential_docs()] == ["bob-uid-00002"]
        assert login(client, OTHER).status_code == 200

    def test_delete_data_removes_the_key_even_when_the_feature_is_off_again(self, client, on, monkeypatch):
        a = user(client, "alice-uid-001")
        register(client, a)
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "false")
        client.post("/api/user/delete-data", headers=a)
        assert credential_docs() == []

    def test_credentials_is_not_a_user_owned_collection(self):
        from store import USER_OWNED_COLLECTIONS

        assert "credentials" not in USER_OWNED_COLLECTIONS


# 10. nothing leaks
class TestNoLeak:
    def test_no_password_or_key_in_logs_responses_or_users(self, client, on, caplog, monkeypatch):
        monkeypatch.setattr(password_auth, "fixed_failure_delay", lambda: None)
        caplog.set_level(logging.DEBUG)
        a = user(client, "alice-uid-001")
        secrets = [GOOD, "Wrong1!xYz", "Password1!", OTHER, "Tb7# kq2Lm"]
        keys = [password_auth.make_key(s) for s in (GOOD, "Wrong1!xYz", OTHER)]
        texts = []
        for resp in (
            register(client, a, GOOD),
            register(client, a, "Password1!", "r2"),
            register(client, a, "Tb7# kq2Lm", "r3"),
            register(client, a, OTHER, "r4"),
            login(client, "Wrong1!xYz"),
            login(client, OTHER),
            client.get("/api/user/profile", headers=a),
            client.delete("/api/auth/password", headers=a),
        ):
            texts.append(resp.text)
        user_doc = json.dumps(get_store().get("users", "alice-uid-001"))
        everything = "\n".join(texts + [user_doc, caplog.text])
        for secret in secrets + keys:
            assert secret not in everything
        assert set(get_store().get("users", "alice-uid-001")) <= {
            "id", "uid", "role", "active_goal_id", "consent_version", "created_at", "last_active_at", "password_enabled", "password_set_at",
        }

    def test_a_validation_error_does_not_echo_the_password(self, client, on):
        response = client.post("/api/auth/password/login", json={"password": "x" * 2000})
        assert response.status_code == 422
        assert "xxxxxxxx" not in response.text
        response = client.post("/api/auth/password", json={"password": GOOD}, headers=user(client, "alice-uid-001"))
        assert response.status_code == 422 and GOOD not in response.text

    def test_an_unexpected_error_does_not_reveal_the_password(self, client, on, monkeypatch, caplog):
        a = user(client, "alice-uid-001")
        register(client, a)

        def boom(uid):
            raise RuntimeError("firebase said no")

        monkeypatch.setattr("main.create_login_token", boom)
        caplog.set_level(logging.DEBUG)
        response = login(client)
        assert response.status_code == 503 and response.json()["detail"]["code"] == "AUTH_UNAVAILABLE"
        assert GOOD not in response.text + caplog.text

    def test_the_source_never_logs_the_password_object(self):
        from pathlib import Path

        for name in ("password_auth.py", "main.py"):
            source = Path(password_auth.__file__).parent.joinpath(name).read_text(encoding="utf-8")
            for line in source.splitlines():
                if "log" in line.lower() and ("payload.password" in line or "make_key" in line):
                    raise AssertionError(f"{name}: {line.strip()}")


# 11. start-up check
class TestStartupCheck:
    def test_on_without_a_pepper_refuses(self, monkeypatch):
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
        monkeypatch.delenv("AUTH_PEPPER", raising=False)
        with pytest.raises(RuntimeError) as exc:
            password_auth.assert_safe_password_config()
        assert "AUTH_PEPPER" in str(exc.value)

    def test_a_31_character_pepper_refuses_and_the_message_has_no_value(self, monkeypatch):
        short = "p" * 31 + "SENTINEL"[:0]
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
        monkeypatch.setenv("AUTH_PEPPER", short)
        with pytest.raises(RuntimeError) as exc:
            password_auth.assert_safe_password_config()
        assert short not in str(exc.value)

    def test_32_characters_pass_and_off_needs_nothing(self, monkeypatch):
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "true")
        monkeypatch.setenv("AUTH_PEPPER", "p" * 32)
        password_auth.assert_safe_password_config()
        monkeypatch.setenv("PASSWORD_LOGIN_ENABLED", "false")
        monkeypatch.delenv("AUTH_PEPPER", raising=False)
        password_auth.assert_safe_password_config()

    def test_the_server_refuses_to_start_in_a_fresh_process(self):
        import os
        import subprocess
        import sys
        from pathlib import Path

        backend = Path(password_auth.__file__).parent
        env = {**os.environ, "AUTH_MODE": "dev", "STORE_BACKEND": "memory", "PASSWORD_LOGIN_ENABLED": "true", "AUTH_PEPPER": "x" * 31}
        result = subprocess.run([sys.executable, "-c", "import main"], cwd=backend, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode != 0
        assert "AUTH_PEPPER" in result.stderr and "x" * 31 not in result.stderr

    def test_the_key_depends_on_the_pepper(self, monkeypatch):
        monkeypatch.setenv("AUTH_PEPPER", "a" * 40)
        first = password_auth.make_key(GOOD)
        assert password_auth.make_key(GOOD) == first
        monkeypatch.setenv("AUTH_PEPPER", "b" * 40)
        assert password_auth.make_key(GOOD) != first  # a changed pepper invalidates every registered password


# 12. isolation
class TestIsolation:
    def test_one_users_token_cannot_change_or_remove_another_users_password(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        register(client, a)
        # B acts: the UID comes from B's token, whatever the body says
        client.post("/api/auth/password", json={"password": OTHER, "client_request_id": "x", "uid": "alice-uid-001"}, headers=b)
        client.delete("/api/auth/password?uid=alice-uid-001", headers=b)
        # B's two calls only ever touched B: B registered OTHER, then removed B's own key
        assert login(client, GOOD).json()["custom_token"] == "dev-alice-uid-001"
        assert login(client, OTHER).status_code == 401
        assert client.get("/api/user/profile", headers=a).json()["password_enabled"] is True
        assert client.get("/api/user/profile", headers=b).json()["password_enabled"] is False
        assert [d["uid"] for d in credential_docs()] == ["alice-uid-001"]

    def test_a_password_set_by_b_does_not_log_in_as_a(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        register(client, a)
        client.post("/api/auth/password", json={"password": OTHER, "client_request_id": "x", "uid": "alice-uid-001"}, headers=b)
        assert login(client, OTHER).json()["custom_token"] == "dev-bob-uid-00002"
        assert login(client, GOOD).json()["custom_token"] == "dev-alice-uid-001"

    def test_removing_without_a_key_does_not_touch_other_keys(self, client, on):
        a = user(client, "alice-uid-001")
        b = user(client, "bob-uid-00002")
        register(client, a)
        client.delete("/api/auth/password", headers=b)
        assert len(credential_docs()) == 1


# firebase mode token creation
class TestFirebaseCustomToken:
    def test_firebase_mode_issues_a_custom_token_for_the_uid(self, monkeypatch):
        import auth

        monkeypatch.setenv("AUTH_MODE", "firebase")
        monkeypatch.setattr(auth, "firebase_configured", lambda: True)
        app = object()
        monkeypatch.setattr(auth, "get_firebase_app", lambda: app)
        from firebase_admin import auth as fb_auth

        seen = {}

        def fake(uid, developer_claims=None, app=None):
            seen["uid"], seen["app"] = uid, app
            return b"custom.jwt.value"

        monkeypatch.setattr(fb_auth, "create_custom_token", fake)
        assert auth.create_login_token("alice-uid-001") == "custom.jwt.value"
        assert seen == {"uid": "alice-uid-001", "app": app}

    def test_firebase_mode_without_credentials_is_503(self, monkeypatch):
        import auth

        monkeypatch.setenv("AUTH_MODE", "firebase")
        monkeypatch.setattr(auth, "firebase_configured", lambda: False)
        with pytest.raises(Exception) as exc:
            auth.create_login_token("alice-uid-001")
        assert exc.value.status_code == 503


def test_hash_time_is_reasonable(monkeypatch):
    """Not a benchmark: the key must be slow enough to be a real cost but not seconds on a normal CPU."""
    monkeypatch.setenv("AUTH_PEPPER", PEPPER)
    start = time.perf_counter()
    password_auth.make_key(GOOD)
    assert 0.005 < time.perf_counter() - start < 3
