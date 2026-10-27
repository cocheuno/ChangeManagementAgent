"""Queries that match synthetic rows and leave out-of-box rows alone.

ServiceNow STARTSWITH is case-insensitive, and a trailing space in a query
value is trimmed. ``nameSTARTSWITHSYN`` therefore also matches the out-of-box
CIs ``Synaptics Pointing Device Driver`` and ``SynthCore``. Infrastructure
names use the ``syn-`` prefix. The four service names are matched in full.
"""

SERVICE_CI_NAMES = (
    "SYN Online Store",
    "SYN Payments",
    "SYN Order Fulfillment",
    "SYN HR Portal",
)
GROUP_NAMES = (
    "SYN Release Management",
    "SYN Store DevOps",
    "SYN Payments DevOps",
    "SYN Fulfillment DevOps",
    "SYN Platform Ops",
    "SYN Service Desk",
)
# Seed adds memberships only in these groups. The integration user's
# platform-managed "Conditional Script Writer" membership is not one of them.
OWNED_MEMBERSHIP_GROUPS = GROUP_NAMES + (
    "Change Management",
    "CAB Approval",
    "eCAB Approval",
)
SPAN_NAMES = (
    "SYN Saturday night",
    "SYN Tuesday evening",
    "SYN Thursday evening",
)


def _or_equals(field: str, names: tuple[str, ...]) -> str:
    return "^OR".join(f"{field}={name}" for name in names)


CI = "nameSTARTSWITHsyn-^OR" + _or_equals("name", SERVICE_CI_NAMES)
RELATIONSHIP = "parent.nameSTARTSWITHsyn-^OR" + _or_equals("parent.name", SERVICE_CI_NAMES)
GROUP = _or_equals("name", GROUP_NAMES)
SCHEDULE = "nameSTARTSWITHSYN Tier-"
SPAN = _or_equals("name", SPAN_NAMES)
CHANGE = "correlation_idSTARTSWITHSYN-"
INCIDENT = "correlation_idSTARTSWITHSYN-"
TASK_CI = "task.correlation_idSTARTSWITHSYN-"
USER = "user_nameSTARTSWITHsyn."
MEMBERSHIP = "user.user_nameSTARTSWITHsyn."
ROLE = "user.user_nameSTARTSWITHsyn."
TEMPLATE = "nameSTARTSWITHSYN Tier-^ORnameSTARTSWITHSYN Standard"
PROPOSAL = (
    "template_nameSTARTSWITHSYN Standard^ORshort_descriptionSTARTSWITHSYN Standard"
)
STD_TEMPLATE = "nameSTARTSWITHSYN Standard"
STD_VERSION = "std_change_producer.nameSTARTSWITHSYN Standard"
STD_DELETE_STAGE = "u_syn_std_delete"
STD_DELETE_MAP = "SYN Standard Template Delete"
BLACKOUT = "nameSTARTSWITHSYN Freeze"
IMPORT_SET = (
    "table_name=u_syn_chg_import^ORtable_name=u_syn_inc_import"
    "^ORtable_name=u_syn_taskci_import^ORtable_name=u_syn_std_delete"
)
TRANSFORM_MAP = (
    "name=SYN Change Import^ORname=SYN Incident Import^ORname=SYN Task CI Import"
    "^ORname=SYN Standard Template Delete"
)
TRANSFORM_ENTRY = (
    "source_table=u_syn_chg_import^ORsource_table=u_syn_inc_import"
    "^ORsource_table=u_syn_taskci_import^ORsource_table=u_syn_std_delete"
)
DICTIONARY = (
    "name=u_syn_chg_import^ORname=u_syn_inc_import^ORname=u_syn_taskci_import"
    "^ORname=u_syn_std_delete"
)
STAGING_TABLE = (
    "name=u_syn_chg_import^ORname=u_syn_inc_import^ORname=u_syn_taskci_import"
    "^ORname=u_syn_std_delete"
)


def is_synthetic_ci_name(name: str) -> bool:
    """True for fixture CI names and false for the two out-of-box packages."""
    folded = name.lower()
    return folded.startswith("syn ") or folded.startswith("syn-")
