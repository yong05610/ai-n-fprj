"""CR-005: continue on another device with a password (no user name).

The password finds the user: the server turns it into a key with a slow hash mixed with a
server-only secret (AUTH_PEPPER) and looks that key up in `credentials` (document id = key,
fields uid and created_at). Neither the password nor the key is ever logged, returned or put in
`users`. After a match the server issues a Firebase custom token; every later API call still
takes the UID from the verified token only.

Everything here is off unless PASSWORD_LOGIN_ENABLED=true.
"""

import hashlib
import os
import re
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import clock

MIN_LENGTH = 8
MAX_LENGTH = 64
PEPPER_MIN_LENGTH = 32

UNAVAILABLE_MESSAGE = "이 암호는 쓸 수 없어요. 다른 암호를 정해 주세요."
LOGIN_FAILED_MESSAGE = "암호가 맞지 않아요."
TOO_MANY_MESSAGE = "잠시 후 다시 시도해 주세요."

# Failed login: per IP 5 / 10 min -> that IP blocked 10 min; all IPs together 30 / 10 min -> every login paused 15 min.
LOGIN_IP_FAILS = 5
LOGIN_WINDOW_SECONDS = 600
LOGIN_IP_BLOCK_SECONDS = 600
LOGIN_TOTAL_FAILS = 30
LOGIN_PAUSE_SECONDS = 900
FAILED_LOGIN_DELAY_SECONDS = 0.3
# Register / change: per UID 5 per hour, per IP 10 per hour.
REGISTER_UID_LIMIT = 5
REGISTER_IP_LIMIT = 10
REGISTER_WINDOW_SECONDS = 3600

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def enabled() -> bool:
    return os.getenv("PASSWORD_LOGIN_ENABLED", "false").strip().lower() in ("true", "1", "yes", "on")


def pepper_problem() -> Optional[str]:
    """Why AUTH_PEPPER cannot be used (names the variable only, never a value)."""
    if len(os.getenv("AUTH_PEPPER", "")) < PEPPER_MIN_LENGTH:
        return f"AUTH_PEPPER must be set to at least {PEPPER_MIN_LENGTH} characters when PASSWORD_LOGIN_ENABLED=true"
    return None


def assert_safe_password_config() -> None:
    """Refuse to start with password login on and no usable pepper (local runs too: the key would be weak)."""
    if enabled():
        problem = pepper_problem()
        if problem:
            raise RuntimeError(problem + ".")


# --- rules ---

_PRINTABLE_ASCII = re.compile(r"^[\x21-\x7e]+$")  # no space, no control characters, no non-ASCII


def rule_problems(password: str) -> list[str]:
    """Rules of the form (length, character kinds). Safe to show to the user: everyone knows them."""
    problems: list[str] = []
    if len(password) < MIN_LENGTH or len(password) > MAX_LENGTH:
        problems.append(f"{MIN_LENGTH}자 이상 {MAX_LENGTH}자 이하여야 해요.")
    if not _PRINTABLE_ASCII.match(password or ""):
        problems.append("공백 없이 영문·숫자·특수문자만 쓸 수 있어요.")
        return problems
    if not re.search(r"[A-Za-z]", password):
        problems.append("영문을 포함해야 해요.")
    if not re.search(r"[0-9]", password):
        problems.append("숫자를 포함해야 해요.")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("특수문자를 포함해야 해요.")
    return problems


_SUBSTITUTIONS = str.maketrans({"0": "o", "1": "i", "@": "a", "$": "s"})
_LOOK_ALIKE_L = str.maketrans({"1": "l"})
_FORBIDDEN_WORDS = ("pacemate", "password", "passw0rd")  # "passw0rd" is caught through the 0 -> o substitution too
_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890", "abcdefghijklmnopqrstuvwxyz")


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "common_passwords.txt"
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return frozenset(words)


def _has_sequence(lowered: str, length: int = 4) -> bool:
    """A run of `length` keyboard-row / digit / alphabet neighbours, forwards or backwards."""
    for row in _KEYBOARD_ROWS:
        for source in (row, row[::-1]):
            for i in range(len(source) - length + 1):
                if source[i:i + length] in lowered:
                    return True
    return False


def _has_repeat(value: str, times: int = 4) -> bool:
    return re.search(r"(.)\1{%d,}" % (times - 1), value) is not None


def is_common(password: str) -> bool:
    """True for a listed common password or a password built from an obvious pattern. Case is ignored."""
    lowered = password.lower()
    if lowered in _common_passwords():
        return True
    if _has_repeat(password) or _has_sequence(lowered):
        return True
    for variant in {lowered.translate(_SUBSTITUTIONS), lowered.translate(_LOOK_ALIKE_L), lowered}:
        if any(word in variant for word in _FORBIDDEN_WORDS):
            return True
    return False


# --- key ---

def make_key(password: str) -> str:
    """scrypt(password, salt=AUTH_PEPPER). The same password gives the same key by design (no per-user salt)."""
    pepper = os.getenv("AUTH_PEPPER", "")
    return hashlib.scrypt(password.encode("utf-8"), salt=pepper.encode("utf-8"), maxmem=64 * 1024 * 1024, **_SCRYPT).hex()


# --- attempt limits (memory only; a restart resets them) ---

def client_ip(request) -> str:
    """The caller's IP for the counters only (never logged or stored). On Render the proxy appends the
    real client address as the RIGHTMOST X-Forwarded-For entry; anything the client put to its left is
    not trusted. Elsewhere the socket address is used."""
    if os.getenv("RENDER"):
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def clock_now() -> float:
    """Seconds since the epoch from the service clock (tests replace this to move time)."""
    return datetime.now(clock.SERVICE_TZ).timestamp()


def _now() -> float:
    return clock_now()


class AttemptLimits:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._login_fails: dict[str, list[float]] = {}
            self._ip_blocked_until: dict[str, float] = {}
            self._all_fails: list[float] = []
            self._paused_until = 0.0
            self._register: dict[tuple[str, str], list[float]] = {}
            self.pause_count = 0

    @staticmethod
    def _recent(stamps: list[float], now: float, window: float) -> list[float]:
        return [t for t in stamps if now - t < window]

    def login_blocked(self, ip: str) -> bool:
        now = _now()
        with self._lock:
            if now < self._paused_until:
                return True
            until = self._ip_blocked_until.get(ip)
            if until is not None:
                if now < until:
                    return True
                del self._ip_blocked_until[ip]
            return False

    def record_login_failure(self, ip: str) -> bool:
        """Count one failure. Returns True when this failure paused the whole login (so the caller logs once)."""
        now = _now()
        paused = False
        with self._lock:
            mine = self._recent(self._login_fails.get(ip, []), now, LOGIN_WINDOW_SECONDS) + [now]
            self._login_fails[ip] = mine
            if len(mine) > LOGIN_IP_FAILS:
                self._ip_blocked_until[ip] = now + LOGIN_IP_BLOCK_SECONDS
            self._all_fails = self._recent(self._all_fails, now, LOGIN_WINDOW_SECONDS) + [now]
            if len(self._all_fails) > LOGIN_TOTAL_FAILS and now >= self._paused_until:
                self._paused_until = now + LOGIN_PAUSE_SECONDS
                self.pause_count += 1
                paused = True
            # drop expired entries so the table does not grow
            for key in [k for k, v in self._login_fails.items() if not self._recent(v, now, LOGIN_WINDOW_SECONDS)]:
                del self._login_fails[key]
        return paused

    def total_failures_in_window(self) -> int:
        now = _now()
        with self._lock:
            return len(self._recent(self._all_fails, now, LOGIN_WINDOW_SECONDS))

    def register_allowed(self, uid: str, ip: str) -> bool:
        """Count one register/change attempt; False when the UID or the IP is over its hourly limit."""
        now = _now()
        with self._lock:
            subjects = (("uid", uid, REGISTER_UID_LIMIT), ("ip", ip, REGISTER_IP_LIMIT))
            current = {(k, s): self._recent(self._register.get((k, s), []), now, REGISTER_WINDOW_SECONDS) for k, s, _ in subjects}
            allowed = all(len(current[(k, s)]) < limit for k, s, limit in subjects)
            if allowed:  # a refused attempt is not counted, so it cannot extend its own lock-out
                for stamps in current.values():
                    stamps.append(now)
            self._register.update(current)
            for key in [k for k, v in self._register.items() if not self._recent(v, now, REGISTER_WINDOW_SECONDS)]:
                del self._register[key]
            return allowed


limits = AttemptLimits()


def fixed_failure_delay() -> None:
    """Failed logins wait this long (after the hash is computed, as for a success) so timing tells nothing."""
    time.sleep(FAILED_LOGIN_DELAY_SECONDS)
