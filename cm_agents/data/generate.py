"""Deterministic synthetic fixtures for Larkspur Outfitters.

The same seed and the same anchor produce the same JSON. The anchor defaults to
midnight UTC on the current UTC date, which is the load date. Pass an anchor
when the fixtures must stay byte-identical from one day to the next.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from faker import Faker

from cm_agents.data.import_time import EASTERN, UTC, format_utc, parse_utc

OPEN_WINDOW = timedelta(days=42)

MODEL_NORMAL = "007c4001c343101035ae3f52c1d3aeb2"
MODEL_EMERGENCY = "62d10fa1c303101035ae3f52c1d3aec1"
MODEL_STANDARD = "e55d0bfec343101035ae3f52c1d3ae49"
MODELS = {"normal": MODEL_NORMAL, "emergency": MODEL_EMERGENCY, "standard": MODEL_STANDARD}

TIER1_SCHEDULE = "SYN Tier-1 Maintenance (Sat 22:00-Sun 04:00)"
TIER23_SCHEDULE = "SYN Tier-2/3 Maintenance (Tue/Thu 20:00-23:00)"

SERVICES = (
    {"key": "store", "name": "SYN Online Store", "tier": 1, "group": "SYN Store DevOps"},
    {"key": "pay", "name": "SYN Payments", "tier": 1, "group": "SYN Payments DevOps"},
    {"key": "ful", "name": "SYN Order Fulfillment", "tier": 2, "group": "SYN Fulfillment DevOps"},
    {"key": "hr", "name": "SYN HR Portal", "tier": 3, "group": "SYN Platform Ops"},
)
SERVICE_BY_KEY = {row["key"]: row for row in SERVICES}
SERVICE_BY_NAME = {row["name"]: row for row in SERVICES}

APPS = {
    "store": ("web", "api", "checkout", "catalog", "cart", "search", "session", "cdn"),
    "pay": ("api", "auth", "gateway", "ledger", "fraud", "recon"),
    "ful": ("api", "warehouse", "shipping", "inventory", "tracking", "returns", "notify"),
    "hr": ("portal", "payroll", "benefits", "recruiting", "time"),
}

# prod, stage, test counts per service. Totals: 120, 35, 35.
SERVER_COUNTS = {
    "prod": {"store": 36, "pay": 36, "ful": 30, "hr": 18},
    "stage": {"store": 10, "pay": 10, "ful": 9, "hr": 6},
    "test": {"store": 10, "pay": 10, "ful": 9, "hr": 6},
}

GROUP_CHANGE_MANAGEMENT = "Change Management"
GROUP_CAB = "CAB Approval"
GROUP_ECAB = "eCAB Approval"
GROUP_RELEASE = "SYN Release Management"
GROUP_PLATFORM = "SYN Platform Ops"
GROUP_DESK = "SYN Service Desk"

SIGNATURES = (
    ("SYN rotate application log files", "cmdb_ci_appl", "SYN Store DevOps", "store"),
    ("SYN clear temporary export files", "cmdb_ci_appl", "SYN Store DevOps", "store"),
    ("SYN refresh read-only cache", "cmdb_ci_linux_server", "SYN Store DevOps", "store"),
    ("SYN renew non-prod monitoring certificate", "cmdb_ci_appl", "SYN Payments DevOps", "pay"),
    ("SYN update service health dashboard", "cmdb_ci_appl", "SYN Payments DevOps", "pay"),
    ("SYN rebuild search suggestion index", "cmdb_ci_linux_server", "SYN Payments DevOps", "pay"),
    ("SYN rotate service account key for batch", "cmdb_ci_appl", GROUP_PLATFORM, "hr"),
    ("SYN compact archive tables", "cmdb_ci_db_instance", GROUP_PLATFORM, "hr"),
    ("SYN reload feature flag snapshot", "cmdb_ci_appl", GROUP_PLATFORM, "hr"),
    ("SYN synchronize reference price list", "cmdb_ci_appl", "SYN Store DevOps", "store"),
    ("SYN recycle application connection pool", "cmdb_ci_linux_server", GROUP_PLATFORM, "hr"),
    ("SYN republish static help content", "cmdb_ci_appl", GROUP_PLATFORM, "hr"),
)

STRONG = {
    "ordered_backout": True,
    "backout_trigger": True,
    "test_criteria": True,
    "implementation_owner": True,
}
WEAK = {
    "ordered_backout": False,
    "backout_trigger": False,
    "test_criteria": True,
    "implementation_owner": True,
}

RELEASE_VERSIONS = ("2025.11.0", "2026.01.0", "2026.03.0", "2026.05.0", "2026.07.0")
LATE_RELEASES = {("store", "2025.11.0"), ("ful", "2026.03.0"), ("hr", "2026.05.0")}
ROLLED_BACK_RELEASES = {("pay", "2026.01.0")}

# Names carry the SYN prefix. The loader publishes each row through a Standard
# Change Template Proposal. Text must not contain "^" or "="; it is sent as one
# encoded template_value query.
TEMPLATES = (
    {
        "name": "SYN Standard rotate TLS certificate",
        "group": "SYN Store DevOps",
        "short_description": "SYN rotate TLS certificate",
        "description": (
            "Replace the TLS certificate on a non-production endpoint and reload the listener."
        ),
        "implementation_plan": "1. Install the new certificate. 2. Reload the listener.",
        "backout_plan": "Restore the previous certificate and reload the listener.",
        "test_plan": "The endpoint presents the new certificate and returns HTTP 200.",
        "justification": "Keep the certificate inside its validity window.",
    },
    {
        "name": "SYN Standard OS patch on a non-PROD server",
        "group": "SYN Platform Ops",
        "short_description": "SYN apply an OS patch on a non-PROD server",
        "description": (
            "Apply one approved operating-system patch on a non-production server and reboot it."
        ),
        "implementation_plan": "1. Apply the approved patch. 2. Reboot the server.",
        "backout_plan": "Uninstall the patch and reboot the server.",
        "test_plan": "The server answers monitoring and the patch is listed as installed.",
        "justification": "Keep non-production servers on the approved patch level.",
    },
    {
        "name": "SYN Standard restart application service",
        "group": "SYN Store DevOps",
        "short_description": "SYN restart an application service",
        "description": "Restart one application service on a non-production server.",
        "implementation_plan": "1. Stop the service. 2. Start the service.",
        "backout_plan": "Start the service again from the previous build.",
        "test_plan": "The health endpoint returns HTTP 200.",
        "justification": "Clear a stuck worker without changing the build.",
    },
    {
        "name": "SYN Standard scale out web tier node",
        "group": "SYN Store DevOps",
        "short_description": "SYN scale out one web tier node",
        "description": (
            "Add one web tier node from the existing image and attach it to the load balancer."
        ),
        "implementation_plan": (
            "1. Start a node from the current image. 2. Add it to the load balancer."
        ),
        "backout_plan": "Remove the node from the load balancer and stop it.",
        "test_plan": "The load balancer reports the new node as healthy.",
        "justification": "Add capacity for a known traffic peak.",
    },
    {
        "name": "SYN Standard update DNS CNAME",
        "group": "SYN Platform Ops",
        "short_description": "SYN update a DNS CNAME",
        "description": "Point one existing CNAME at another approved target in the same service.",
        "implementation_plan": (
            "1. Update the CNAME. 2. Confirm the resolver returns the new target."
        ),
        "backout_plan": "Restore the previous CNAME target.",
        "test_plan": (
            "The resolver returns the new target and the health endpoint returns HTTP 200."
        ),
        "justification": "Move a name to the current target without changing the application.",
    },
    {
        "name": "SYN Standard toggle a configuration flag",
        "group": "SYN Payments DevOps",
        "short_description": "SYN toggle a configuration flag",
        "description": "Turn one documented configuration flag on or off and reload the service.",
        "implementation_plan": "1. Set the flag to the requested value. 2. Reload the service.",
        "backout_plan": "Restore the previous flag value and reload the service.",
        "test_plan": (
            "The service reports the requested flag value and the health endpoint returns HTTP 200."
        ),
        "justification": "Change one documented flag without a code deploy.",
    },
)


class AnchorError(ValueError):
    """The anchor text is not a UTC date or a UTC date-time."""


def default_anchor(now: datetime | None = None) -> datetime:
    """Midnight UTC on the UTC calendar date of `now`. That date is the load date."""
    moment = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_anchor(text: str) -> datetime:
    """Parse `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` as UTC. A date is midnight."""
    raw = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    raise AnchorError("anchor must be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS in UTC")


def generate(seed: int = 42, anchor: datetime | None = None) -> dict[str, Any]:
    """Build the fixture document for `seed`. Names use Faker; everything else is fixed."""
    chosen = _as_utc(anchor) if anchor is not None else default_anchor()
    history_start = chosen - timedelta(days=365)
    cis = _cis()
    changes, incidents = _changes_and_incidents(cis, chosen)
    fixtures: dict[str, Any] = {
        "seed": seed,
        "anchor": format_utc(chosen),
        "history_start": format_utc(history_start),
        "company": "Larkspur Outfitters",
        "services": [_service_row(row) for row in SERVICES],
        "cis": [_ci_row(row) for row in cis],
        "relationships": _relationships(cis),
        "groups": _groups(),
        "users": _users(seed),
        "schedules": _schedules(),
        "changes": changes,
        "incidents": incidents,
        "templates": [dict(row) for row in TEMPLATES],
        "task_ci": _task_links(changes, cis),
        "samples": _samples(changes, incidents),
    }
    _check_shape(fixtures)
    _check_dates(fixtures, chosen, history_start)
    return fixtures


def _as_utc(anchor: datetime) -> datetime:
    if anchor.tzinfo is None:
        raise AnchorError("anchor must be timezone-aware UTC")
    return anchor.astimezone(UTC).replace(microsecond=0)


def write_fixtures(fixtures: dict[str, Any], directory: Path) -> str:
    """Write canonical JSON and return the sha256 of the fixture bytes."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(fixtures, indent=2, sort_keys=True) + "\n"
    path = directory / "fixtures.json"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _service_row(row: dict[str, Any]) -> dict[str, Any]:
    return {"key": row["key"], "name": row["name"], "tier": row["tier"], "group": row["group"]}


def _ci_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "table": row["table"],
        "ci_class": row["ci_class"],
        "service": row["service"],
        "environment": row["environment"],
        "schedule": row["schedule"],
        "payments_db": row["payments_db"],
    }


def _cis() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for service in SERVICES:
        tier_schedule = TIER1_SCHEDULE if service["tier"] == 1 else TIER23_SCHEDULE
        rows.append(
            {
                "name": service["name"],
                "table": "cmdb_ci_service",
                "ci_class": "cmdb_ci_service",
                "service": service["name"],
                "environment": "",
                "schedule": tier_schedule,
                "payments_db": False,
            }
        )
    for key, roles in APPS.items():
        service = SERVICE_BY_KEY[key]
        for role in roles:
            rows.append(_infra(f"syn-{key}-{role}", "cmdb_ci_appl", service, "prod"))
    serial = {"prod": 0, "stage": 0, "test": 0}
    for environment, counts in SERVER_COUNTS.items():
        prefix = {"prod": "prd", "stage": "stg", "test": "tst"}[environment]
        for key, count in counts.items():
            service = SERVICE_BY_KEY[key]
            for _ in range(count):
                serial[environment] += 1
                number = serial[environment]
                kind = "lx" if number % 10 < 7 else "win"
                table = "cmdb_ci_linux_server" if kind == "lx" else "cmdb_ci_win_server"
                name = f"syn-{prefix}-{kind}-{number:03d}"
                rows.append(_infra(name, table, service, environment))
    rows.extend(_databases())
    rows.extend(_load_balancers())
    rows.extend(_network())
    return rows


def _infra(name: str, table: str, service: dict[str, Any], environment: str) -> dict[str, Any]:
    tier1_prod = environment == "prod" and service["tier"] == 1
    return {
        "name": name,
        "table": table,
        "ci_class": table,
        "service": service["name"],
        "environment": environment,
        "schedule": TIER1_SCHEDULE if tier1_prod else TIER23_SCHEDULE,
        "payments_db": False,
    }


def _databases() -> list[dict[str, Any]]:
    specs = [("pay", "prod", 7), ("pay", "stage", 2), ("pay", "test", 2)]
    specs += [("ful", "prod", 6), ("ful", "stage", 2), ("ful", "test", 2)]
    specs += [("store", "prod", 8), ("store", "stage", 2), ("store", "test", 2)]
    specs += [("hr", "prod", 4), ("hr", "stage", 1), ("hr", "test", 1)]
    rows = [
        {
            "name": "syn-shared-sqlclu-prd-01",
            "table": "cmdb_ci_db_instance",
            "ci_class": "cmdb_ci_db_instance",
            "service": "SYN Payments",
            "environment": "prod",
            "schedule": TIER1_SCHEDULE,
            "payments_db": True,
        }
    ]
    serial: dict[tuple[str, str], int] = {}
    prefix = {"prod": "prd", "stage": "stg", "test": "tst"}
    for key, environment, count in specs:
        service = SERVICE_BY_KEY[key]
        for _ in range(count):
            serial[(key, environment)] = serial.get((key, environment), 0) + 1
            number = serial[(key, environment)]
            rows.append(
                {
                    "name": f"syn-{key}-db-{prefix[environment]}-{number:02d}",
                    "table": "cmdb_ci_db_instance",
                    "ci_class": "cmdb_ci_db_instance",
                    "service": service["name"],
                    "environment": environment,
                    "schedule": TIER1_SCHEDULE
                    if environment == "prod" and service["tier"] == 1
                    else TIER23_SCHEDULE,
                    "payments_db": key == "pay",
                }
            )
    return rows


def _load_balancers() -> list[dict[str, Any]]:
    rows = [
        {
            "name": "syn-shared-lb-prd-01",
            "table": "cmdb_ci_lb",
            "ci_class": "cmdb_ci_lb",
            "service": "SYN Online Store",
            "environment": "prod",
            "schedule": TIER1_SCHEDULE,
            "payments_db": False,
        }
    ]
    specs = [("store", 6), ("pay", 5), ("ful", 4), ("hr", 4)]
    for key, count in specs:
        service = SERVICE_BY_KEY[key]
        for number in range(1, count + 1):
            environment = "prod" if number <= max(count - 2, 1) else "stage"
            rows.append(
                _infra(f"syn-{key}-lb-{number:02d}", "cmdb_ci_lb", service, environment)
            )
    return rows


def _network() -> list[dict[str, Any]]:
    rows = []
    classes = (
        ("sw", "cmdb_ci_ip_switch", 8),
        ("rt", "cmdb_ci_ip_router", 6),
        ("fw", "cmdb_ci_ip_firewall", 6),
    )
    for prefix, table, count in classes:
        for number in range(1, count + 1):
            rows.append(
                {
                    "name": f"syn-net-{prefix}-{number:02d}",
                    "table": table,
                    "ci_class": table,
                    "service": "",
                    "environment": "",
                    "schedule": TIER23_SCHEDULE,
                    "payments_db": False,
                }
            )
    return rows


def _relationships(cis: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_class_service: dict[tuple[str, str], list[str]] = {}
    for row in cis:
        by_class_service.setdefault((row["ci_class"], row["service"]), []).append(row["name"])
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(parent: str, child: str, rel_type: str) -> None:
        key = (parent, child, rel_type)
        if parent == child or key in seen:
            return
        seen.add(key)
        links.append({"parent": parent, "child": child, "type": rel_type})

    servers = [row for row in cis if row["table"] in {"cmdb_ci_linux_server", "cmdb_ci_win_server"}]
    network = [row["name"] for row in cis if row["name"].startswith("syn-net-")]
    for row in cis:
        if row["ci_class"] == "cmdb_ci_appl":
            pool = [item["name"] for item in servers if item["service"] == row["service"]]
            for offset in range(9):
                add(row["name"], pool[offset % len(pool)], "Runs on::Runs")
            key = SERVICE_BY_NAME[row["service"]]["key"]
            databases = by_class_service[("cmdb_ci_db_instance", row["service"])]
            add(row["name"], databases[0], "Depends on::Used by")
            if key in {"pay", "ful"}:
                add(row["name"], "syn-shared-sqlclu-prd-01", "Depends on::Used by")
        if row["ci_class"] == "cmdb_ci_db_instance":
            pool = [item["name"] for item in servers if item["service"] == row["service"]]
            add(row["name"], pool[0], "Runs on::Runs")
        if row["ci_class"] == "cmdb_ci_lb":
            pool = [item["name"] for item in servers if item["service"] == row["service"]]
            add(row["name"], pool[0], "Hosted on::Hosts")
    for index, server in enumerate(servers):
        add(server["name"], network[index % len(network)], "Depends on::Used by")
    lb_names = [row["name"] for row in cis if row["ci_class"] == "cmdb_ci_lb"]
    apps = [row for row in cis if row["ci_class"] == "cmdb_ci_appl"]
    for index, lb_name in enumerate(lb_names):
        service_name = next(row["service"] for row in cis if row["name"] == lb_name)
        same = [row["name"] for row in apps if row["service"] == service_name]
        add(same[index % len(same)], lb_name, "Depends on::Used by")
        if len(same) > 1:
            add(same[(index + 1) % len(same)], lb_name, "Depends on::Used by")
    return links


def _groups() -> list[dict[str, str]]:
    names = [
        GROUP_RELEASE,
        "SYN Store DevOps",
        "SYN Payments DevOps",
        "SYN Fulfillment DevOps",
        GROUP_PLATFORM,
        GROUP_DESK,
    ]
    return [{"name": name} for name in names]


def _users(seed: int) -> list[dict[str, Any]]:
    faker = Faker("en_US")
    faker.seed_instance(seed)
    slots: list[tuple[str, tuple[str, ...]]] = []
    slots += [("change_manager", (GROUP_CHANGE_MANAGEMENT,))] * 3
    slots += [("cab", (GROUP_CAB, GROUP_ECAB))] * 3
    slots += [("cab", (GROUP_CAB,))] * 2
    slots += [("release_manager", (GROUP_RELEASE,))] * 2
    slots += [("devops", ("SYN Store DevOps",))] * 6
    slots += [("devops", ("SYN Payments DevOps",))] * 6
    slots += [("devops", ("SYN Fulfillment DevOps",))] * 6
    slots += [("platform", (GROUP_PLATFORM,))] * 6
    slots += [("service_desk", (GROUP_DESK,))] * 6
    users = []
    used: set[str] = set()
    for index, (role, groups) in enumerate(slots, start=1):
        first = _slug(faker.first_name()) or "user"
        last = _slug(faker.last_name()) or "name"
        user_name = f"syn.{first}.{last}"
        if user_name in used:
            user_name = f"{user_name}.{index}"
        used.add(user_name)
        users.append(
            {
                "user_name": user_name,
                "first_name": first,
                "last_name": last,
                "email": f"{user_name}@example.com",
                "role": role,
                "groups": list(groups),
            }
        )
    return users


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(char for char in ascii_text.lower() if char.isalpha())


def _schedules() -> list[dict[str, Any]]:
    return [
        {
            "name": TIER1_SCHEDULE,
            "time_zone": "US/Eastern",
            "spans": [
                {
                    "name": "SYN Saturday night",
                    "start_date_time": "20110101T220000",
                    "end_date_time": "20110102T040000",
                    "repeat_type": "weekly",
                    "days_of_week": "6",
                }
            ],
        },
        {
            "name": TIER23_SCHEDULE,
            "time_zone": "US/Eastern",
            "spans": [
                {
                    "name": "SYN Tuesday evening",
                    "start_date_time": "20110104T200000",
                    "end_date_time": "20110104T230000",
                    "repeat_type": "weekly",
                    "days_of_week": "2",
                },
                {
                    "name": "SYN Thursday evening",
                    "start_date_time": "20110106T200000",
                    "end_date_time": "20110106T230000",
                    "repeat_type": "weekly",
                    "days_of_week": "4",
                },
            ],
        },
    ]


def _changes_and_incidents(
    cis: list[dict[str, Any]],
    anchor: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    changes: list[dict[str, Any]] = []
    incidents: list[dict[str, Any]] = []
    pools = _pools(cis)

    for signature_index, (text, ci_class, group, service_key) in enumerate(SIGNATURES):
        service = SERVICE_BY_KEY[service_key]["name"]
        matches = pools[(ci_class, service)]
        for copy in range(12):
            changes.append(
                _closed(
                    service=service,
                    group=group,
                    ci=matches[(signature_index + copy) % len(matches)],
                    ci_class=ci_class,
                    change_type="normal",
                    method="automated",
                    quality=STRONG,
                    close_code="successful",
                    friday=False,
                    month_slot=(signature_index * 12 + copy) % 12,
                    summary=text,
                )
            )

    pay_dbs = [row["name"] for row in cis if row["payments_db"]]
    for index in range(80):
        changes.append(
            _closed(
                service="SYN Payments",
                group="SYN Payments DevOps",
                ci=pay_dbs[index % len(pay_dbs)],
                ci_class="cmdb_ci_db_instance",
                change_type="normal",
                method="automated",
                quality=STRONG,
                close_code="unsuccessful" if index < 16 else "successful",
                friday=False,
                month_slot=index % 12,
                summary=f"SYN Payments database change {index + 1}",
                payments_db=True,
            )
        )

    ful_cis = pools[("cmdb_ci_appl", "SYN Order Fulfillment")]
    for index in range(160):
        weak = index < 48
        if weak:
            failed = index < 13
        else:
            failed = index < 48 + 12
        changes.append(
            _closed(
                service="SYN Order Fulfillment",
                group="SYN Fulfillment DevOps",
                ci=ful_cis[index % len(ful_cis)],
                ci_class="cmdb_ci_appl",
                change_type="normal",
                method="automated",
                quality=WEAK if weak else STRONG,
                close_code="unsuccessful" if failed else "successful",
                friday=False,
                month_slot=index % 12,
                summary=f"SYN fulfillment application change {index + 1}",
            )
        )

    rest_plan = (
        [("friday-success", "automated", "successful", True)] * 70
        + [("manual-fail", "manual", "unsuccessful", False)] * 13
        + [("auto-fail", "automated", "unsuccessful", False)] * 4
        + [("manual-success", "manual", "successful", False)] * 100
        + [("auto-success", "automated", "successful", False)] * 113
    )
    rest_services = ("store", "pay", "hr")
    for index, (label, method, close_code, friday) in enumerate(rest_plan):
        service = SERVICE_BY_KEY[rest_services[index % 3]]
        apps = pools[("cmdb_ci_appl", service["name"])]
        changes.append(
            _closed(
                service=service["name"],
                group=service["group"],
                ci=apps[index % len(apps)],
                ci_class="cmdb_ci_appl",
                change_type="normal",
                method=method,
                quality=STRONG,
                close_code=close_code,
                friday=friday,
                month_slot=index % 12,
                summary=f"SYN {service['key']} normal change {label} {index + 1}",
            )
        )

    for index in range(13):
        service = SERVICE_BY_KEY[("store", "pay", "hr")[index % 3]]
        servers = [
            row["name"]
            for row in cis
            if row["service"] == service["name"] and row["table"] == "cmdb_ci_linux_server"
        ]
        changes.append(
            _closed(
                service=service["name"],
                group=service["group"],
                ci=servers[index % len(servers)],
                ci_class="cmdb_ci_linux_server",
                change_type="standard",
                method="manual",
                quality=STRONG,
                close_code="unsuccessful",
                friday=True,
                month_slot=index % 12,
                summary=f"SYN standard friday change {index + 1}",
            )
        )
    for index in range(642):
        service = SERVICE_BY_KEY[("store", "pay", "hr")[index % 3]]
        apps = pools[("cmdb_ci_appl", service["name"])]
        changes.append(
            _closed(
                service=service["name"],
                group=service["group"],
                ci=apps[index % len(apps)],
                ci_class="cmdb_ci_appl",
                change_type="standard",
                method="automated",
                quality=STRONG,
                close_code="successful",
                friday=False,
                month_slot=index % 12,
                summary=f"SYN standard change {index + 1}",
            )
        )

    emergency_plan = (
        [("friday-success", "automated", "successful", True)] * 37
        + [("fail", "automated", "unsuccessful", False)] * 17
        + [("manual-success", "manual", "successful", False)] * 54
        + [("auto-success", "automated", "successful", False)] * 8
    )
    for index, (_label, method, close_code, friday) in enumerate(emergency_plan):
        service = SERVICE_BY_KEY[("store", "pay", "hr")[index % 3]]
        apps = pools[("cmdb_ci_appl", service["name"])]
        changes.append(
            _closed(
                service=service["name"],
                group=service["group"],
                ci=apps[index % len(apps)],
                ci_class="cmdb_ci_appl",
                change_type="emergency",
                method=method,
                quality=STRONG,
                close_code=close_code,
                friday=friday,
                month_slot=index % 12,
                summary=f"SYN emergency change {index + 1}",
            )
        )

    canceled_types = (("standard",) * 20) + (("normal",) * 21) + (("emergency",) * 4)
    for index, change_type in enumerate(canceled_types):
        service = SERVICE_BY_KEY[("store", "pay", "hr")[index % 3]]
        apps = pools[("cmdb_ci_appl", service["name"])]
        opened = _tuesday(index % 12) - timedelta(days=3)
        changes.append(
            _base(
                service=service["name"],
                group=service["group"],
                ci=apps[index % len(apps)],
                ci_class="cmdb_ci_appl",
                change_type=change_type,
                method="automated",
                quality=STRONG,
                state="4",
                approval="not requested",
                close_code="",
                summary=f"SYN canceled {change_type} change {index + 1}",
                opened_at=opened,
                friday=False,
            )
        )

    releases = _releases(cis)
    _link_release_members(changes, releases)
    changes.extend(releases)
    _link_triggers(changes, incidents)
    _link_caused_by(changes, incidents)
    incidents.extend(_open_incidents(cis, anchor))
    changes.extend(_open_changes(cis, anchor))
    _assign_keys(changes, incidents)
    return changes, incidents


def _pools(cis: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    pools: dict[tuple[str, str], list[str]] = {}
    for row in cis:
        if row["service"]:
            pools.setdefault((row["ci_class"], row["service"]), []).append(row["name"])
    return pools


def _closed(**kwargs: Any) -> dict[str, Any]:
    opened = _moment(kwargs.pop("month_slot"), kwargs["friday"])
    return _base(
        state="3",
        approval="approved",
        opened_at=opened - timedelta(days=5),
        work_start=opened,
        work_end=opened + timedelta(hours=2),
        closed_at=opened + timedelta(hours=3),
        start_date=opened,
        end_date=opened + timedelta(hours=2),
        **kwargs,
    )


def _base(
    *,
    service: str,
    group: str,
    ci: str,
    ci_class: str,
    change_type: str,
    method: str,
    quality: dict[str, bool],
    state: str,
    approval: str,
    close_code: str,
    summary: str,
    opened_at: datetime,
    friday: bool,
    payments_db: bool = False,
    work_start: datetime | None = None,
    work_end: datetime | None = None,
    closed_at: datetime | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    kind: str = "historical",
    release: bool = False,
) -> dict[str, Any]:
    plans = _plans(method, quality, group)
    tier = SERVICE_BY_NAME[service]["tier"]
    return {
        "key": "",
        "kind": kind,
        "release": release,
        "short_description": summary,
        "description": f"Larkspur Outfitters change for {service}. {summary}",
        "type": change_type,
        "state": state,
        "active": state not in {"3", "4"},
        "approval": approval,
        "impact": str(tier),
        "opened_at": format_utc(opened_at),
        "closed_at": format_utc(closed_at) if closed_at else "",
        "work_start": format_utc(work_start) if work_start else "",
        "work_end": format_utc(work_end) if work_end else "",
        "start_date": format_utc(start_date) if start_date else "",
        "end_date": format_utc(end_date) if end_date else "",
        "close_code": close_code,
        "close_notes": f"SYN close notes for {summary}" if close_code else "",
        "assignment_group": group,
        "cmdb_ci": ci,
        "ci_class": ci_class,
        "service": service,
        "environment": "prod",
        "parent": "",
        "requested_by_role": "service_desk",
        "deployment_method": method,
        "plan_quality": dict(quality),
        "payments_db": payments_db,
        "friday_evening": friday,
        "chg_model": MODELS[change_type],
        **plans,
        "justification": f"Keep {service} within its agreed service level.",
    }


def _plans(method: str, quality: dict[str, bool], owner: str) -> dict[str, str]:
    label = "AUTOMATED" if method == "automated" else "MANUAL"
    if quality["ordered_backout"] and quality["backout_trigger"]:
        backout = (
            "1. Stop the service.\n"
            "2. Restore the previous build.\n"
            "Trigger: the health check fails. Backout duration: 20 minutes."
        )
    else:
        backout = "Revert if needed."
    if quality["test_criteria"]:
        test_plan = (
            "1. Call the health endpoint.\n"
            "Success criteria: HTTP 200 and error rate under 1 percent."
        )
    else:
        test_plan = "Check that it works."
    if quality["implementation_owner"]:
        implementation = (
            f"Deployment method: {label}\n"
            f"1. Owner: {owner}. Apply the change.\n"
            "2. Restart the service."
        )
    else:
        implementation = f"Deployment method: {label}\nMake the change."
    return {
        "implementation_plan": implementation,
        "backout_plan": backout,
        "test_plan": test_plan,
    }


def _moment(slot: int, friday: bool) -> datetime:
    year, month = _month(slot)
    if friday:
        day = _nth_weekday(year, month, 4, 2)
        return datetime(year, month, day, 18, 0, tzinfo=EASTERN).astimezone(UTC)
    return _tuesday(slot)


def _tuesday(slot: int) -> datetime:
    year, month = _month(slot)
    day = _nth_weekday(year, month, 1, 2)
    return datetime(year, month, day, 10, 0, tzinfo=EASTERN).astimezone(UTC)


def _month(slot: int) -> tuple[int, int]:
    months = []
    year, month = 2025, 11
    for _ in range(12):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months[slot % 12]


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int:
    first = datetime(year, month, 1, tzinfo=UTC)
    offset = (weekday - first.weekday()) % 7
    return 1 + offset + (n - 1) * 7


def _releases(cis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    releases = []
    for service in SERVICES:
        for version in RELEASE_VERSIONS:
            late = (service["key"], version) in LATE_RELEASES
            rolled = (service["key"], version) in ROLLED_BACK_RELEASES
            year, month = int(version[:4]), int(version[5:7])
            day = _nth_weekday(year, month, 5, 1)
            start = datetime(year, month, day, 22, 0, tzinfo=EASTERN).astimezone(UTC)
            end = start + timedelta(hours=6)
            work_end = end + timedelta(days=5) if late else end
            releases.append(
                _base(
                    service=service["name"],
                    group=GROUP_RELEASE,
                    ci=service["name"],
                    ci_class="cmdb_ci_service",
                    change_type="normal",
                    method="automated",
                    quality=STRONG,
                    state="3",
                    approval="approved",
                    close_code="unsuccessful" if rolled else "successful",
                    summary=f"SYN RELEASE {service['name']} {version}",
                    opened_at=start - timedelta(days=7),
                    friday=False,
                    work_start=start,
                    work_end=work_end,
                    closed_at=work_end + timedelta(hours=1),
                    start_date=start,
                    end_date=end,
                    kind="release",
                    release=True,
                )
            )
    return releases


def _link_release_members(changes: list[dict[str, Any]], releases: list[dict[str, Any]]) -> None:
    by_service: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        if (
            change["type"] == "normal"
            and change["state"] == "3"
            and change["close_code"] == "successful"
            and not change["payments_db"]
            and change["short_description"] not in {row[0] for row in SIGNATURES}
        ):
            by_service.setdefault(change["service"], []).append(change)
    for release in releases:
        members = by_service[release["service"]][:4]
        del by_service[release["service"]][:4]
        for member in members:
            member["parent_release_summary"] = release["short_description"]


def _link_triggers(changes: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
    emergencies = [row for row in changes if row["type"] == "emergency" and row["state"] == "3"]
    for index, change in enumerate(emergencies[:84]):
        opened = datetime.strptime(change["opened_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        opened = opened - timedelta(hours=2 + (index % 4))
        priority = "1" if index < 10 else "2"
        impact, urgency = ("1", "1") if priority == "1" else ("1", "2")
        incident = _incident(
            summary=f"SYN trigger incident {index + 1}",
            service=change["service"],
            ci=change["cmdb_ci"],
            state="7",
            impact=impact,
            urgency=urgency,
            priority=priority,
            opened_at=opened,
            resolved_at=opened + timedelta(hours=8),
            closed_at=opened + timedelta(hours=9),
            close_code="Solution provided",
            parent="",
        )
        incidents.append(incident)
        change["trigger_summary"] = incident["short_description"]


def _link_caused_by(changes: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
    failed = [
        row
        for row in changes
        if row["close_code"] == "unsuccessful" and row["kind"] == "historical"
    ]
    for index, change in enumerate(failed[:74]):
        opened = datetime.strptime(change["work_start"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        opened = opened + timedelta(minutes=30)
        resolved = index < 14
        incidents.append(
            _incident(
                summary=f"SYN caused incident {index + 1}",
                service=change["service"],
                ci=change["cmdb_ci"],
                state="6" if resolved else "7",
                impact="2",
                urgency="2",
                priority="3",
                opened_at=opened,
                resolved_at=opened + timedelta(hours=4),
                closed_at=None if resolved else opened + timedelta(hours=6),
                close_code="Workaround provided" if resolved else "Resolved by change",
                caused_by_summary=change["short_description"],
            )
        )


def _open_incidents(cis: list[dict[str, Any]], anchor: datetime) -> list[dict[str, Any]]:
    apps = [row for row in cis if row["ci_class"] == "cmdb_ci_appl"]
    rows = []
    for index in range(6):
        ci = apps[index]
        rows.append(
            _incident(
                summary=f"SYN open incident {index + 1}",
                service=ci["service"],
                ci=ci["name"],
                state="1",
                impact="3",
                urgency="3",
                priority="4",
                opened_at=anchor - timedelta(days=1, hours=index),
                resolved_at=None,
                closed_at=None,
                close_code="",
                parent="",
            )
        )
    return rows


def _incident(
    *,
    summary: str,
    service: str,
    ci: str,
    state: str,
    impact: str,
    urgency: str,
    priority: str,
    opened_at: datetime,
    resolved_at: datetime | None,
    closed_at: datetime | None,
    close_code: str,
    parent: str = "",
    caused_by_summary: str = "",
) -> dict[str, Any]:
    return {
        "key": "",
        "short_description": summary,
        "description": f"Larkspur Outfitters incident for {service}. {summary}",
        "state": state,
        "active": state not in {"6", "7", "8"},
        "impact": impact,
        "urgency": urgency,
        "priority": priority,
        "opened_at": format_utc(opened_at),
        "resolved_at": format_utc(resolved_at) if resolved_at else "",
        "closed_at": format_utc(closed_at) if closed_at else "",
        "close_code": close_code,
        "close_notes": f"SYN incident notes for {summary}" if close_code else "",
        "cmdb_ci": ci,
        "service": service,
        "assignment_group": GROUP_DESK,
        "caller_role": "service_desk",
        "parent": parent,
        "caused_by": "",
        "caused_by_summary": caused_by_summary,
    }


def _open_changes(cis: list[dict[str, Any]], anchor: datetime) -> list[dict[str, Any]]:
    apps = [
        row
        for row in cis
        if row["ci_class"] == "cmdb_ci_appl" and row["name"] != "syn-shared-sqlclu-prd-01"
    ]
    rows = []
    for index in range(25):
        if index < 15:
            state, approval = "-2", "approved"
        elif index < 20:
            state, approval = "-5", "not requested"
        else:
            state, approval = "-4", "requested"
        ci = apps[index]
        service = SERVICE_BY_NAME[ci["service"]]
        start = anchor + timedelta(days=7 + index)
        rows.append(
            _base(
                service=service["name"],
                group=service["group"],
                ci=ci["name"],
                ci_class="cmdb_ci_appl",
                change_type="normal",
                method="automated",
                quality=STRONG,
                state=state,
                approval=approval,
                close_code="",
                summary=f"SYN open change {index + 1}",
                opened_at=anchor - timedelta(days=1),
                friday=False,
                start_date=start,
                end_date=start + timedelta(hours=2),
                kind="open",
            )
        )
    return rows


def _assign_keys(changes: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> None:
    historical = [row for row in changes if row["kind"] == "historical"]
    for index, row in enumerate(historical, start=1):
        row["key"] = f"SYN-CHG-{index:04d}"
    for index, row in enumerate([row for row in changes if row["kind"] == "open"], start=1):
        row["key"] = f"SYN-OPEN-{index:02d}"
    for row in changes:
        if row["kind"] == "release":
            version = row["short_description"].rsplit(" ", 1)[-1]
            key = SERVICE_BY_NAME[row["service"]]["key"]
            row["key"] = f"SYN-REL-{key}-{version}"
    by_summary = {row["short_description"]: row["key"] for row in changes}
    for row in changes:
        summary = row.pop("parent_release_summary", "")
        trigger = row.pop("trigger_summary", "")
        if summary:
            row["parent"] = by_summary[summary]
        elif trigger:
            # Filled after incident keys exist. Remember the summary for a second pass.
            row["trigger_summary"] = trigger
    for index, row in enumerate(incidents, start=1):
        row["key"] = f"SYN-INC-{index:04d}"
    incident_by_summary = {row["short_description"]: row["key"] for row in incidents}
    for row in incidents:
        summary = row.pop("caused_by_summary", "")
        if summary:
            row["caused_by"] = by_summary[summary]
    for row in changes:
        trigger = row.pop("trigger_summary", "")
        if trigger:
            row["parent"] = incident_by_summary[trigger]


def _samples(
    changes: list[dict[str, Any]], incidents: list[dict[str, Any]]
) -> dict[str, list[str]]:
    def first_change(predicate: Any) -> str:
        return next(row["key"] for row in changes if predicate(row))

    def first_incident(state: str) -> str:
        return next(row["key"] for row in incidents if row["state"] == state)

    return {
        "changes": [
            first_change(lambda row: row["state"] == "-5"),
            first_change(lambda row: row["state"] == "-4"),
            first_change(lambda row: row["state"] == "-2"),
            first_change(lambda row: row["state"] == "3" and row["kind"] == "historical"),
            first_change(lambda row: row["state"] == "4"),
        ],
        "incidents": [first_incident("1"), first_incident("6"), first_incident("7")],
    }


def _task_links(changes: list[dict[str, Any]], cis: list[dict[str, Any]]) -> list[dict[str, str]]:
    links = [{"change": row["key"], "ci": row["cmdb_ci"]} for row in changes]
    servers = [row["name"] for row in cis if "server" in row["table"]]
    extras = 2400 - len(links)
    for index, change in enumerate(changes[:extras]):
        extra = servers[index % len(servers)]
        if extra == change["cmdb_ci"]:
            extra = servers[(index + 1) % len(servers)]
        links.append({"change": change["key"], "ci": extra})
    return links


def _check_shape(fixtures: dict[str, Any]) -> None:
    changes = fixtures["changes"]
    historical = [row for row in changes if row["kind"] == "historical"]
    if len(historical) != 1500:
        raise RuntimeError(f"historical changes {len(historical)}")
    if len([row for row in changes if row["kind"] == "open"]) != 25:
        raise RuntimeError("open changes")
    if len([row for row in changes if row["release"]]) != 20:
        raise RuntimeError("releases")
    if len(fixtures["cis"]) != 300:
        raise RuntimeError(f"cis {len(fixtures['cis'])}")
    if len(fixtures["users"]) != 40:
        raise RuntimeError("users")
    if len(fixtures["task_ci"]) != 2400:
        raise RuntimeError(f"task_ci {len(fixtures['task_ci'])}")
    if len(fixtures["templates"]) != 6:
        raise RuntimeError("templates")
    if any(row["parent"] for row in fixtures["incidents"]):
        raise RuntimeError("incident.parent is not the caused-by link")
    caused = [row for row in fixtures["incidents"] if row["caused_by"]]
    if len(caused) != 74:
        raise RuntimeError(f"caused_by {len(caused)}")
    if not 540 <= len(fixtures["relationships"]) <= 660:
        raise RuntimeError(f"relationships {len(fixtures['relationships'])}")
    keys = [row["key"] for row in changes]
    if len(keys) != len(set(keys)):
        raise RuntimeError("duplicate change keys")


def _check_dates(
    fixtures: dict[str, Any], anchor: datetime, history_start: datetime
) -> None:
    """Refuse an anchor that does not cover the fixed November 2025-October 2026 calendar.

    Every opened_at is before the anchor. Completion timestamps are not later
    than the anchor. Only an open change's planned start and end may fall in
    the next 6 weeks.
    """
    # history_start is the anchor minus 365 days. The 2025.11.0 releases open
    # one day before that when the anchor is 2026-10-27, so the lower bound is
    # enforced on implemented non-release changes. Those are the P1-P6 rows.
    # Every historical timestamp still has to be before the anchor.
    latest = history_start
    for row in fixtures["changes"]:
        if row["kind"] == "open":
            continue
        for field in ("opened_at", "closed_at", "work_start", "work_end", "start_date", "end_date"):
            moment = _stamp(row.get(field, ""))
            if moment is not None:
                latest = max(latest, moment)
        if row["release"] or row["state"] != "3":
            continue
        opened = parse_utc(row["opened_at"])
        if opened < history_start or opened >= anchor:
            raise RuntimeError(
                "anchor does not cover the fixed history calendar "
                f"({row['key']} opened_at {row['opened_at']})"
            )
    for row in fixtures["incidents"]:
        if row["state"] == "1":
            continue
        for field in ("opened_at", "resolved_at", "closed_at"):
            moment = _stamp(row.get(field, ""))
            if moment is not None:
                latest = max(latest, moment)
    if latest >= anchor:
        raise RuntimeError(
            "anchor does not cover the fixed history calendar "
            f"(latest {format_utc(latest)})"
        )
    limit = anchor + OPEN_WINDOW
    for row in fixtures["changes"]:
        opened = parse_utc(row["opened_at"])
        if opened >= anchor:
            raise RuntimeError(f"{row['key']} opened_at is not before the anchor")
        for field in ("closed_at", "work_end"):
            moment = _stamp(row.get(field, ""))
            if moment is not None and moment > anchor:
                raise RuntimeError(f"{row['key']} {field} is later than the anchor")
        if row["kind"] != "open":
            continue
        if row["work_start"] or row["work_end"] or row["closed_at"]:
            raise RuntimeError(f"{row['key']} open change has a completion date")
        start = parse_utc(row["start_date"])
        end = parse_utc(row["end_date"])
        if not (anchor < start <= limit and anchor < end <= limit):
            raise RuntimeError(f"{row['key']} planned dates are outside the next 6 weeks")
    for row in fixtures["incidents"]:
        opened = parse_utc(row["opened_at"])
        if opened >= anchor:
            raise RuntimeError(f"{row['key']} opened_at is not before the anchor")
        for field in ("resolved_at", "closed_at"):
            moment = _stamp(row.get(field, ""))
            if moment is None:
                continue
            if moment > anchor:
                raise RuntimeError(f"{row['key']} {field} is later than the anchor")
            if moment < opened:
                raise RuntimeError(f"{row['key']} {field} is earlier than opened_at")


def _stamp(text: str) -> datetime | None:
    if not text:
        return None
    return parse_utc(text)
