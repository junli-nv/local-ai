# v2.1.3 Completion deduplication and BCM PDF manuals

Once complete task output has reached the assistant, completion produces only a toast, without inserting a message or waking the model to repeat that results were read or no instruction remains. Unread output still triggers automatic inspection and continuation. Contiguous read cursors persist with tasks. Older records are checked against actual tool outputs in the latest 100 native messages; uncertain cases retain automatic processing.

The BCM template prioritizes manuals in `/cm/shared/docs`, with version, component and PDF page citations, and locates nodeinstaller at `/cm/node-installer`. Installation/boot troubleshooting may inspect the associated image under `/cm/images`; ordinary discovery still excludes the complete image tree and never scans all images.

PDF reading prefers Poppler and can use optional pypdf in a separate environment when the text converter is absent. `document setup-pdf` prepares a private user venv; `--wheel-dir DIR` installs local wheels offline without changing system Python. Without a renderer, auto returns text with a clear warning. pypdf performs no OCR; scans and charts still require rendering and an image-capable model.

After updating the BCM program, exit/resume chat; no model-service restart is needed. Reapply the BCM template as the actual chat user:

```bash
./local-ai install --role client --instructions bcm
```

If no PDF text backend is available, the assistant can run `./local-ai document setup-pdf` and retry. Offline targets need prepared wheels. Private document-tool environments are excluded from public exports and history migration. Existing tags are preserved.

[Execution and notices](execution.md) · [PDF fallback](documents.md#v213-optional-pdf-text-backend) · [Validation](validation.md) · [中文](../release-2.1.3.md)
