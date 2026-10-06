from app.seed import SCHEMAS
from app.services.importer.normalize import compute_fingerprint

ALIASES = {"海力士": "SK hynix", "skhynix": "SK hynix", "镁光": "Micron", "micron": "Micron"}


def resolve(text: str) -> str | None:
    return ALIASES.get(text.replace(" ", "").lower()) or ALIASES.get(text)


def ram(brand: str | None = "Wodposit", **attrs):
    base = {
        "type": "DDR4",
        "capacity_gb": "8GB",
        "speed_mhz": "2666MHZ",
        "form_factor": "SO DIMM",
        "chip_vendor": "海力士",
    }
    base.update(attrs)
    return compute_fingerprint("ram_module", brand, SCHEMAS["ram_module"], base, resolve)


def test_same_product_different_spellings_same_fingerprint():
    a = ram()
    b = ram(capacity_gb=8, speed_mhz="2666 MHz", form_factor="SODIMM", chip_vendor="SK hynix")
    c = ram(type="ddr4", capacity_gb="8 G", speed_mhz=2666, form_factor="so-dimm")
    assert a == b == c


def test_different_brand_different_fingerprint():
    assert ram("Wodposit") != ram("ADATA")


def test_different_chip_vendor_different_fingerprint():
    assert ram(chip_vendor="海力士") != ram(chip_vendor="镁光")


def test_non_fingerprint_attributes_ignored():
    assert ram(rank="1R", voltage="1.2V") == ram()


def test_capacity_units_matter():
    assert ram(capacity_gb="16GB") != ram()


def test_ssd_interface_and_capacity_spellings():
    schema = SCHEMAS["ssd"]

    def ssd(**attrs):
        return compute_fingerprint("ssd", "keyway", schema, attrs, resolve)

    a = ssd(capacity_gb="1T", form_factor="2280", interface="PCIE4.0", nand_type="QLC")
    b = ssd(capacity_gb="1024GB", form_factor="2280", interface="PCIe 4.0", nand_type="qlc")
    assert a == b
    assert a != ssd(capacity_gb="1T", form_factor="2280", interface="PCIE3.0", nand_type="QLC")


def test_category_is_part_of_fingerprint():
    attrs = {"model": "SP10KS"}
    schema = SCHEMAS["ups"]
    assert compute_fingerprint("ups", None, schema, attrs) != compute_fingerprint(
        "battery", None, schema, attrs
    )


def test_name_fallback_when_no_identifying_attribute():
    schema = SCHEMAS["ups"]
    a = compute_fingerprint("other", None, schema, {}, name_zh="安装服务")
    b = compute_fingerprint("other", None, schema, {}, name_zh="运输服务")
    assert a != b
    assert a == compute_fingerprint("other", None, schema, {}, name_zh=" 安装服务 ")


def test_fingerprint_is_stable_sha1():
    fp = ram()
    assert len(fp) == 40
    assert fp == ram()
