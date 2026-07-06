# Examples

This directory holds a small, harmless demo canvas plus documentation on how
to reproduce a larger worked export. The actual output folders (`*_html/`)
are gitignored — run the converter yourself to generate them.

---

## Small demo (in this repo)

| file | what |
|------|------|
| [`demo.canvas`](./demo.canvas) | A 6-node canvas (no proprietary content) — groups, text cards, markdown tables, edges. |
| [`demo-screenshot.png`](./demo-screenshot.png) | Screenshot of the exported HTML, also used as the README banner. |

### Reproduce

```bash
# from repo root
pip install -r requirements.txt
python scripts/canvas_to_html.py examples/demo.canvas \
  --output-dir examples/demo_html --title "Demo Canvas"
# then open examples/demo_html/demo.html in a browser
```

---

## Worked example: research canvas

Input canvas (not in this repo — private):

```
方案13完整构建流程.canvas
```

A 89-node Obsidian canvas describing a full model-building pipeline
(groups, text cards, `.md` file cards, SHAP figure cards, and ~84 labelled
edges).

### Reproduce

```bash
# from the repo root
pip install -r requirements.txt

python scripts/canvas_to_html.py \
  "/path/to/方案13完整构建流程.canvas" \
  --output-dir ./examples/方案13完整构建流程_html
```

### Expected output

```
方案13完整构建流程_html/
├── 方案13完整构建流程.html        (~245 KB, self-contained)
└── attachments/
    ├── 0-方案13全量DatasetA正式构建流程.md
    ├── 1-研究问题与因变量对应.md
    ├── ... (16 markdown notes total)
    ├── scheme13b_shap_group_contribution_...png
    ├── scheme13b_shap_poi_aoi_heatmap_...png
    └── ... (6 PNG figures total)
```

Open the `.html` in any browser — middle-drag to pan, wheel to zoom.

### What to verify

- **7 groups** render as dashed, colour-coded containers.
- **58 text cards** show rendered markdown (tables, code blocks, wikilinks).
- **22 file cards**: 16 `.md` notes render inline + link their source;
  6 PNG figures embed inline.
- **~84 edges** draw as labelled bezier curves; drag any card and its
  connected edges (and their labels) follow.
