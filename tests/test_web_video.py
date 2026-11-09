import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai import video, webpage
from local_ai.cli import dispatch, parser
from local_ai.document_mcp import handle


def decoded(result):
    meta, _, text = result["content"][0]["text"].partition("\n")
    return json.loads(meta), text


class Pages(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in {"/redirect", "/badredirect"}:
            self.send_response(302)
            self.send_header(
                "Location", "/page" if self.path == "/redirect" else "file:///etc/passwd"
            )
            self.end_headers()
            return
        data = b'<title>Guide</title><nav>Ignore</nav><main><p>GPU &amp; CPU</p><script>secret()</script><a href="/next">Next</a></main>'
        mime = "text/html; charset=utf-8"
        if self.path == "/long":
            data = b"<main>" + b"A" * 41000 + b"</main>"
        elif self.path == "/empty":
            data = b"<script>load()</script>"
        elif self.path == "/binary":
            mime = "application/pdf"
        elif self.path == "/large":
            data = b"x" * 100
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data) + (5 if self.path == "/partial" else 0)))
        self.end_headers()
        self.wfile.write(data)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Pages)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_html_redirect_source_and_links(self):
        meta, text = decoded(webpage.read_webpage(self.base + "/redirect"))
        self.assertEqual(meta["title"], "Guide")
        self.assertEqual(meta["final_url"], self.base + "/page")
        self.assertIn("GPU & CPU", text)
        self.assertNotIn("Ignore", text)
        self.assertNotIn("secret", text)
        self.assertEqual(meta["links"], [self.base + "/next"])

    def test_continuation(self):
        meta, text = decoded(webpage.read_webpage(self.base + "/long"))
        self.assertEqual(len(text), 40000)
        self.assertEqual(meta["next_offset"], 40000)
        meta, text = decoded(webpage.read_webpage(self.base + "/long", offset=40000))
        self.assertEqual(len(text), 1000)
        self.assertIsNone(meta["next_offset"])

    def test_rejected_inputs_and_download_failures(self):
        for url in ["file:///etc/passwd", "http://user:password@example.com", "ftp://example.com"]:
            with self.assertRaises(ValueError):
                webpage.read_webpage(url)
        for route in ["/badredirect", "/binary", "/empty", "/partial"]:
            with self.subTest(route=route), self.assertRaises(ValueError):
                webpage.read_webpage(self.base + route)
        with patch.object(webpage, "MAX_BYTES", 10), self.assertRaises(ValueError):
            webpage.read_webpage(self.base + "/large")

    def test_cli_and_mcp(self):
        result = dispatch(parser().parse_args(["document", "web", self.base + "/page"]))
        self.assertIn("GPU", decoded(result)[1])
        result = handle(
            {
                "method": "tools/call",
                "params": {"name": "read_webpage", "arguments": {"url": "file:///etc/passwd"}},
            }
        )
        self.assertTrue(result["isError"])


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "clip.mp4"
        self.path.write_bytes(b"fixture")

    def test_sidecar_without_ffmpeg_and_continuation(self):
        self.path.with_suffix(".vtt").write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n" + "A" * 41000
        )
        with patch.object(video, "run", side_effect=AssertionError("must not execute")):
            first, text = decoded(video.read_video(self.path))
            second, rest = decoded(video.read_video(self.path, offset=first["next_offset"]))
        self.assertIn("00:00:01.000", text)
        self.assertTrue(rest)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(first["subtitle_source"], str(self.path.with_suffix(".vtt")))

    def test_invalid_parameters_and_missing_optional_tools(self):
        for args in [
            {"start": float("nan")},
            {"count": True},
            {"count": 6},
            {"mode": "frames", "interval": 0},
            {"start": 5},
            {"offset": -1},
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                video.read_video(self.path, **args)
        with patch("local_ai.video.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "optional client package"):
                video.read_video(self.path, mode="frames", count=1)
        result = handle(
            {
                "method": "tools/call",
                "params": {
                    "name": "read_video",
                    "arguments": {"path": "https://example.com/a.mp4"},
                },
            }
        )
        self.assertTrue(result["isError"])

    def test_tools_and_cli(self):
        tools = handle({"method": "tools/list"})["tools"]
        self.assertEqual(
            [t["name"] for t in tools], ["read_document", "read_webpage", "read_video"]
        )
        opts = parser().parse_args(
            [
                "document",
                "video",
                str(self.path),
                "--mode",
                "frames",
                "--start",
                "1.5",
                "--count",
                "2",
                "--interval",
                "0.5",
            ]
        )
        self.assertEqual(opts.start, 1.5)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "optional FFmpeg")
    def test_real_frames_metadata_and_embedded_subtitles(self):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x120:r=2",
                "-t",
                "2",
                "-c:v",
                "mpeg4",
                "-threads",
                "1",
                str(self.path),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        info, _ = decoded(video.read_video(self.path, mode="info"))
        self.assertAlmostEqual(float(info["media"]["format"]["duration"]), 2, places=1)
        result = video.read_video(self.path, mode="frames", start=0, count=2, interval=0.5)
        meta, _ = decoded(result)
        self.assertEqual(meta["returned_frames"], 2)
        self.assertEqual(meta["requested_timestamps_seconds"], [0, 0.5])
        self.assertEqual(sum(c["type"] == "image" for c in result["content"]), 2)
        subs = self.path.with_suffix(".srt")
        subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nGPU ready\n")
        target = self.path.parent / "embedded.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(self.path),
                "-i",
                str(subs),
                "-c:v",
                "copy",
                "-c:s",
                "mov_text",
                str(target),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )
        meta, text = decoded(video.read_video(target))
        self.assertIn("GPU ready", text)
        self.assertEqual(meta["subtitle_source"], "first embedded subtitle stream")

    def test_partial_frame_count_and_actual_failure(self):
        def fake(command, deadline):
            self.assertIn("file,pipe", command)
            self.assertIn("-nostdin", command)
            if command[-1].endswith("frame-0.jpg"):
                Path(command[-1]).write_bytes(b"\xff\xd8\xfffixture")
            return b""

        with patch.object(video, "run", side_effect=fake):
            result = video.read_video(self.path, mode="frames", count=3, start=1)
        meta, _ = decoded(result)
        self.assertEqual(meta["returned_frames"], 1)
        self.assertEqual(meta["requested_count"], 3)
        self.assertTrue(any("Fewer" in warning for warning in meta["warnings"]))
        with patch.object(video, "run", side_effect=ValueError("decoder failed")):
            result = handle(
                {
                    "method": "tools/call",
                    "params": {
                        "name": "read_video",
                        "arguments": {"path": str(self.path), "mode": "frames"},
                    },
                }
            )
        self.assertTrue(result["isError"])
        self.assertIn("decoder failed", result["content"][0]["text"])

    def test_doctor_detects_broken_shared_libraries(self):
        from local_ai.documents import dependencies

        failed = subprocess.CompletedProcess([], 127, b"", b"liblapack.so.3: not found")
        with (
            patch("local_ai.documents.shutil.which", return_value="/bin/tool"),
            patch("local_ai.documents.subprocess.run", return_value=failed),
        ):
            result = dependencies()
        self.assertFalse(result["video_frames_ready"])
        self.assertFalse(result["video_info_ready"])
        self.assertTrue(result["video_sidecar_ready"])
        self.assertIn("liblapack", result["video_tool_errors"]["ffmpeg"])

    def test_offline_discovery_and_local_reads(self):
        with patch("local_ai.webpage.open_page", side_effect=OSError("Network unreachable")):
            self.assertIn("tools", handle({"method": "initialize"})["capabilities"])
            self.assertEqual(len(handle({"method": "tools/list"})["tools"]), 3)
            result = handle(
                {
                    "method": "tools/call",
                    "params": {"name": "read_webpage", "arguments": {"url": "https://example.com"}},
                }
            )
            self.assertTrue(result["isError"])
            path = self.path.with_suffix(".txt")
            path.write_text("local content still available")
            result = handle(
                {
                    "method": "tools/call",
                    "params": {"name": "read_document", "arguments": {"path": str(path)}},
                }
            )
            self.assertFalse(result["isError"])
            self.assertIn("local content still available", result["content"][0]["text"])
