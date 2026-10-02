from mapping import extract_project_number, normalize_iso_timestamp


def test_project_number_extraction():
    assert extract_project_number("1587-RMV") == "1587"
    assert extract_project_number("1588-Mesa Access Rd") == "1588"
    assert extract_project_number("No Number Project") == ""


def test_timestamp_conversion():
    assert normalize_iso_timestamp("2026-07-14T23:17:10.0000000+00:00") == (
        "2026-07-14T23:17:10Z"
    )
    assert normalize_iso_timestamp(None) is None
