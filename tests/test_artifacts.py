import tempfile
import unittest
import zipfile
from pathlib import Path

from linza_mcp.artifacts import extract_docx_text, extract_xlsx_text


def write_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


class ArtifactExtractorTests(unittest.TestCase):
    def test_docx_and_xlsx_extract_text_with_safe_xml_parser(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            docx = tmp / "sample.docx"
            write_zip(docx, {
                "word/document.xml": (
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body><w:p><w:r><w:t>Hello LINZA</w:t></w:r></w:p></w:body>"
                    "</w:document>"
                ),
            })
            docx_text, docx_meta = extract_docx_text(docx)
            self.assertEqual(docx_text, "Hello LINZA")
            self.assertEqual(docx_meta["extractor"], "docx-xml")

            xlsx = tmp / "sample.xlsx"
            write_zip(xlsx, {
                "xl/sharedStrings.xml": (
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<si><t>Alpha</t></si><si><t>Beta</t></si></sst>"
                ),
                "xl/workbook.xml": (
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
                ),
                "xl/_rels/workbook.xml.rels": (
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
                ),
                "xl/worksheets/sheet1.xml": (
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row></sheetData>'
                    "</worksheet>"
                ),
            })
            xlsx_text, xlsx_meta = extract_xlsx_text(xlsx)
            self.assertIn("# Sheet: Data", xlsx_text)
            self.assertIn("Alpha\tBeta", xlsx_text)
            self.assertEqual(xlsx_meta["extractor"], "xlsx-xml")

    def test_office_extractors_reject_unsafe_xml_entities(self):
        unsafe_xml = """<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY unsafe "expanded">]>
<root><p><t>&unsafe;</t></p></root>
"""
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            docx = tmp / "unsafe.docx"
            write_zip(docx, {"word/document.xml": unsafe_xml})
            with self.assertRaisesRegex(ValueError, "unsafe constructs"):
                extract_docx_text(docx)

            xlsx = tmp / "unsafe.xlsx"
            write_zip(xlsx, {"xl/sharedStrings.xml": unsafe_xml})
            with self.assertRaisesRegex(ValueError, "unsafe constructs"):
                extract_xlsx_text(xlsx)


if __name__ == "__main__":
    unittest.main()
