---
name: Obsidian-CanvasToHtml
description: Export an Obsidian .canvas file into a portable, self-contained HTML bundle with an adjacent attachments/ folder. Mirrors the canvas layout (groups, text/file/link nodes, edges) as a pan/zoom web page and copies every referenced note/image/attachment. Use when the user says "canvas导出html", "canvas to html", "导出canvas", "export canvas", "canvas转网页", or asks to share/archive an Obsidian canvas.
metadata:
  version: 1.0.0
---

# Obsidian Canvas → HTML Exporter

Convert an Obsidian **`.canvas`** file (the JSON produced by the Canvas core
plugin) into a single **portable HTML page** plus an **`attachments/`** folder.
The export visually reproduces the canvas: groups as dashed containers, text
cards rendered as Obsidian-flavour markdown, file cards with their `.md`
content or embedded image, and edges drawn as labelled curves. The bundle is
fully self-contained — drop it on a USB stick, email it, host it statically,
or open the HTML directly from disk.

## When to trigger

- Explicit: user invokes `/Obsidian-CanvasToHtml` or types any of
  `canvas导出html`, `canvas转html`, `导出canvas`, `canvas to html`,
  `export canvas`, `canvas转网页`.
- Implicit: user pastes a `.canvas` path and asks to convert / share / archive
  / view it outside Obsidian.

## What it produces

```
<output-dir>/
├── <canvas-name>.html        ← open this in a browser
└── attachments/
    ├── note1.md              ← copied from vault
    ├── note2.md
    ├── figure1.png           ← embedded inline
    ├── figure2.png
    └── ...
```

- The HTML file is the entry point. It references `attachments/...` via
  relative URLs only — no absolute paths, so the whole folder is portable.
- Images referenced by canvas file nodes render **inline** (`<img>`).
- Markdown notes referenced by canvas file nodes are **rendered** (tables,
  code blocks, wikilinks, `![[embed]]`) and the `.md` is also copied into
  `attachments/` for the curious reader.
- Missing files (vault path broken, file deleted) are shown as a labelled
  placeholder rather than crashing the export.

## How to run

The converter is a plain Python script with no network access. **Always run it
inside the `webgis-ocean` conda env** so the markdown libraries are available.

```bash
conda run -n webgis-ocean python "C:/Users/henu_3090/.zcode/skills/Obsidian-CanvasToHtml/scripts/canvas_to_html.py" \
    "<input.canvas>" \
    --output-dir "<output-dir>"
```

Required Python deps (already in `webgis-ocean`): `markdown`,
`pymdown-extensions`, `Pygments`. If a run reports a missing module, install
with `conda run -n webgis-ocean pip install markdown pymdown-extensions`.

### CLI flags

| flag | purpose |
|------|---------|
| `<canvas>` (positional) | Path to the `.canvas` file. Required. |
| `--vault-root DIR` | Obsidian vault root. Auto-detected via `.obsidian/` if omitted. |
| `--output-dir DIR` | Output directory. Defaults to `<canvas-stem>_html/` next to the canvas. |
| `--title TEXT` | HTML `<title>` and topbar heading. Defaults to canvas filename stem. |
| `--open` | Open the result in the default browser when done. |

## Workflow (for the agent)

1. **Locate the canvas.** Confirm the `.canvas` path the user gave actually
   exists. If the user only gave a folder, look for the single `.canvas`
   inside it.
2. **Resolve the vault root.** Auto-detection searches upward from the canvas
   for `.obsidian/`. If the canvas lives outside a vault (rare), pass
   `--vault-root` explicitly or the `file` nodes will all render as "missing".
3. **Pick an output dir.** Default is fine; if the user named one, use it.
4. **Run** the command above with `conda run -n webgis-ocean`. Capture stderr
   — it prints a `DONE` summary line with the html path, attachments path,
   and the count of copied files.
5. **Verify** by listing the output dir: the HTML plus an `attachments/`
   folder whose file count matches the summary line. Spot-check one image
   file to confirm it is non-empty.
6. **Report** the absolute path of the HTML file to the user and tell them
   they can open it directly (double-click) or host the folder statically.

## Tips & caveats

- The canvas coordinate system uses Obsidian's pixel units; negative coords
  are normal. The exporter computes a bounding box and auto-fits on load.
- Edges are SVG bezier curves with the optional `label` rendered as a
  stroked text label. Dragging a card redraws its connected edges live.
- Wikilinks `[[Target]]` inside text/file nodes become in-page anchors that
  jump to the matching card id (best-effort; works when the target note is
  also a node on the same canvas).
- Excalidraw-drawn canvases (`.excalidraw.md` pretending to be canvas) are
  **not** supported — only native `.canvas` JSON.
- Very large canvases (hundreds of nodes) still work but the initial layout
  pass is O(n); the JS view itself is cheap.
