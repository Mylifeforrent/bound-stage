#!/usr/bin/env python3
"""Real-Jenkins E2E for the full-flow QA kit.

What it proves, through public APIs only:

1. two synthetic identities (owner/admin) log in through the mock OIDC IdP;
2. an ``external_ci`` environment is registered and four-eye approved;
3. a referenced case is created and reviewed to ACTIVE;
4. starting a run triggers the real Docker Jenkins job (POST /buildWithParameters);
5. Jenkins archives JUnit + artifacts, a downstream Jenkins job sends the HMAC
   webhook after the build is final, and the platform resumes collection;
6. the platform ingests the build log and JUnit report, normalizes CaseResult,
   and schedules a quality-gate evaluation;
7. the failure job is normalized to FAILED, not silently treated as success.

Usage (from backend/):
    .venv/bin/python qa/full_flow/scripts/run_jenkins_e2e.py

Requires the QA stack (`qa.sh up`) and Jenkins (`qa.sh jenkins-up`).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from _qa_env import RUNTIME_DIR, load_qa_env

PASSWORD = "local-dev"
USERS = {"owner": "local-dev-user", "admin": "local-dev-user-2"}

CHECKS: list[dict[str, Any]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    CHECKS.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})
    marker = "\033[1;32mPASS\033[0m" if passed else "\033[1;31mFAIL\033[0m"
    print(f"  [{marker}] {name}" + (f" — {detail}" if detail else ""))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


class QaClient:
    def __init__(self, base: str, cookie_name: str, cookie: str) -> None:
        self.base = base.rstrip("/")
        self.cookie_name = cookie_name
        self.cookie = cookie
        self.http = httpx.AsyncClient(
            base_url=self.base,
            cookies={cookie_name: cookie},
            timeout=60.0,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def get(self, path: str, *, expected: int = 200) -> dict[str, Any]:
        response = await self.http.get(path)
        if response.status_code != expected:
            raise AssertionError(f"GET {path} -> {response.status_code}: {response.text[:400]}")
        return response.json()

    async def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        expected: int = 200,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = await self.http.post(path, json=body, headers=headers)
        if response.status_code != expected:
            raise AssertionError(f"POST {path} -> {response.status_code}: {response.text[:400]}")
        return response.json()


async def login(base: str, cookie_name: str, username: str) -> str:
    async with httpx.AsyncClient(base_url=base, timeout=30.0, follow_redirects=False) as client:
        started = await client.get("/api/v1/auth/oidc/start", params={"prompt": "login"})
        if started.status_code != 200:
            raise AssertionError(f"OIDC start -> {started.status_code}: {started.text[:300]}")
        authorize = urlparse(started.json()["authorization_url"])
        query = parse_qs(authorize.query)
        issued = await client.post(
            f"{authorize.scheme}://{authorize.netloc}/authorize/complete",
            data={
                "redirect_uri": query["redirect_uri"][0],
                "state": query["state"][0],
                "nonce": query["nonce"][0],
                "code_challenge": query["code_challenge"][0],
                "client_id": query["client_id"][0],
                "username": username,
                "password": PASSWORD,
            },
        )
        if issued.status_code != 302:
            raise AssertionError(f"IdP authorize -> {issued.status_code}: {issued.text[:300]}")
        callback = urlparse(issued.headers["location"])
        finished = await client.get(f"{callback.path}?{callback.query}")
        if finished.status_code != 302:
            raise AssertionError(f"OIDC callback -> {finished.status_code}: {finished.text[:300]}")
        for header in finished.headers.get_list("set-cookie"):
            jar = SimpleCookie()
            jar.load(header)
            if cookie_name in jar:
                return str(jar[cookie_name].value)
        raise AssertionError(f"OIDC callback did not set {cookie_name}")


async def wait_run_terminal(
    client: QaClient, run_id: str, timeout: float = 180.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        detail = (await client.get(f"/api/v1/test-runs/{run_id}"))["data"]
        status = str(detail.get("status", ""))
        if status != last:
            print(f"    run {run_id[:8]} … {status}")
            last = status
        if status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"}:
            return detail
        await asyncio.sleep(1.0)
    raise AssertionError(f"run {run_id} did not reach a terminal state in {timeout:.0f}s")


async def wait_gate(
    client: QaClient, run_id: str, *, expected: str, timeout: float = 90.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = (await client.get(f"/api/v1/test-runs/{run_id}/gate-evaluation"))["data"]
        evaluation = payload.get("evaluation")
        if evaluation is not None and evaluation.get("result") == expected:
            return evaluation
        await asyncio.sleep(1.0)
    raise AssertionError(f"gate evaluation for run {run_id} did not become {expected}")


async def ensure_policy(owner: QaClient, project_id: str) -> str:
    # Evaluation picks the most recently updated policy.  Always create a fresh
    # one so a previous live-smoke policy with min_pass_rate=0 cannot mask the
    # intentional failure below.
    created = await owner.post(
        "/api/v1/quality-gate-policies",
        {
            "project_id": project_id,
            "thresholds": {"min_pass_rate": 100.0, "max_p95_ms": 60000.0, "max_error_rate": 100.0},
            "mode": "blocking",
            "scope": {},
            "confirm_blocking": True,
        },
        expected=201,
        idempotency_key=str(uuid.uuid4()),
    )
    return str(created["data"]["id"])


async def register_env(
    owner: QaClient, admin: QaClient, project_id: str, jenkins_url: str
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    contracts = []
    for job_id in ("full-flow-smoke", "full-flow-fail"):
        contracts.append(
            {
                "job_id": job_id,
                "supports_cancel": True,
                "contract_version": 1,
                "report_adapter": "junit",
                "schema": {
                    "type": "object",
                    "properties": {"branch": {"type": "string"}},
                },
                "artifact_manifest": {"junit_path": "junit.xml"},
            }
        )
    created = await owner.post(
        "/api/v1/execution-environments",
        {
            "name": f"QA Jenkins {suffix}",
            "env_type": "external_ci",
            "scope_level": "project",
            "project_id": project_id,
            "endpoint": jenkins_url,
            "credential_ref": "env:JENKINS_API_TOKEN",
            "job_contracts": contracts,
        },
        idempotency_key=str(uuid.uuid4()),
    )
    env_id = str(created["data"]["id"])
    approval_id = str(created["data"]["approval_request_id"])

    detail = (await admin.get(f"/api/v1/approval-requests/{approval_id}"))["data"]
    decision = await admin.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": detail["version"]},
        idempotency_key=str(uuid.uuid4()),
    )
    require(
        decision["data"].get("status") == "EXECUTED",
        f"env approval was not EXECUTED: {decision['data']}",
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        env = (await owner.get(f"/api/v1/execution-environments/{env_id}"))["data"]
        if env.get("status") == "ACTIVE":
            return env
        await asyncio.sleep(1)
    raise AssertionError(f"environment {env_id} did not become ACTIVE")


async def create_case(
    owner: QaClient, admin: QaClient, project_id: str, env_id: str, job_id: str
) -> dict[str, Any]:
    created = await owner.post(
        "/api/v1/test-cases",
        {
            "project_id": project_id,
            "case_type": "referenced",
            "execution_mode": "script",
            "title": f"QA Jenkins {job_id} {uuid.uuid4().hex[:6]}",
            "job_binding": {
                "env_id": env_id,
                "job_id": job_id,
                "collect_config": {"artifact_path": "junit.xml"},
            },
        },
        expected=201,
        idempotency_key=str(uuid.uuid4()),
    )
    case_id = str(created["data"]["id"])
    version = int(created["data"]["version"])
    submitted = await owner.post(
        f"/api/v1/test-cases/{case_id}/submit-review",
        {"expected_version": version},
        idempotency_key=str(uuid.uuid4()),
    )
    reviewed = await admin.post(
        f"/api/v1/test-cases/{case_id}/review",
        {"expected_version": submitted["data"]["version"], "decision": "approve"},
        idempotency_key=str(uuid.uuid4()),
    )
    require(
        reviewed["data"].get("lifecycle_status") == "ACTIVE",
        f"case {case_id} did not reach ACTIVE: {reviewed['data']}",
    )
    return reviewed["data"]


async def start_run(
    owner: QaClient,
    *,
    project_id: str,
    env: dict[str, Any],
    case_id: str,
    key: str | None = None,
) -> dict[str, Any]:
    return await owner.post(
        "/api/v1/test-runs",
        {
            "project_id": project_id,
            "env_id": str(env["id"]),
            "execution_source": "external_ci",
            "case_ids": [case_id],
            "trigger_type": "manual",
            "expected_env_version": int(env["version"]),
            "params": {"branch": "main"},
        },
        idempotency_key=key or str(uuid.uuid4()),
    )


async def assert_run(
    owner: QaClient,
    *,
    label: str,
    run_id: str,
    expected_status: str,
    expected_outcome: str,
    expected_gate: str,
) -> dict[str, Any]:
    detail = await wait_run_terminal(owner, run_id)
    record(f"{label}: run terminal status", detail["status"] == expected_status, detail["status"])
    summary = detail.get("result_summary") or {}
    ci = summary.get("ci") if isinstance(summary.get("ci"), dict) else {}
    record(
        f"{label}: Jenkins build number recorded",
        isinstance(ci.get("build_number"), int),
        str(ci.get("build_number")),
    )
    record(
        f"{label}: trigger recorded",
        ci.get("trigger_state") == "triggered",
        str(ci.get("trigger_state")),
    )
    record(
        f"{label}: log collected",
        int(ci.get("log_bytes") or 0) > 0,
        f"log_bytes={ci.get('log_bytes')}",
    )
    parse_state = ci.get("report_parse") if isinstance(ci.get("report_parse"), dict) else {}
    record(
        f"{label}: JUnit parsed",
        parse_state.get("status") == "done" and int(parse_state.get("rows_done") or 0) > 0,
        f"status={parse_state.get('status')} rows={parse_state.get('rows_done')}",
    )
    record(
        f"{label}: collection done", ci.get("collect_state") == "done", str(ci.get("collect_state"))
    )

    results = (await owner.get(f"/api/v1/test-runs/{run_id}/case-results"))["data"]["items"]
    require(len(results) >= 1, f"{label}: no CaseResult rows")
    outcome = results[0].get("outcome")
    record(f"{label}: CaseResult normalized", outcome == expected_outcome, str(outcome))

    evaluation = await wait_gate(owner, run_id, expected=expected_gate)
    record(
        f"{label}: gate evaluation",
        evaluation.get("result") == expected_gate,
        str(evaluation.get("result")),
    )
    return {"run": detail, "case_result": results[0], "gate": evaluation}


async def main() -> int:
    env = load_qa_env()
    base = env["QA_BASE_URL"].rstrip("/")
    cookie_name = env["SESSION_COOKIE_NAME"]
    jenkins_url = env["QA_JENKINS_URL"].rstrip("/")
    report: dict[str, Any] = {
        "generated_at": iso_now(),
        "base_url": base,
        "jenkins_url": jenkins_url,
        "checks": CHECKS,
        "runs": {},
    }

    print("HuntAI QA · real Jenkins E2E")
    print(f"API: {base}")
    print(f"Jenkins: {jenkins_url}")

    async with httpx.AsyncClient(timeout=15.0) as probe:
        for job in (
            "full-flow-smoke",
            "full-flow-fail",
            "notify-full-flow-smoke",
            "notify-full-flow-fail",
        ):
            response = await probe.get(f"{jenkins_url}/job/{job}/api/json")
            if response.status_code != 200:
                raise SystemExit(
                    f"Jenkins job {job} not reachable ({response.status_code}). "
                    "Run `backend/qa/full_flow/qa.sh jenkins-up` first."
                )
    record("Jenkins jobs reachable", True, "4 jobs")

    print("  logging in owner/admin …")
    owner: QaClient | None = None
    admin: QaClient | None = None
    exit_code = 0
    try:
        owner_cookie = await login(base, cookie_name, USERS["owner"])
        admin_cookie = await login(base, cookie_name, USERS["admin"])
        owner = QaClient(base, cookie_name, owner_cookie)
        admin = QaClient(base, cookie_name, admin_cookie)

        me = (await owner.get("/api/v1/me"))["data"]
        record(
            "owner session",
            me["user"]["email"] == "local-dev@example.test",
            me["organization"]["slug"],
        )
        projects = (await owner.get("/api/v1/projects"))["data"]["items"]
        require(bool(projects), "no project visible; run seed_local_identity.py")
        project_id = str(projects[0]["id"])
        record("project visible", True, project_id)

        policy_id = await ensure_policy(owner, project_id)
        record("blocking gate policy ready", True, policy_id)

        env_row = await register_env(owner, admin, project_id, jenkins_url)
        record(
            "external_ci environment ACTIVE", env_row.get("status") == "ACTIVE", str(env_row["id"])
        )
        report["environment_id"] = str(env_row["id"])

        smoke_case = await create_case(
            owner, admin, project_id, str(env_row["id"]), "full-flow-smoke"
        )
        fail_case = await create_case(
            owner, admin, project_id, str(env_row["id"]), "full-flow-fail"
        )
        record("referenced cases ACTIVE", True, f"{smoke_case['id']} / {fail_case['id']}")

        # Idempotency: the same key/body must return the same run id.
        key = str(uuid.uuid4())
        started = await start_run(
            owner, project_id=project_id, env=env_row, case_id=str(smoke_case["id"]), key=key
        )
        replay = await start_run(
            owner, project_id=project_id, env=env_row, case_id=str(smoke_case["id"]), key=key
        )
        record(
            "start idempotency (same key -> same run)",
            started["data"]["id"] == replay["data"]["id"],
            started["data"]["id"],
        )
        require(
            started["data"]["receipt"]["status"] == "accepted",
            "start receipt was not accepted",
        )
        smoke_run_id = str(started["data"]["id"])
        smoke = await assert_run(
            owner,
            label="smoke",
            run_id=smoke_run_id,
            expected_status="SUCCEEDED",
            expected_outcome="passed",
            expected_gate="pass",
        )
        report["runs"]["smoke"] = {
            "run_id": smoke_run_id,
            "status": smoke["run"]["status"],
            "case_result": smoke["case_result"]["outcome"],
            "gate": smoke["gate"]["result"],
            "ci": (smoke["run"].get("result_summary") or {}).get("ci"),
        }

        fail_started = await start_run(
            owner, project_id=project_id, env=env_row, case_id=str(fail_case["id"])
        )
        fail_run_id = str(fail_started["data"]["id"])
        fail = await assert_run(
            owner,
            label="fail",
            run_id=fail_run_id,
            expected_status="FAILED",
            expected_outcome="failed",
            expected_gate="fail",
        )
        report["runs"]["fail"] = {
            "run_id": fail_run_id,
            "status": fail["run"]["status"],
            "case_result": fail["case_result"]["outcome"],
            "gate": fail["gate"]["result"],
            "ci": (fail["run"].get("result_summary") or {}).get("ci"),
        }
    except Exception as exc:  # noqa: BLE001 - surfaced as a FAIL check + report
        record("E2E completed", False, f"{type(exc).__name__}: {exc}")
        exit_code = 1
    finally:
        if owner is not None:
            await owner.close()
        if admin is not None:
            await admin.close()
        report["checks"] = CHECKS
        report["finished_at"] = iso_now()
        report_path = RUNTIME_DIR / "last_e2e_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport: {report_path}")

    failed = [check for check in CHECKS if check["status"] == "FAIL"]
    if failed:
        print(f"\nRESULT: FAIL ({len(failed)} check(s))")
        return 1
    print(f"\nRESULT: PASS ({len(CHECKS)} checks)")
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
