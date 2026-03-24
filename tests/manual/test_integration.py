"""Manual integration tests — these call the live server and incur LLM costs.

Run with:
    python tests/manual/test_integration.py
    python tests/manual/test_integration.py --url http://localhost:8000
    python tests/manual/test_integration.py --only calendar
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, field

import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str) -> str:
    return f"{GREEN}✓{RESET} {msg}"


def fail(msg: str) -> str:
    return f"{RED}✗{RESET} {msg}"


def info(msg: str) -> str:
    return f"{CYAN}→{RESET} {msg}"


def header(msg: str) -> str:
    return f"\n{BOLD}{msg}{RESET}"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}


# ---------------------------------------------------------------------------
# Test result
# ---------------------------------------------------------------------------

@dataclass
class Result:
    name: str
    model: str
    passed: bool
    response: str = ""
    error: str = ""
    elapsed: float = 0.0


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def record(self, r: Result) -> None:
        self.results.append(r)
        status = ok(f"{r.name} [{r.model}] ({r.elapsed:.1f}s)") if r.passed else fail(f"{r.name} [{r.model}] ({r.elapsed:.1f}s)")
        print(f"  {status}")
        if r.response:
            # Wrap long responses
            snippet = r.response[:200] + ("…" if len(r.response) > 200 else "")
            print(f"    {YELLOW}{snippet}{RESET}")
        if r.error:
            print(f"    {RED}{r.error}{RESET}")

    def summary(self) -> None:
        passed = [r for r in self.results if r.passed]
        failed = [r for r in self.results if not r.passed]
        print(header("─" * 55))
        print(f"  {ok(f'{len(passed)} passed')}  {fail(f'{len(failed)} failed') if failed else ''}")
        if failed:
            print(f"\n  {BOLD}Failures:{RESET}")
            for r in failed:
                print(f"    {RED}• {r.name} [{r.model}]{RESET}: {r.error or 'no response'}")
        print()

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)


# ---------------------------------------------------------------------------
# Individual test runners
# ---------------------------------------------------------------------------

def run_case(
    base_url: str,
    suite: Suite,
    name: str,
    message: str,
    model: str,
    *,
    expect_contains: str | None = None,
) -> None:
    """Send one request and record pass/fail."""
    conversation_id = f"manual-{name}-{model}-{uuid.uuid4().hex[:6]}"
    payload: dict = {
        "user_id": "manual-test",
        "conversation_id": conversation_id,
        "message": message,
        "model_preference": model,
    }
    t0 = time.monotonic()
    status, body = post(f"{base_url}/chat", payload)
    elapsed = time.monotonic() - t0

    if status != 200:
        suite.record(Result(name, model, False, error=f"HTTP {status}: {body}", elapsed=elapsed))
        return

    response = body.get("response", "")
    if not response:
        suite.record(Result(name, model, False, error="empty response", elapsed=elapsed))
        return

    if expect_contains and expect_contains.lower() not in response.lower():
        suite.record(Result(
            name, model, False, response=response,
            error=f"expected to contain '{expect_contains}'",
            elapsed=elapsed,
        ))
        return

    suite.record(Result(name, model, True, response=response, elapsed=elapsed))


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

TESTS: list[dict] = [
    {
        "name": "basic_math",
        "group": "basic",
        "message": "What is 17 multiplied by 6?",
        "expect_contains": "102",
    },
    {
        "name": "basic_greeting",
        "group": "basic",
        "message": "Say hello in exactly three words.",
        "expect_contains": None,
    },
    {
        "name": "calendar_read",
        "group": "calendar",
        "message": "What events do I have today?",
        "expect_contains": None,
    },
    {
        "name": "calendar_next",
        "group": "calendar",
        "message": "What is my next upcoming appointment?",
        "expect_contains": None,
    },
    {
        "name": "gmail_read",
        "group": "gmail",
        "message": "What are my most recent emails? Just list the subjects.",
        "expect_contains": None,
    },
    {
        "name": "search_read",
        "group": "search",
        "message": "Search for the current weather in London and give me a brief summary.",
        "expect_contains": None,
    },
]

MODELS = ["fast", "premium"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Manual integration tests for Flo")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the server")
    parser.add_argument("--only", help="Only run tests in this group (basic, calendar, gmail, search)")
    parser.add_argument("--model", choices=MODELS, help="Only run one model tier")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    # Health check
    print(info(f"Connecting to {base_url} …"))
    status, body = post(f"{base_url}/health", {})  # health is GET but let's GET it
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
        print(ok(f"Server healthy: {health}"))
    except Exception as e:
        print(fail(f"Server not reachable: {e}"))
        sys.exit(1)

    suite = Suite()
    models_to_run = [args.model] if args.model else MODELS

    tests_to_run = [
        t for t in TESTS
        if (args.only is None or t["group"] == args.only)
    ]

    if not tests_to_run:
        print(fail(f"No tests matched group '{args.only}'"))
        sys.exit(1)

    # Group by group label
    groups: dict[str, list[dict]] = {}
    for t in tests_to_run:
        groups.setdefault(t["group"], []).append(t)

    for group, cases in groups.items():
        print(header(f"[ {group.upper()} ]"))
        for case in cases:
            for model in models_to_run:
                run_case(
                    base_url,
                    suite,
                    case["name"],
                    case["message"],
                    model,
                    expect_contains=case.get("expect_contains"),
                )

    suite.summary()
    sys.exit(0 if suite.all_passed else 1)


if __name__ == "__main__":
    main()
