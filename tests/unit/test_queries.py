from cm_agents.data.queries import CI, IMPORT_SET, STAGING_TABLE, is_synthetic_ci_name


def test_ci_query_does_not_use_a_bare_syn_prefix() -> None:
    assert "nameSTARTSWITHsyn-" in CI
    assert "name=SYN Online Store" in CI
    assert "nameSTARTSWITHSYN^" not in CI
    assert "nameSTARTSWITHSYN " not in CI


def test_task_ci_staging_table_is_removed_with_the_other_import_tables() -> None:
    assert "u_syn_taskci_import" in IMPORT_SET
    assert "u_syn_taskci_import" in STAGING_TABLE
    assert "u_syn_std_delete" in IMPORT_SET
    assert "u_syn_std_delete" in STAGING_TABLE


def test_out_of_box_package_names_are_not_synthetic() -> None:
    assert is_synthetic_ci_name("SYN Online Store")
    assert is_synthetic_ci_name("syn-shared-sqlclu-prd-01")
    assert not is_synthetic_ci_name("Synaptics Pointing Device Driver")
    assert not is_synthetic_ci_name("SynthCore")
