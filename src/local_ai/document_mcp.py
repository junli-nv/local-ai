"""Small stdio MCP bridge; document content never becomes executable code."""

import json
import sys

from .documents import read_document
from .video import read_video
from .webpage import read_webpage

TOOL = {
    "name": "read_document",
    "description": "Read local PDF, images, Word, Excel, PowerPoint, OpenDocument or text. "
    "PDF auto returns extracted text AND page images (including scans). "
    "Office auto returns text/cells/formulas/notes; render shows layout/charts through LibreOffice. "
    "Use start/count to select pages, sheets or slides; offset continues long text. "
    "Never use raw PDF attachments with a Chat Completions endpoint. Paths are on this client host.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "mode": {"type": "string", "enum": ["auto", "text", "render"], "default": "auto"},
            "start": {"type": "integer", "minimum": 1, "default": 1},
            "count": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
}


def media_tool(name, description, properties, required, network=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": network,
        },
    }


TOOLS = [
    TOOL,
    media_tool(
        "read_webpage",
        "Fetch HTTP(S) page text on the client. No JavaScript, login or browser. "
        "Returns title, source URL, links and next_offset; continue long text using offset.",
        {"url": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
        ["url"],
        network=True,
    ),
    media_tool(
        "read_video",
        "Read a LOCAL video: subtitles (default) uses same-name UTF-8 SRT/VTT, "
        "or first embedded subtitle track with optional FFmpeg. info needs ffprobe. "
        "frames needs FFmpeg and an image-capable model. start/interval are SECONDS; "
        "count limits sampled frames, not full-video coverage. No ASR or video URLs.",
        {
            "path": {"type": "string"},
            "mode": {"type": "string", "enum": ["info", "subtitles", "frames"]},
            "start": {"type": "number", "minimum": 0},
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
            "interval": {"type": "number", "exclusiveMinimum": 0},
            "offset": {"type": "integer", "minimum": 0},
        },
        ["path"],
    ),
]
FUNCTIONS = {"read_document": read_document, "read_webpage": read_webpage, "read_video": read_video}


def handle(request):
    method = request.get("method")
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "local-ai-documents", "version": "1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = request.get("params", {})
        tool = next((item for item in TOOLS if item["name"] == params.get("name")), None)
        if tool is None:
            raise ValueError("Unknown document tool")
        args = params.get("arguments", {})
        if not isinstance(args, dict) or any(
            not isinstance(args.get(key), str) for key in tool["inputSchema"]["required"]
        ):
            raise ValueError("A string path or URL is required")
        if set(args) - set(tool["inputSchema"]["properties"]):
            raise ValueError("Unknown document argument")
        try:
            return FUNCTIONS[tool["name"]](**args)
        except Exception as error:
            # Errors remain visible to the caller; no guessed/partial success.
            return {
                "isError": True,
                "content": [{"type": "text", "text": type(error).__name__ + ": " + str(error)}],
            }
    raise ValueError("Unknown method: " + str(method))


def main():
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if "id" not in request:
                continue
            response = {"jsonrpc": "2.0", "id": request["id"], "result": handle(request)}
        except Exception as error:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32602, "message": str(error)},
            }
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
