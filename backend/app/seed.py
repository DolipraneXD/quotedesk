"""First-run data: categories with attribute schemas, brands + aliases, note rules.

Seeding is idempotent and additive: rows the user already has (matched by category
code, brand canonical name, or rule pattern+field) are never overwritten, so edits
made in Settings survive restarts.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Brand, BrandAlias, Category, NoteRule
from app.services.importer.normalize import brand_key


def f(
    key: str,
    label_en: str,
    label_zh: str,
    type: str = "text",
    fp: bool = False,
    unit: str | None = None,
    options: list[str] | None = None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "key": key,
        "label_en": label_en,
        "label_zh": label_zh,
        "type": type,
        "in_fingerprint": fp,
    }
    if unit:
        field["unit"] = unit
    if options:
        field["options"] = options
    return field


MODEL = f("model", "Model", "型号", fp=True)
SPEC = f("spec_text", "Specification", "规格")

EXTRA_SCHEMA = [
    MODEL,
    SPEC,
    f("power_va", "Power (VA)", "功率(VA)", "number", unit="VA"),
    f("power_w", "Power (W)", "功率(W)", "number", unit="W"),
    f("capacity_ah", "Capacity (Ah)", "容量(Ah)", "number", unit="Ah"),
    f("size_mm", "Size (mm)", "尺寸(mm)"),
    f("weight_kg", "Weight (kg)", "重量(kg)", "number", unit="kg"),
]

GENERIC_SCHEMA = [MODEL, SPEC]

# a wearable device: identified by its model, the rest is its spec sheet
WEARABLE_SCHEMA = [
    MODEL,
    f("sensors", "Sensors", "传感器"),
    f("battery_life", "Battery life", "续航"),
    f("size", "Size", "尺寸"),
    SPEC,
]

# a complete unit; its parts are separate products, linked by a configuration
UNIT_SCHEMA = [
    MODEL,
    f("cpu", "Platform / CPU", "平台"),
    f("screen", "Screen", "屏"),
    f("memory_config", "Memory / storage", "存储"),
    f("market", "Market", "市场"),
    SPEC,
]

SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "ram_module": [
        f(
            "type",
            "Type",
            "类型",
            fp=True,
            options=["DDR3", "DDR4", "DDR5", "LPDDR4X", "LPDDR5", "LPDDR5X"],
        ),
        f("capacity_gb", "Capacity", "容量", "capacity", fp=True, unit="GB"),
        f("speed_mhz", "Speed", "频率", "frequency", fp=True, unit="MHz"),
        f(
            "form_factor",
            "Form factor",
            "规格",
            "form_factor",
            fp=True,
            options=["SODIMM", "UDIMM", "SO/U DIMM"],
        ),
        f("chip_vendor", "Chip vendor", "颗粒", "brand", fp=True),
        f("rank", "Rank", "Rank"),
        f("voltage", "Voltage", "电压"),
    ],
    "dram_chip": [
        f("type", "Type", "颗粒类型", fp=True),
        f("capacity_gb", "Capacity", "容量", "capacity", fp=True, unit="GB"),
        f("speed_mhz", "Speed", "频率", "frequency", fp=True, unit="MHz"),
        f("package_balls", "Package (balls)", "封装", fp=True),
        f("wafer_vendor", "Wafer vendor", "wafer", "brand", fp=True),
        f("platform", "Platform", "平台"),
    ],
    "ssd": [
        f("capacity_gb", "Capacity", "容量", "capacity", fp=True, unit="GB"),
        f(
            "form_factor",
            "Form factor",
            "尺寸",
            "form_factor",
            fp=True,
            options=["2280", "2242", "2230"],
        ),
        f(
            "interface",
            "Interface",
            "接口",
            "interface",
            fp=True,
            options=["SATA", "PCIe3.0", "PCIe4.0", "PCIe5.0"],
        ),
        f("nand_type", "NAND type", "闪存类型", fp=True, options=["TLC", "QLC", "MLC"]),
        f("controller", "Controller", "主控"),
        f("nand_vendor", "NAND vendor", "颗粒", "brand"),
        f("solution_text", "Solution", "方案"),
        f("full_capacity", "Full capacity", "足容", "bool"),
        f("fixed_firmware", "Fixed firmware", "固带", "bool"),
    ],
    "emmc": [
        f("capacity_gb", "Capacity", "容量", "capacity", fp=True, unit="GB"),
        f("controller_nand", "Controller + NAND", "主控+flash方案", fp=True),
        f("firmware", "Firmware", "固件", options=["Intel FW", "ARM FW"]),
    ],
    "cpu": [
        f("model", "Model", "型号", fp=True),
        f("sspec", "S-Spec", "S-Spec"),
        f("platform_family", "Platform family", "平台", fp=True),
        f("tdp_w", "TDP", "功耗", "number", unit="W"),
        f("process_nm", "Process", "制程", "number", unit="nm"),
        f("vpro", "vPro", "vPro", "bool"),
        f("ipu", "IPU", "IPU", "bool"),
        f("core_class", "Core class", "大小核", options=["大核", "小核"]),
    ],
    "wifi": [
        f("chipset", "Chipset", "芯片", fp=True),
        f("module_model", "Module model", "模组型号", fp=True),
        f("interface", "Interface", "接口", "interface", fp=True, options=["CNVi", "PCIe", "USB"]),
        f("package", "Package", "封装", options=["插卡", "贴片"]),
        f("wifi_gen", "Wi-Fi generation", "WiFi代", options=["WIFI5", "WIFI6", "WIFI6E", "WIFI7"]),
        f("streams", "Streams", "天线", options=["1T1R", "2T2R"]),
        f("vendor_module", "Module vendor", "模组厂商"),
    ],
    "tablet": UNIT_SCHEMA,
    **{code: UNIT_SCHEMA for code in ("pc", "mini_pc", "laptop", "nas", "workstation", "server")},
    **{code: WEARABLE_SCHEMA for code in ("smart_ring", "health_tracker")},
    "motherboard": [
        f("model", "Model", "机型", fp=True),
        f("sku", "SKU", "SKU", fp=True),
        f("erp_code", "Part no.", "料号"),
        f("pcb_spec", "PCB spec", "PCB规格"),
        f("cpu", "CPU", "CPU"),
        f("memory_config", "Memory config", "配置"),
        f("typec", "Type-C", "Type c"),
        f("wifi", "Wi-Fi", "WIFI"),
        f("cost_pcb", "PCB cost", "PCB", "number", unit="USD"),
        f("cost_others", "Other cost", "Others", "number", unit="USD"),
        f("cost_smt", "SMT cost", "SMT", "number", unit="USD"),
        f("cost_ttl", "Total cost", "TTL", "number", unit="USD"),
        f("fx_rate", "FX rate", "汇率", "number"),
    ],
    "hdd": [
        f("capacity_gb", "Capacity", "容量", "capacity", fp=True, unit="GB"),
        f("interface", "Interface", "接口", "interface", fp=True),
        MODEL | {"in_fingerprint": True},
        f("rpm", "RPM", "转速", "number"),
    ],
    "psu": [MODEL, f("power_w", "Power (W)", "功率(W)", "number", unit="W"), SPEC],
    "ups": EXTRA_SCHEMA,
    "battery": EXTRA_SCHEMA,
    "cabinet": EXTRA_SCHEMA,
}

# code, name_en, name_zh, is_main
CATEGORIES: list[tuple[str, str, str, bool]] = [
    ("cpu", "CPU", "处理器", True),
    ("gpu", "GPU", "显卡", True),
    ("motherboard", "Motherboard", "主板", True),
    ("ram_module", "RAM module", "内存条", True),
    ("dram_chip", "DRAM chip", "内存颗粒", True),
    ("ssd", "SSD", "固态硬盘", True),
    ("hdd", "HDD", "机械硬盘", True),
    ("emmc", "eMMC", "eMMC", True),
    ("psu", "Power supply", "电源", True),
    ("wifi", "Wi-Fi module", "无线网卡", True),
    ("display", "Display", "显示屏", True),
    ("battery", "Battery", "电池", False),
    ("camera", "Camera", "摄像头", False),
    ("cooling", "Cooling", "散热", False),
    ("case", "Case", "机箱", False),
    ("keyboard", "Keyboard", "键盘", False),
    ("adapter", "Adapter", "适配器", False),
    ("cable", "Cable", "线材", False),
    ("ups", "UPS", "不间断电源", False),
    ("cabinet", "Battery cabinet", "电池柜", False),
    ("service", "Service", "服务", False),
    ("other", "Other", "其他", False),
    ("tablet", "Tablet", "平板电脑", True),
    # finished devices (Sixunited product lines); same codes as the device types
    ("pc", "Desktop PC", "台式机", True),
    ("mini_pc", "Mini PC", "迷你主机", True),
    ("laptop", "Laptop", "笔记本电脑", True),
    ("nas", "NAS", "NAS", True),
    ("workstation", "Workstation", "工作站", True),
    ("server", "Server", "服务器", True),
    ("smart_ring", "Smart ring", "智能戒指", True),
    ("health_tracker", "Health tracker", "健康监测设备", True),
]

# canonical, name_zh, extra aliases
BRANDS: list[tuple[str, str | None, list[str]]] = [
    ("Micron", "镁光", ["美光"]),
    ("Micron (SpecTek)", None, ["SpecTek"]),
    ("SK hynix", "海力士", ["hynix", "SKhynix"]),
    ("Samsung", "三星", []),
    ("CXMT", "长鑫", []),
    ("YMTC", "长存", []),
    ("UNIS", "紫光", []),
    ("UniIC", "紫光国芯", []),
    ("Wodposit", "沃存", []),
    ("Asint", "昱联", []),
    ("Kingfast", "金速", []),
    ("ADATA", "威刚", []),
    ("Kingston", "金士顿", []),
    ("Crucial", "英睿达", []),
    ("Kimtigo", "金泰克", []),
    ("Longsys", "江波龙", ["Airdisk", "Longsys(Airdisk)"]),
    ("Exascend", "至誉", []),
    ("DGZ", "登高者", []),
    ("HOGE", "汇钜", []),
    ("KingSpec", "金胜维", []),
    ("keyway", "凯威", []),
    ("SIX", "赛可驰", []),
    ("Zettastone", "泽石", []),
    ("Phison", "群联", []),
    ("BIWIN", "佰维", []),
    ("SCY", "时创意", []),
    ("Maxio", "联芸", []),
    ("SMI", "慧荣", []),
    ("CDTech", "中龙通", []),
    ("MM", "妙明智能", []),
    ("AI-Link", "爱联科技", []),
    ("DW", "大为", []),
    ("Rockchip", "瑞芯微", []),
    ("Qualcomm", "高通", []),
    ("SanDisk", "闪迪", []),
    ("Kioxia", "铠侠", []),
    ("Intel", "英特尔", []),
    ("Yemas", None, []),
]

# pattern, field, kind, value  (plan §1.4; order matters: first match wins per field)
NOTE_RULES: list[tuple[str, str, str, str | None]] = [
    (r"接单前确认|实单前需确认", "confirm_before_order", "set", "true"),
    (r"已发停产通知|已停产|停产", "status", "set", "discontinued"),
    (r"消耗完库存不接", "status", "set", "stock_only"),
    (r"无货无供应", "status", "set", "no_supply"),
    (r"供应良好", "supply_note", "text", None),
    (r"交期需确认", "lead_time_confirm", "set", "true"),
    (r"(?<!库存)可接单?\s*([\d.]+)\s*(K|pcs)?", "max_order_qty", "qty", None),
    (r"库存可接\s*([\d.]+)\s*(K|pcs)?", "from_stock_qty", "qty", None),
    (r"预付\s*\d+\s*%", "payment_terms", "text", None),
    (r"新料需验证|需验证|待验证", "needs_validation", "set", "true"),
    (r"现询", "quote_on_request", "set", "true"),
    (r"主推", "recommended", "set", "true"),
    (r"大众市场", "market", "set", "consumer"),
]


def seed(session: Session) -> None:
    existing_codes = set(session.scalars(select(Category.code)))
    for order, (code, name_en, name_zh, is_main) in enumerate(CATEGORIES):
        if code not in existing_codes:
            session.add(
                Category(
                    code=code,
                    name_en=name_en,
                    name_zh=name_zh,
                    is_main=is_main,
                    attribute_schema=SCHEMAS.get(code, GENERIC_SCHEMA),
                    sort_order=order,
                )
            )

    existing_brands = set(session.scalars(select(Brand.canonical)))
    taken_keys = set(session.scalars(select(BrandAlias.alias_key)))
    for canonical, brand_zh, extra in BRANDS:
        if canonical in existing_brands:
            continue
        brand = Brand(canonical=canonical, name_en=canonical, name_zh=brand_zh)
        session.add(brand)
        for alias, lang in [
            (canonical, "en"),
            *([(brand_zh, "zh")] if brand_zh else []),
            *[(a, "en") for a in extra],
        ]:
            key = brand_key(alias)
            if key not in taken_keys:
                taken_keys.add(key)
                brand.aliases.append(BrandAlias(alias=alias, alias_key=key, lang=lang))

    # only into an empty table: the seller edits and deletes rules in Settings
    if session.scalar(select(NoteRule.id).limit(1)) is None:
        for order, (pattern, field, kind, value) in enumerate(NOTE_RULES):
            session.add(
                NoteRule(pattern=pattern, field=field, kind=kind, value=value, sort_order=order)
            )
    session.commit()
