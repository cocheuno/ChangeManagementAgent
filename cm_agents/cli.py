"""Command line interface. Phase 1 adds seed and teardown."""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from cm_agents.doctor import run_doctor
from cm_agents.settings import SettingsError, load_settings, redact_text


class RedactFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage(), self._secrets)
        record.args = ()
        return True


def configure_logging(secrets: list[str], *, level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, force=True)
    redactor = RedactFilter(secrets)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redactor)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cm-agents")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Print instance build, plugin status, and login results")
    sub.add_parser("discover", help="Run Phase 0 discovery probes against the PDI")
    seed_parser = sub.add_parser("seed", help="Generate fixtures and load them into the PDI")
    seed_parser.add_argument("--seed", type=int, default=42)
    seed_parser.add_argument(
        "--anchor",
        default=None,
        help="UTC load date, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Default: midnight UTC today",
    )
    seed_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("teardown", help="Delete synthetic records recorded in the manifest")
    change = sub.add_parser("change", help="Run the change enablement graph")
    change_sub = change.add_subparsers(dest="change_command", required=True)
    new_change = change_sub.add_parser("new", help="Create a change from a request file")
    new_change.add_argument("--file", required=True)
    new_change.add_argument("--thread", default=None)
    resume_change = sub.add_parser("resume", help="Resume a thread after an interrupt")
    resume_change.add_argument("thread")
    resume_change.add_argument("--info", default=None)
    resume_change.add_argument("--decision", choices=["go", "no-go"], default=None)
    resume_change.add_argument("--by", default=None)
    resume_change.add_argument("--reason", default=None)
    resume_change.add_argument(
        "--now", default=None, help="UTC simulated clock, YYYY-MM-DD HH:MM:SS"
    )
    status_change = sub.add_parser("status", help="Show a thread and re-read its change")
    status_change.add_argument("thread")
    release = sub.add_parser("release", help="Create or run a release change")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    new_release = release_sub.add_parser("new", help="Create a release change and stop")
    new_release.add_argument("--service", required=True)
    new_release.add_argument("--version", required=True)
    new_release.add_argument("--window", nargs=2, required=True, metavar=("START", "END"))
    new_release.add_argument("--thread", default=None)
    run_release = release_sub.add_parser(
        "run",
        help="Start a release thread. Pass --thread, or SERVICE VERSION such as STORE 2026.11.0",
    )
    run_release.add_argument("name", nargs="*")
    run_release.add_argument("--thread", default=None)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    configure_logging(settings.secret_values())
    if args.command in {"seed", "teardown"}:
        configure_logging(settings.secret_values(), level=logging.WARNING)
    if args.command == "doctor":
        report = run_doctor(settings)
        print(redact_text(report.text(), settings.secret_values()))
        return 0 if report.ok else 1
    if args.command == "discover":
        from cm_agents.discover import run_discover

        configure_logging(settings.secret_values(), level=logging.WARNING)
        return run_discover(settings)
    if args.command == "seed":
        from cm_agents.data.generate import AnchorError, parse_anchor
        from cm_agents.data.load import SeedError, seed

        try:
            anchor = parse_anchor(args.anchor) if args.anchor else None
        except AnchorError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        try:
            return seed(settings, seed=args.seed, dry_run=args.dry_run, anchor=anchor)
        except (SeedError, AnchorError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "teardown":
        from cm_agents.data.teardown import TeardownError, teardown

        try:
            return teardown(settings)
        except TeardownError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "change":
        from cm_agents.graphs.runner import RunError, load_request, new_thread_id, start_change

        try:
            request = load_request(Path(args.file))
            thread_id = args.thread or new_thread_id()
            return start_change(settings, request, thread_id)
        except Exception as exc:
            return _fail(exc, settings)
    if args.command == "resume":
        from cm_agents.graphs.runner import resume_change

        try:
            return resume_change(settings, args.thread, _resume_value(args))
        except Exception as exc:
            return _fail(exc, settings)
    if args.command == "status":
        from cm_agents.graphs.runner import RunError, show_status

        try:
            return show_status(settings, args.thread)
        except RunError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "release":
        return _release(settings, args)
    return 2


def _release(settings: object, args: argparse.Namespace) -> int:
    from cm_agents.agents.release import resolve_service
    from cm_agents.graphs.runner import create_release, new_release_thread_id, start_release
    from cm_agents.settings import Settings

    if not isinstance(settings, Settings):
        return 2
    try:
        if args.release_command == "new":
            service = resolve_service(args.service)
            start, end = _window(args.window[0], args.window[1])
            thread_id = args.thread or new_release_thread_id()
            return create_release(
                settings,
                service=service,
                version=args.version.strip(),
                start=start,
                end=end,
                thread_id=thread_id,
            )
        if args.release_command == "run":
            thread_id = args.thread or _release_thread(settings, args.name)
            return start_release(settings, thread_id)
    except Exception as exc:
        return _fail(exc, settings)
    return 2


def _window(start: str, end: str) -> tuple[str, str]:
    from datetime import datetime

    from cm_agents.graphs.runner import RunError

    try:
        datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise RunError("window must be YYYY-MM-DD HH:MM:SS UTC") from exc
    if start >= end:
        raise RunError("window start must be before the end")
    return start, end


def _release_thread(settings: object, name: list[str]) -> str:
    from cm_agents.agents.release import release_summary, resolve_service
    from cm_agents.graphs.runner import RunError
    from cm_agents.servicenow.client import ServiceNowClient
    from cm_agents.settings import Settings

    if not isinstance(settings, Settings):
        raise RunError("settings are missing")
    if len(name) != 2:
        raise RunError("release run needs --thread or SERVICE VERSION")
    service = resolve_service(name[0])
    summary = release_summary(service, name[1].strip())
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as client:
        rows = client.get_table(
            "change_request",
            query=f"short_description={summary}",
            fields=["sys_id", "short_description", "correlation_id"],
            limit=5,
        )
    match = [row for row in rows if row.get("short_description") == summary]
    if len(match) != 1:
        raise RunError(f"release {summary} was not found")
    thread_id = str(match[0].get("correlation_id") or "")
    if not thread_id.startswith(("SYN-RUN-", "SYN-S06-")):
        raise RunError("that release is not a runnable scenario thread")
    return thread_id


def _fail(exc: Exception, settings: object) -> int:
    from cm_agents.graphs.runner import RunError
    from cm_agents.llm import LlmError
    from cm_agents.servicenow.changes import ChangeError
    from cm_agents.servicenow.client import ServiceNowError
    from cm_agents.settings import Settings

    secrets = settings.secret_values() if isinstance(settings, Settings) else []
    text = redact_text(str(exc), secrets).strip() or exc.__class__.__name__
    print(text, file=sys.stderr)
    if not isinstance(exc, (RunError, ServiceNowError, ChangeError, LlmError, OSError, ValueError)):
        traceback.print_exc()
    return 1


def _resume_value(args: argparse.Namespace) -> dict[str, object]:
    import yaml

    from cm_agents.graphs.runner import RunError

    if args.info and args.decision:
        raise RunError("pass either --info or --decision")
    if args.info:
        loaded = yaml.safe_load(Path(args.info).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise RunError("info file must be a mapping")
        payload: dict[str, object] = dict(loaded)
    elif args.decision:
        if not args.by or not args.reason:
            raise RunError("--decision requires --by and --reason")
        payload = {"decision": args.decision, "by": args.by, "reason": args.reason}
    else:
        payload = {"continue": "true"}
    if args.now:
        payload["simulated_now"] = args.now
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
