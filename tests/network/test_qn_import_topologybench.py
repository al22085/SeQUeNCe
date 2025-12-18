import csv
import subprocess
import tempfile
import zipfile
from pathlib import Path


def _build_minimal_xlsx(path: Path):
    shared_strings = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="6" uniqueCount="6">
<si><t>source</t></si><si><t>destination</t></si><si><t>linkLengthInKm</t></si>
<si><t>A</t></si><si><t>B</t></si><si><t>C</t></si>
</sst>"""
    sheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
 <row r="1">
  <c t="s"><v>0</v></c><c t="s"><v>1</v></c><c t="s"><v>2</v></c>
 </row>
 <row r="2">
  <c t="s"><v>3</v></c><c t="s"><v>4</v></c><c><v>10</v></c>
 </row>
 <row r="3">
  <c t="s"><v>4</v></c><c t="s"><v>5</v></c><c><v>20</v></c>
 </row>
</sheetData>
</worksheet>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        zf.writestr("xl/sharedStrings.xml", shared_strings)


def test_import_topologybench_mini():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        xlsx = tmp / "mini.xlsx"
        _build_minimal_xlsx(xlsx)
        out_csv = tmp / "dist.csv"
        out_md = tmp / "dist.md"
        cmd = [
            "python",
            "scripts/qn_import_nsfnet_distances_from_topologybench.py",
            "--xlsx",
            str(xlsx),
            "--out-csv",
            str(out_csv),
            "--out-md",
            str(out_md),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        assert out_csv.exists()
        with out_csv.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
            assert rows[0]["u"] and float(rows[0]["distance_km"])
        assert out_md.exists()
