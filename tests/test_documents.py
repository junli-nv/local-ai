import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from local_ai import documents
from local_ai.cli import parser
from local_ai.document_mcp import handle


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def package(self, name, files):
        p = self.root / name
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            for key, value in files.items():
                z.writestr(key, value)
        return p

    def text(self, result):
        return result["content"][0]["text"]

    def test_word_paragraphs_table_and_header_preserve_text(self):
        path = self.package(
            "a.docx",
            {
                "word/document.xml": "<document><body><p><t>你好</t></p><tbl><tr><tc><p><t>GPU-A</t></p></tc><tc><p><t>4</t></p></tc></tr></tbl></body></document>",
                "word/header1.xml": "<header><p><t>Header</t></p></header>",
            },
        )
        text = self.text(documents.read_document(path))
        for expected in ["你好", "GPU-A", "Header", "Document body"]:
            self.assertIn(expected, text)

    def test_excel_sheet_order_cell_addresses_formulas_and_cached_values(self):
        path = self.package(
            "a.xlsx",
            {
                "xl/workbook.xml": '<workbook xmlns:r="urn:r"><sheets><sheet name="Second" r:id="r2" state="hidden"/><sheet name="First" r:id="r1"/></sheets></workbook>',
                "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="/xl/worksheets/sheet2.xml"/></Relationships>',
                "xl/sharedStrings.xml": "<sst><si><t>节点</t></si></sst>",
                "xl/worksheets/sheet1.xml": '<worksheet><row><c r="A1" t="s"><v>0</v></c></row></worksheet>',
                "xl/worksheets/sheet2.xml": '<worksheet><row><c r="B7"><f>SUM(B1:B6)</f><v>42</v></c></row></worksheet>',
            },
        )
        text = self.text(documents.read_document(path, count=1))
        self.assertIn("Second", text)
        self.assertIn("hidden", text)
        self.assertIn("B7", text)
        self.assertIn("=SUM(B1:B6) [cached value: 42]", text)
        self.assertNotIn("节点", text)
        self.assertIn("节点", self.text(documents.read_document(path, start=2)))
        self.assertIn("may be stale", text)

    def test_presentation_relationship_order_and_matching_notes(self):
        path = self.package(
            "a.pptx",
            {
                "ppt/presentation.xml": '<presentation xmlns:r="urn:r"><sldIdLst><sldId id="256" r:id="r2"/><sldId id="257" r:id="r1"/></sldIdLst></presentation>',
                "ppt/_rels/presentation.xml.rels": '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>',
                "ppt/slides/slide1.xml": "<slide><t>Last</t></slide>",
                "ppt/slides/slide2.xml": "<slide><t>First</t></slide>",
                "ppt/slides/_rels/slide2.xml.rels": '<Relationships><Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide9.xml"/></Relationships>',
                "ppt/notesSlides/notesSlide9.xml": "<notes><t>Correct note</t></notes>",
            },
        )
        text = self.text(documents.read_document(path, count=1))
        self.assertIn("First", text)
        self.assertIn("Correct note", text)
        self.assertNotIn("Last", text)

    def test_long_text_has_explicit_continuation(self):
        path = self.root / "long.txt"
        path.write_text("Z" * 41000)
        one = documents.read_document(path)
        meta = json.loads(self.text(one).split("\n", 1)[0])
        self.assertEqual(meta["next_offset"], 40000)
        two = documents.read_document(path, offset=40000)
        self.assertIsNone(json.loads(self.text(two).split("\n", 1)[0])["next_offset"])

    def test_entities_rejected(self):
        path = self.package(
            "bad.docx",
            {"word/document.xml": '<!DOCTYPE x [<!ENTITY x "secret">]><document>&x;</document>'},
        )
        with self.assertRaisesRegex(ValueError, "entities"):
            documents.read_document(path)

    def test_large_expansion_rejected(self):
        path = self.package("bad.docx", {"word/document.xml": "<d/>" * 20})
        with patch.object(documents, "MAX_ARCHIVE", 10):
            with self.assertRaisesRegex(ValueError, "Expanded"):
                documents.read_document(path)

    def test_bad_ranges_and_unsupported_binary(self):
        path = self.root / "a.txt"
        path.write_text("abc")
        for args in [{"start": 0}, {"count": 6}, {"count": True}, {"offset": -1}]:
            with self.assertRaises(ValueError):
                documents.read_document(path, **args)
        path.write_bytes(b"a\0b")
        with self.assertRaisesRegex(ValueError, "Binary"):
            documents.read_document(path)

    def test_missing_converter_is_actionable(self):
        with patch("local_ai.documents.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "document doctor"):
                documents.run_tool(["pdftotext", "a.pdf"])

    def test_pdf_calls_selected_pages_and_keeps_images(self):
        path = self.root / "a.pdf"
        path.write_bytes(b"%PDF-1.4")

        def fake(cmd):
            if cmd[0] == "pdftotext":
                Path(cmd[-1]).write_text("page two\fpage three\f")
            else:
                Path(cmd[-1] + "-2.png").write_bytes(b"\x89PNG\r\n\x1a\nplaceholder")

        with patch("local_ai.documents.run_tool", side_effect=fake) as run:
            result = documents.read_document(path, start=2, count=2)
        self.assertIn("Page 2", self.text(result))
        self.assertEqual(result["content"][-1]["type"], "image")
        self.assertIn("-f", run.call_args_list[0].args[0])
        self.assertIn("2", run.call_args_list[0].args[0])

    def test_mcp_errors_are_reported_and_protocol_negotiates(self):
        self.assertIn("tools", handle({"method": "initialize"})["capabilities"])
        self.assertEqual(handle({"method": "tools/list"})["tools"][0]["name"], "read_document")
        result = handle(
            {
                "method": "tools/call",
                "params": {
                    "name": "read_document",
                    "arguments": {"path": str(self.root / "missing.pdf")},
                },
            }
        )
        self.assertTrue(result["isError"])
        self.assertIn("Not a regular file", self.text(result))

    def test_document_cli_selection(self):
        opts = parser().parse_args(["document", "read", "a.pdf", "--start", "2", "--count", "1"])
        self.assertEqual((opts.start, opts.count), (2, 1))
