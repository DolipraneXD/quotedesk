"""Recorded model output for the sample files, and a fake extractor that replays it.

The rows below are what the extraction prompt asks the model to return for real rows of
``wifi_price_20260929.xlsx`` and ``motherboard_cost.xlsx`` (values copied from the cells),
the four screenshots and the UPS quotation PDF.
They let the whole pipeline (normalize, match, review, commit, revert) run offline and
deterministically; ``test_golden_live.py`` checks the live model against the same rules.
"""

from __future__ import annotations

import copy
import re
from decimal import Decimal
from typing import Any

from app.services.importer.llm_parser import ChunkContext, ChunkResult, OutputTooLong


def price(amount: str, column: str, **kw: Any) -> dict[str, Any]:
    return {
        "tier": kw.get("tier", "standard"),
        "amount": Decimal(amount),
        "currency": kw.get("currency", "USD"),
        "column": column,
        "date": kw.get("date"),
        "original_amount": Decimal(kw["original_amount"]) if kw.get("original_amount") else None,
        "original_currency": kw.get("original_currency"),
        "fx_rate": Decimal(kw["fx_rate"]) if kw.get("fx_rate") else None,
    }


def row(source_row: int, category: str, name_zh: str, **kw: Any) -> dict[str, Any]:
    return {
        "source_row": source_row,
        "category_code": category,
        "name_zh": name_zh,
        "name_en": kw.get("name_en"),
        "brand": kw.get("brand"),
        "erp_codes": kw.get("erp_codes", []),
        "mpn": kw.get("mpn"),
        "attributes": [{"key": k, "value": v} for k, v in kw.get("attributes", {}).items()],
        "prices": kw.get("prices", []),
        "no_price_reason": kw.get("no_price_reason"),
        "stock_qty": kw.get("stock_qty"),
        "demand_qty": kw.get("demand_qty"),
        "stock_after_qty": kw.get("stock_after_qty"),
        "notes_raw": kw.get("notes_raw"),
        "platform": kw.get("platform"),
        "confidence": Decimal(kw.get("confidence", "0.95")),
        "issues": kw.get("issues", []),
    }


def intel(n: int, iface: str, erp: str, model: str, amount: str | None, stock: tuple, note: str):
    chipset = model.split(".")[0]
    return row(
        n,
        "wifi",
        f"Intel {model} {iface}",
        name_en=f"Intel {chipset} Wi-Fi module ({iface})",
        brand="Intel",
        erp_codes=[erp],
        mpn=model,
        attributes={"chipset": chipset, "module_model": model, "interface": iface},
        prices=[price(amount, "F")] if amount else [],
        no_price_reason=None if amount else "-",
        stock_qty=stock[0],
        demand_qty=stock[1],
        stock_after_qty=stock[2],
        notes_raw=note,
    )


INTEL_WIFI = [
    intel(4, "CNVI", "E.M.W.0000119", "AX101.NGWG.NV,999CV1", "3.1", (1734, 51257, -49523),
          "已停产，接单前确认"),
    intel(5, "CNVI", "E.M.W.0000118", "AX101.D2WG.NV,999CWG", "3.1", (2509, 4544, -2035),
          "已停产，接单前确认"),
    intel(6, "PCIE", "E.M.W.0000067", "AX200.D2WG.LNV,985952", None, (916, 0, 916), "消耗完库存不接"),
    intel(7, "PCIE", "E.M.W.0000071", "AX200.NGWG.NV,985927", None, (678, 0, 678), "消耗完库存不接"),
    intel(8, "PCIE", "E.M.W.0000095", "AX210.NGWG.NV,999M85", "6.5", (0, 0, 0), "供应良好"),
    intel(9, "PCIE", "E.M.W.0000102", "AX210.D2WG.NV,999MA0", "6.5", (50, 0, 50), "供应良好"),
    intel(10, "PCIE", "E.M.W.0000196", "AX210.NGWG.NVX,999M86", "13.8", (100, 0, 100), "供应良好"),
    intel(11, "PCIE", "E.M.W.0000198", "BE200.D2WG.NV,99C475", "13", (6389, 0, 6389), "供应良好"),
]  # fmt: skip


def domestic(n: int, package: str, brand: str, erp: str | None, model: str, cny: str | None,
             usd: str | None, note: str = "大众市场"):  # fmt: skip
    prices = (
        [price(usd, "M", original_amount=cny, original_currency="CNY", fx_rate="6.7175")]
        if usd
        else []
    )
    return row(
        n,
        "wifi",
        f"WIFI5 1T1R {package} {brand} {model} RTL8821CE PCIE",
        name_en=f"Wi-Fi 5 1T1R {model} (RTL8821CE, PCIe)",
        brand=brand,
        erp_codes=[erp] if erp else [],
        mpn=model,
        attributes={
            "chipset": "RTL8821CE",
            "module_model": model,
            "interface": "PCIE",
            "package": package,
            "wifi_gen": "WIFI5",
            "streams": "1T1R",
        },
        prices=prices,
        no_price_reason=None if usd else "0",
        notes_raw=note,
    )


DOMESTIC_WIFI = [
    domestic(2, "插卡", "中龙通（cdtech）", "E.M.W.0000167", "CDW-C9821CE-00", "14.85",
             "1.95632198293323"),
    domestic(3, "插卡", "中龙通（cdtech）", "E.M.W.0000183", "CDW-C9821CE-00(NMS)", "14.85",
             "1.95632198293323"),
    domestic(4, "插卡", "妙明智能（MM）", None, "WD-RTL8821CE-M.2", "14", "1.84434395697409"),
    domestic(5, "插卡", "爱联科技（AI-Link）", None, "WF-R21C-EPA1G", None, None),
]  # fmt: skip


def ram(n: int, cap: str, speed: str, erp: str, mpn: str, amount: str, platform: str | None):
    return row(
        n,
        "ram_module",
        f"DDR4 {cap} {speed}MHZ 沃存 海力士颗粒",
        name_en=f"DDR4 {cap} {speed}MHz Wodposit (SK hynix chips)",
        brand="Wodposit",
        erp_codes=[erp],
        mpn=mpn,
        attributes={
            "type": "DDR4",
            "capacity_gb": cap,
            "speed_mhz": f"{speed}MHZ",
            "chip_vendor": "海力士",
        },
        prices=[price(amount, "H")],
        notes_raw="接单前确认",
        platform=platform,
    )


RAM_MODULES = [
    ram(3, "4GB", "2666", "E.M.R.0000029", "WPBH26D408SWA-4G", "10", "Intel/AMD"),
    ram(4, "8GB", "2666", "E.M.R.0000036", "WPBH26D408SWA-8G", "14.5", "Intel/AMD"),
    ram(5, "16GB", "2666", "E.M.R.0000025", "WPBH26D416SWA-16G", "26", "Intel/AMD"),
]


def board(n: int, model: str, erp: str | None, sku: str, ttl: str, when: str | None, fx: str):
    return row(
        n,
        "motherboard",
        f"{model} {sku}",
        name_en=f"{model} daughter board {sku}",
        erp_codes=[erp] if erp else [],
        attributes={"model": model, "sku": sku, "cost_ttl": ttl, "fx_rate": fx},
        prices=[price(ttl, "L", date=when)],
    )


DB_BOARDS = [
    board(3, "XN21S", "A.F.D.2400329-PVT", "A.F.D.2400329 RJ45 DB", "5.01212775165322",
          "2026-02-28", "6.837"),
    board(4, "DA1021C", "A.F.D.2500004-PVT", "A.F.D.2500004 RJ45 DB", "3.69630786087827",
          "2026-02-28", "6.837"),
    board(5, "XN21", "A.F.D.2300285", "A.F.D.2300285 RJ45 DB", "3.77191916523577",
          "2026-09-20", "6.7"),
    board(601, "XN35", "A.F.D.2600143", "A.F.D.2600143 DB小板", "2.58046778867958",
          "2026-04-16", "6.8216"),
    board(602, "XN35", None, "A.F.D.2600143 DB小板", "2.19324811537201", None, "6.75"),
    board(603, "XN35", None, "A.F.D.2600143 DB小板", "2.312579482137", None, "6.75"),
]  # fmt: skip

# ---------------------------------------------------------------- screenshots


def chip(n: int, group: str, cap: str, speed: str, amount: str, note: str, brand="Yemas"):
    balls = group.rsplit("-", 1)[1]
    return row(
        n,
        "dram_chip",
        f"{group} {cap} {brand} {speed}",
        name_en=f"{group.split('-')[0]} {cap} {speed} MT/s chip, {balls} balls ({brand})",
        brand=brand,
        attributes={"type": group.split("-")[0], "capacity_gb": cap, "speed_mhz": speed,
                    "package_balls": balls},
        prices=[price(amount, "9/28参考价", date="2026-09-28")],
        notes_raw=note,
    )  # fmt: skip


DRAM_CHIPS = [
    chip(1, "LPDDR5/5X-315", "4GB", "6400", "46.00", "可接单3.7K"),
    chip(2, "LPDDR5/5X-315", "8GB", "6400", "86.00", "库存可接12K"),
    chip(3, "LPDDR5/5X-315", "4GB", "8533", "52.00", "接单前确认", brand="yemas"),
    chip(4, "LPDDR5/5X-315", "8GB", "8533", "110.00", "接单前确认", brand="yemas"),
    chip(5, "LPDDR5/5X-315", "16GB", "8533", "210.00", "接单前确认", brand="yemas"),
    chip(6, "LPDDR5x-496", "8GB", "6400", "75.00", "可接单20K"),
]


def module(n: int, kind: str, cap: str, speed: str, brand: str, vendor: str, amount: str,
           form: str, note: str):  # fmt: skip
    return row(
        n,
        "ram_module",
        f"{kind} {cap} {speed}MHZ {brand} {vendor}颗粒 {form}",
        name_en=f"{kind} {cap} {speed}MHz module ({vendor} chips, {form})",
        brand=brand,
        attributes={"type": kind, "capacity_gb": cap, "speed_mhz": f"{speed}MHZ",
                    "form_factor": form, "chip_vendor": vendor},
        prices=[price(amount, "9/28参考价", date="2026-09-28")],
        notes_raw=note,
        platform="X86",
    )  # fmt: skip


RAM_SCREENSHOT = [
    module(1, "DDR4", "8GB", "2666", "昱联", "镁光", "42.00", "SO DIMM", "可接13K,预付30%，尾款到发货"),
    module(2, "DDR4", "8GB", "2666", "金速", "海力士", "48.00", "SO/U DIMM", "预付30%，尾款开支票30天"),
    module(3, "DDR4", "16GB", "2666", "昱联", "海力士", "83.00", "SO/U DIMM", "预付30%，尾款到发货"),
    module(4, "DDR4", "8GB", "3200", "威刚", "镁光", "65.00", "SO/U DIMM", "接单前确认"),
    module(5, "DDR4", "16GB", "3200", "威刚", "镁光", "130.00", "SO/U DIMM", "接单前确认"),
    module(6, "DDR5", "8GB", "5600", "威刚", "镁光", "125.00", "SO DIMM", "接单前确认"),
    module(7, "DDR5", "8GB", "5600", "沃存", "镁光", "113.00", "SO DIMM", "接单前确认"),
    module(8, "DDR5", "16GB", "5600", "沃存", "镁光", "215.00", "SO/U DIMM", "接单前确认"),
    module(9, "DDR5", "16GB", "5600", "威刚", "长鑫", "245.00", "SO/U DIMM", "接单前确认"),
]  # fmt: skip


def ssd(n: int, cap: str, iface: str, brand: str, solution: str, amount: str | None, note: str,
        nand: str, **kw: Any):  # fmt: skip
    return row(
        n,
        "ssd",
        f"{cap} 2280 {iface} {brand} {solution}",
        name_en=f"SSD {cap} M.2 2280 {iface} {nand}",
        brand=brand,
        attributes={"capacity_gb": cap, "form_factor": "2280", "interface": iface,
                    "nand_type": nand, "solution_text": solution},
        prices=[price(amount, "9/28参考价", date="2026-09-28")] if amount else [],
        no_price_reason=None if amount else "/",
        notes_raw=note,
        **kw,
    )  # fmt: skip


SSD_NOTE = "表格上方注：ink方案不良率1%左右，不良一对一换货，有需求务必提前沟通确认"
SSD_SCREENSHOT = [
    ssd(1, "128G", "SATA", "江波龙（Airdisk）", "足容 固带 TLC", None, "库存可接1629pcs", "TLC",
        issues=[SSD_NOTE]),
    ssd(2, "256G", "SATA", "至誉（EXASCEND）", "足容 固带 TLC", None, "库存可接2293pcs", "TLC"),
    ssd(3, "128G", "PCIE3.0", "登高者（DGZ）", "足容 INK V7 TLC", "22.00", "接单前确认", "TLC"),
    ssd(9, "512G", "PCIE3.0", "泽石(ZETTASTONE)", "足容；固带 联芸1202+武当山TLC", "86.00",
        "可接单50K", "TLC"),
    ssd(14, "2T", "PCIE4.0", "凯威(keyway)", "足容 固带 联芸1602+n58. QLC", "240.00", "新料需验证",
        "QLC"),
    ssd(17, "4T", "PCIE4.0", "威刚(ADATA)", "足容；固带 镁光颗粒 QLC", "700.00", "接单前确认",
        "QLC"),
]  # fmt: skip


def cpu(n: int, family: str, erp: str | None, model: str, sspec: str | None, tdp: str,
        process: str | None, standard: str | None, forecast: str | None, stock: tuple,
        note: str):  # fmt: skip
    prices = []
    if standard:
        prices.append(price(standard, "10月不报数参考价格", date="2026-10-01"))
    if forecast:
        prices.append(price(forecast, "10月报数参考价格", tier="forecast", date="2026-10-01"))
    attributes = {"model": model, "platform_family": family, "tdp_w": tdp, "core_class": "大核"}
    if sspec:
        attributes["sspec"] = sspec
    if process:
        attributes["process_nm"] = process
    return row(
        n,
        "cpu",
        f"{model} {sspec}" if sspec else model,
        name_en=f"Intel {model}",
        brand="Intel",
        erp_codes=[erp] if erp else [],
        attributes=attributes,
        prices=prices,
        no_price_reason=None if prices else "-",
        stock_qty=stock[0],
        demand_qty=stock[1],
        stock_after_qty=stock[2],
        notes_raw=note,
    )


CPU_SCREENSHOT = [
    cpu(1, "Raptor Lake-P", "E.I.P.0000455", "i5-1340P", "SRMJ7", "28W", "10nm", "154", "154",
        (0, 0, 0), "Q4供应良好"),
    cpu(3, "Raptor Lake-U", "E.I.P.0000451", "i3-1315U", "SRMLV", "15W", "10nm", None, None,
        (58, 15685, -15627), "交期需确认"),
    cpu(12, "Raptor Lake-H", "E.I.P.0000565", "i9-13900H", "SRMJ4", "45W", "10nm", "286", "286",
        (0, 0, 0), "已发停产通知，交期需确认"),
    cpu(35, "Meteor Lake-U", "E.I.P.0000609", "Ultra 5-115U", "SRN6F", "15W", "7nm", "118", None,
        (8201, 40, 8161), "Q4供应良好"),
    cpu(36, "Meteor Lake-U", "E.I.P.0000560", "Ultra 5 125U", "SRN6E", "15W", "7nm", "130",
        "156.5", (524, 20847, -20323), "Q4供应良好"),
    cpu(56, "Arrow Lake-HX Refresh", None, "Ultra 9 290HX", None, "55W", "3nm", "330", "330",
        (0, 0, 0), "Q4供应良好"),
]  # fmt: skip


# ------------------------------------------------------------------- PDF


def offer_line(n: int, category: str, model: str, name: str, description: str, amount: str,
               **attributes: str):  # fmt: skip
    return row(
        n,
        category,
        name,
        name_en=name,
        attributes={"model": model, "description": description, **attributes},
        prices=[price(amount, "E", date="2026-08-11")],
    )


UPS_PDF = [
    offer_line(11, "ups", "SP10KS", "SP10KS 10KVA/5400W online UPS",
               "High-frequency on-line UPS, power 10KVA/5400W, input/output: 220VAC, frequency: "
               "50/60Hz, battery voltage:192VDC, machine size: 425×190×340mm, weight:14KG",
               "490", power_va="10KVA", power_w="5400W", weight_kg="14KG"),
    offer_line(15, "battery", "12V24AH", "12V24AH battery",
               "Maintenance-free valve-regulated lead-acid battery 12V24AH", "34",
               capacity_ah="24AH"),
    offer_line(19, "cabinet", "C6", "Battery cabinet C6",
               "Customized battery cabinetC6, fireproof material, can accommodate 16*12V24AH "
               "standard battery cabinets,Size：595*470*620mm,Includes cables and circuit breaker",
               "49", size_mm="595*470*620"),
    offer_line(28, "ups", "SP20KS", "SP20KS 20KVA/18000W online UPS",
               "High-frequency on-line UPS, power 20KVA/18000W, input/output: 220VAC, frequency: "
               "50/60Hz, battery voltage: 192VDC, machine size: 560*250*580mm, weight: 38KG",
               "943", power_va="20KVA", power_w="18000W", weight_kg="38KG"),
    offer_line(32, "battery", "12V38AH", "12V38AH battery",
               "UPS special valve-controlled Maintenance-free lead-acid battery 12V38AH * 16", "50",
               capacity_ah="38AH"),
    offer_line(35, "cabinet", "C8", "Battery cabinet C8",
               "Customized battery cabinetC8, fireproof material, can accommodate 16*12V38AH "
               "standard battery cabinets,Size：780*470*620mm", "59", size_mm="780*470*620"),
]  # fmt: skip

MEDIA_RECORDED: dict[str, list[dict[str, Any]]] = {
    "img_dram_chips.jpg": DRAM_CHIPS,
    "img_ram_modules.jpg": RAM_SCREENSHOT,
    "img_ssd.jpg": SSD_SCREENSHOT,
    "img_cpu.jpg": CPU_SCREENSHOT,
    "Page 1": UPS_PDF,
}

RECORDED: dict[str, list[dict[str, Any]]] = {
    **MEDIA_RECORDED,
    "Intel wifi": INTEL_WIFI,
    "domestic  WIFI": DOMESTIC_WIFI,
    "内存条 参考价": RAM_MODULES,
    "DB小板汇总": DB_BOARDS,
}

SHEET_META: dict[str, dict[str, Any]] = {
    "Intel wifi": {"currency": "USD", "fx_rate": None, "price_date": None},
    "domestic  WIFI": {"currency": "USD", "fx_rate": Decimal("6.7175"), "price_date": None},
    "内存条 参考价": {"currency": "USD", "fx_rate": None, "price_date": None},
    "DB小板汇总": {"currency": "USD", "fx_rate": Decimal("6.71"), "price_date": None},
    "Page 1": {"currency": "USD", "fx_rate": None, "price_date": "2026-08-11"},
}


class FakeExtractor:
    """Replays RECORDED rows whose source_row appears in the chunk's grid."""

    model = "fake-model"

    def __init__(
        self,
        recorded: dict[str, list[dict[str, Any]]] | None = None,
        max_rows: int | None = None,
        fail_sheets: set[str] | None = None,
    ) -> None:
        self.recorded = copy.deepcopy(recorded if recorded is not None else RECORDED)
        self.max_rows = max_rows
        self.fail_sheets = fail_sheets or set()
        self.calls: list[ChunkContext] = []

    async def extract(self, context: ChunkContext) -> ChunkResult:
        from app.services.importer.llm_parser import ExtractionError

        self.calls.append(context)
        if context.sheet in self.fail_sheets:
            raise ExtractionError("simulated failure")
        recorded = self.recorded.get(context.sheet, [])
        if context.kind == "sheet":
            numbers = {int(n) for n in re.findall(r"^\| (\d+) \|", context.body, re.M)}
            if self.max_rows is not None and len(numbers) > self.max_rows:
                raise OutputTooLong("too many rows for the fake")
            rows = [r for r in recorded if r["source_row"] in numbers]
        else:  # a whole screenshot or page
            rows = list(recorded)
        return ChunkResult(
            rows=copy.deepcopy(rows),
            sheet_meta=SHEET_META.get(context.sheet, {}),
            input_tokens=1000,
            output_tokens=100 * len(rows),
            model=self.model,
        )
