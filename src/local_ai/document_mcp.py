"""Small stdio MCP bridge; document content never becomes executable code."""

import json
import sys

from .documents import read_document

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
        return {"tools": [TOOL]}
    if method == "tools/call":
        params = request.get("params", {})
        if params.get("name") != TOOL["name"]:
            raise ValueError("Unknown document tool")
        args = params.get("arguments", {})
        if not isinstance(args, dict) or not isinstance(args.get("path"), str):
            raise ValueError("A string path is required")
        if set(args) - set(TOOL["inputSchema"]["properties"]):
            raise ValueError("Unknown document argument")
        try:
            return read_document(**args)
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
