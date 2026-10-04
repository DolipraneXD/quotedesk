# PyInstaller one-folder build of QuoteDesk (plan §9). Build from the repository root with
#   scripts/build-desktop.sh      (or scripts\build-desktop.bat on Windows)
# after `npm run build` in frontend/. The result is dist/QuoteDesk/: copy the whole folder.
# The data folder (database, photos, backups, API keys) is created next to the executable.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"
if not (DIST / "index.html").exists():
    raise SystemExit("frontend/dist is missing: run `npm run build` in frontend/ first")

datas = [
    (str(DIST), "frontend/dist"),
    (str(BACKEND / "alembic.ini"), "backend"),
    (str(BACKEND / "alembic"), "backend/alembic"),  # migration scripts are read as files
    (str(BACKEND / "app" / "assets"), "app/assets"),  # Noto Sans SC for the PDFs
]
for package in ("fpdf", "pdfplumber", "pypdfium2", "pypdfium2_raw", "certifi"):
    datas += collect_data_files(package)

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("alembic")
    + ["sqlalchemy.dialects.sqlite"]
)

a = Analysis(
    [str(BACKEND / "packaging" / "quotedesk.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QuoteDesk",
    console=True,  # the window shows the address and closing it stops the app
)
coll = COLLECT(exe, a.binaries, a.datas, name="QuoteDesk")
