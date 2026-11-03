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
    return 2


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
