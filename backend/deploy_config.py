"""Start-up checks for a deployed (Render) environment. Local runs (RENDER unset) are not affected.

A refusal names the rule or the variable that failed, never a value: CORS origins and secrets
must not end up in logs."""

import os

REQUIRED_SECRETS = ("FIREBASE_SERVICE_ACCOUNT_JSON", "OPENAI_API_KEY")


def is_deployed() -> bool:
    return bool(os.getenv("RENDER"))


def cors_origin_problems(raw: str | None) -> list[str]:
    """Rules a deployed CORS_ORIGINS value breaks (empty list = fine). Names rules only."""
    if raw is None or not raw.strip():
        return ["CORS_ORIGINS is not set (the default is a localhost origin)"]
    problems: list[str] = []
    items = raw.split(",")
    if any(not item.strip() for item in items):
        problems.append("an empty entry (stray comma or space)")
    for item in (i.strip() for i in items if i.strip()):
        lowered = item.lower()
        if "*" in item:
            problems.append("a wildcard (*) origin")
        if "localhost" in lowered or "127.0.0.1" in lowered:
            problems.append("a localhost / 127.0.0.1 origin")
        if lowered.startswith("http://"):
            problems.append("a non-https (http://) origin")
        elif not lowered.startswith("https://"):
            problems.append("an origin that does not start with https://")
        if item.endswith("/"):
            problems.append("an origin ending with '/'")
    seen: list[str] = []
    for p in problems:
        if p not in seen:
            seen.append(p)
    return seen


def assert_safe_deploy_config() -> None:
    """Fail fast on a deployed environment with an unsafe CORS list or missing secrets."""
    if not is_deployed():
        return
    problems = cors_origin_problems(os.getenv("CORS_ORIGINS"))
    if problems:
        raise RuntimeError("CORS_ORIGINS is not valid for a deployed (Render) environment: " + "; ".join(problems) + ".")
    missing = [name for name in REQUIRED_SECRETS if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("Required secret(s) are not set in the deployed (Render) environment: " + ", ".join(missing) + ".")
