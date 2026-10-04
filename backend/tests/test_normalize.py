from decimal import Decimal

import pytest

from app.services.importer.normalize import (
    brand_candidates,
    normalize_bool,
    normalize_capacity,
    normalize_form_factor,
    normalize_frequency,
    normalize_interface,
    normalize_number,
    normalize_text,
    parse_number,
    split_erp_codes,
    to_halfwidth,
)


def test_halfwidth_punctuation():
    assert to_halfwidth("江波龙（Airdisk）") == "江波龙(Airdisk)"
    assert to_halfwidth("足容，固带；TLC") == "足容,固带;TLC"
    assert to_halfwidth("ＡＢＣ１２３") == "ABC123"
    assert to_halfwidth("a　b") == "a b"


def test_normalize_text():
    assert normalize_text("  SO   DIMM ") == "so dimm"
    assert normalize_text("凯威（keyway）") == "凯威(keyway)"
    assert normalize_text(None) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8GB", "8"),
        ("8G", "8"),
        ("8 GB", "8"),
        ("8g", "8"),
        (8, "8"),
        (Decimal("8.0"), "8"),
        ("1T", "1024"),
        ("1TB", "1024"),
        ("2T", "2048"),
        ("512M", "0.5"),
        ("128G 2280 SATA", "128"),
        ("16 gb", "16"),
        ("", ""),
        (None, ""),
    ],
)
def test_capacity(raw, expected):
    assert normalize_capacity(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2666MHZ", "2666"),
        ("2666 MHz", "2666"),
        ("2666", "2666"),
        (2666, "2666"),
        ("8533", "8533"),
        ("3.2GHz", "3200"),
        ("5600MT/s", "5600"),
    ],
)
def test_frequency(raw, expected):
    assert normalize_frequency(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SO DIMM", "sodimm"),
        ("SODIMM", "sodimm"),
        ("SO-DIMM", "sodimm"),
        ("so dimm", "sodimm"),
        ("SO/U DIMM", "so_u_dimm"),
        ("SO/UDIMM", "so_u_dimm"),
        ("SO-U", "so_u_dimm"),
        ("U DIMM", "udimm"),
        ("2280", "2280"),
    ],
)
def test_form_factor(raw, expected):
    assert normalize_form_factor(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PCIE3.0", "pcie3"),
        ("PCIe 3.0", "pcie3"),
        ("PCIE3", "pcie3"),
        ("PCIe Gen3", "pcie3"),
        ("PCIE4.0", "pcie4"),
        ("PCIe4.0 x4", "pcie4"),
        ("SATA", "sata"),
        ("SATA3", "sata"),
        ("CNVi", "cnvi"),
    ],
)
def test_interface(raw, expected):
    assert normalize_interface(raw) == expected


def test_number_and_bool():
    assert normalize_number("28") == "28"
    assert normalize_number("6.7100") == "6.71"
    assert normalize_number(6.71) == "6.71"
    assert normalize_number("n/a") == "n/a"
    assert normalize_bool(True) == "1"
    assert normalize_bool("是") == "1"
    assert normalize_bool("no") == "0"
    assert normalize_bool(None) == ""


def test_brand_candidates_split_bilingual_cells():
    assert brand_candidates("江波龙（Airdisk）") == ["江波龙(airdisk)", "江波龙", "airdisk"]
    assert brand_candidates("沃存(Wodposit)") == ["沃存(wodposit)", "沃存", "wodposit"]
    assert brand_candidates("SK hynix") == ["skhynix"]
    assert brand_candidates("") == []


def test_split_erp_codes():
    assert split_erp_codes("E.I.P.0000455") == ["E.I.P.0000455"]
    assert split_erp_codes("E.M.R.0000036/E.M.R.0000037") == ["E.M.R.0000036", "E.M.R.0000037"]
    assert split_erp_codes("/") == []
    assert split_erp_codes("-") == []
    assert split_erp_codes(None) == []
    assert split_erp_codes(" e.i.p.0000455 ") == ["E.I.P.0000455"]


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("28W", "W", "28"),
        ("28 w", "W", "28"),
        ("14KG", "kg", "14"),
        ("24AH", "Ah", "24"),
        ("10KVA", "VA", "10000"),
        ("1.5kW", "W", "1500"),
        ("10nm", "nm", "10"),
        ("1,213", None, "1213"),
        ("-49523", None, "-49523"),
        ("１２", None, "12"),
        (7, None, "7"),
        ("28W", None, None),  # a unit the field does not have
        ("28V", "W", None),
        ("about 28", "W", None),
        ("", "W", None),
        (True, None, None),
    ],
)
def test_parse_number_with_unit(raw, unit, expected):
    got = parse_number(raw, unit)
    assert (None if got is None else format(got.normalize(), "f")) == expected
