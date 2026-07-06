#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Obsidian Canvas -> standalone HTML exporter with attachments folder.

Reads a *.canvas (JSON) file produced by Obsidian's Canvas core plugin,
renders it as an interactive, pan/zoom HTML page that visually mirrors the
Canvas layout (groups, text cards, file cards, edges), and copies every
attachment that the canvas actually references (markdown notes, PNG/JPG/SVG
images, PDF, etc.) into an adjacent `attachments/` folder so the bundle is
fully portable.

Usage
-----
    python canvas_to_html.py <input.canvas> [--vault-root DIR]
                                [--output-dir DIR] [--title TEXT]
                                [--open]

If --vault-root is omitted, it is auto-detected by walking parent directories
of the .canvas file looking for `.obsidian/` (the canonical vault marker).
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, unquote

# --- Markdown rendering (Obsidian-flavour) ---------------------------------
try:
    import markdown as _md  # type: ignore
except ImportError:  # pragma: no cover - dependency check
    sys.stderr.write("[canvas_to_html] ERROR: python 'markdown' is required.\n"
                     "  conda run -n webgis-ocean pip install markdown pymdown-extensions\n")
    sys.exit(2)


# ============================================================================
# Obsidian colour palette (canvas colour index -> hex)
# ============================================================================
# Obsidian canvas nodes store colour either as "#rrggbb" or as one of the
# named palette indices "0".."6" mapped below.
CANVAS_COLORS = {
    "0": "#b8b8b8",  # grey (no colour / default)
    "1": "#e02d2d",  # red
    "2": "#eac54e",  # orange
    "3": "#5fb555",  # green
    "4": "#4a92f0",  # blue
    "5": "#a05cf0",  # purple
    "6": "#00bcd4",  # cyan
    "7": "#ff8a65",  # pink/peach (extra)
}


def resolve_color(color):
    """Resolve a canvas colour attribute to a CSS hex string."""
    if not color:
        return None
    if isinstance(color, str) and color.startswith("#"):
        return color
    return CANVAS_COLORS.get(str(color))


# ============================================================================
# Markdown -> HTML (Obsidian flavour)
# ============================================================================
def render_markdown(text, md):
    """Render Obsidian-flavour markdown to HTML.

    Handles internal wikilinks [[target]] -> clickable in-page anchors when the
    target note is part of the same export, otherwise a styled placeholder.
    """
    if not text:
        return ""

    # Obsidian wikilinks: [[target]] or [[target|label]] or [[target#heading]]
    def _wikilink_repl(m):
        target = m.group(1)
        label = m.group(2) or target
        anchor = re.sub(r"[^A-Za-z0-9_-]", "_", target.lower())
        return (f'<a class="wikilink" href="#card-{anchor}">'
                f'{html.escape(label)}</a>')

    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", _wikilink_repl, text)

    # Obsidian embeds: ![[image.png]] handled separately by file cards, but if
    # they leak into text we still render a labelled placeholder.
    text = re.sub(
        r"!\[\[([^\]]+)\]\]",
        lambda m: f'<div class="embed">[embed: {html.escape(m.group(1))}]</div>',
        text,
    )

    return md.convert(text)


# ============================================================================
# Vault resolution
# ============================================================================
def find_vault_root(canvas_path):
    """Walk parents of the canvas file looking for `.obsidian/`."""
    p = Path(canvas_path).resolve()
    for parent in [p.parent] + list(p.parents):
        if (parent / ".obsidian").is_dir():
            return parent
    return None


def resolve_vault_file(vault_root, rel_path):
    """Resolve an Obsidian-internal relative path.

    Canvas `file` values are POSIX-style paths from the vault root. Some are
    stored with leading slash or already-URL-encoded; we normalise both.
    """
    if not rel_path:
        return None
    rel = rel_path.lstrip("/")
    rel = unquote(rel)  # %20 -> space, etc.
    if vault_root is not None:
        candidate = (Path(vault_root) / rel).resolve()
        if candidate.exists():
            return candidate
        # try case-insensitive match on final segment
        parent = candidate.parent
        name = candidate.name
        if parent.exists():
            for entry in parent.iterdir():
                if entry.name.lower() == name.lower():
                    return entry
    return None


# ============================================================================
# Image detection
# ============================================================================
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp",
              ".avif", ".ico"}


def is_image(path_str):
    return Path(path_str).suffix.lower() in IMAGE_EXTS


# ============================================================================
# HTML generation
# ============================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{styles}</style>
</head>
<body>
<div id="topbar">
  <div class="t-title">{title}</div>
  <div class="t-meta">
    Exported {date} &middot; {n_nodes} nodes &middot; {n_edges} edges
    &middot; {n_attach} attachments
    &nbsp;|&nbsp;
    <button id="btn-fit" type="button">Fit</button>
    <button id="btn-reset" type="button">Reset</button>
    <span class="hint">wheel = zoom &middot; middle-drag = pan &middot; left-drag card = move &middot; left-drag corner = resize</span>
  </div>
</div>
<div id="canvas-area">
  <svg id="edge-layer" xmlns="http://www.w3.org/2000/svg"></svg>
  <div id="node-layer">{nodes_html}</div>
</div>
<script>{script}</script>
</body>
</html>
"""


def build_styles():
    return """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif;
  background: #1a1a1a; color: #e6e6e6; }
#topbar { position: fixed; top: 0; left: 0; right: 0; z-index: 50;
  background: rgba(24,24,24,.92); backdrop-filter: blur(6px);
  border-bottom: 1px solid #333; padding: 8px 14px; display: flex;
  flex-direction: column; gap: 2px; }
.t-title { font-size: 15px; font-weight: 600; color: #fff; }
.t-meta { font-size: 11px; color: #9a9a9a; display: flex; align-items: center;
  gap: 6px; flex-wrap: wrap; }
.t-meta button { background: #2c2c2c; color: #ddd; border: 1px solid #444;
  border-radius: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer; }
.t-meta button:hover { background: #3a3a3a; }
.t-meta .hint { color: #6a6a6a; margin-left: 8px; }

#canvas-area { position: absolute; top: 60px; left: 0; right: 0; bottom: 0;
  overflow: hidden; cursor: grab; background:
  radial-gradient(circle, rgba(255,255,255,.04) 1px, transparent 1px) 0 0/24px 24px,
  #161616; }
#canvas-area.dragging { cursor: grabbing; }

#edge-layer { position: absolute; top: 0; left: 0; overflow: visible;
  pointer-events: none; }
.edge-path { fill: none; stroke: #8a8a8a; stroke-width: 2;
  stroke-linecap: round; }
.edge-label { font-size: 11px; fill: #bbb;
  paint-order: stroke; stroke: #161616; stroke-width: 4px;
  stroke-linejoin: round; }

#node-layer { position: absolute; top: 0; left: 0; }

.node { position: absolute; background: #2a2a2a; color: #e8e8e8;
  border: 2px solid #555; border-radius: 8px; padding: 12px 14px;
  font-size: 13px; line-height: 1.5; overflow: hidden;
  box-shadow: 0 4px 14px rgba(0,0,0,.45); user-select: text; }
.node.group { background: rgba(255,255,255,.025); border-style: dashed;
  border-width: 2px; box-shadow: none; padding: 0; }
.node.group .group-label { position: absolute; top: 8px; left: 12px;
  font-size: 14px; font-weight: 600; padding: 2px 10px; border-radius: 4px;
  background: rgba(0,0,0,.35); }
.node.file, .node.text { cursor: move; }
.node .node-head { font-size: 11px; color: #888; margin-bottom: 6px;
  display: flex; justify-content: space-between; gap: 8px;
  border-bottom: 1px solid #333; padding-bottom: 4px; }
.node .node-type { text-transform: uppercase; letter-spacing: .5px; }
.node .node-link { color: #4a92f0; text-decoration: none; font-size: 11px; }
.node .node-link:hover { text-decoration: underline; }
.node .md-body { overflow-y: auto; max-height: 100%; }
.node .md-body h1, .node .md-body h2, .node .md-body h3 {
  color: #fff; margin: .3em 0; }
.node .md-body h1 { font-size: 1.25em; }
.node .md-body h2 { font-size: 1.1em; }
.node .md-body h3 { font-size: 1em; }
.node .md-body p { margin: .35em 0; }
.node .md-body code { background: #1d1d1d; padding: 1px 4px; border-radius: 3px;
  font-family: "Cascadia Code", Consolas, monospace; font-size: 12px; }
.node .md-body pre { background: #111; padding: 8px; border-radius: 6px;
  overflow-x: auto; }
.node .md-body pre code { background: none; padding: 0; }
.node .md-body ul, .node .md-body ol { margin: .35em 0; padding-left: 1.4em; }
.node .md-body a { color: #4a92f0; }
.node .md-body table { border-collapse: collapse; margin: .4em 0; }
.node .md-body th, .node .md-body td { border: 1px solid #444;
  padding: 3px 8px; }
.node .md-body img.embed-img { max-width: 100%; height: auto; display: block;
  margin: 4px 0; border-radius: 4px; }
.wikilink { color: #c792ea; text-decoration: none; border-bottom: 1px dotted #c792ea; }
.embed { font-size: 11px; color: #888; padding: 4px; border: 1px dashed #444;
  border-radius: 4px; }

/* ---- resize handle (bottom-right of every non-group card) ---- */
.resize-handle { position: absolute; right: 0; bottom: 0; width: 16px;
  height: 16px; cursor: nwse-resize; z-index: 5; opacity: 0;
  transition: opacity .15s; }
.resize-handle::after { content: ''; position: absolute; right: 3px;
  bottom: 3px; width: 8px; height: 8px;
  border-right: 2px solid #888; border-bottom: 2px solid #888;
  border-bottom-right-radius: 2px; }
.node.file:hover .resize-handle,
.node.text:hover .resize-handle,
.node.link:hover .resize-handle { opacity: 1; }
.node .md-body { padding-bottom: 6px; }
"""


def build_script(bounds, fit_params):
    """Build JS for pan/zoom + card dragging + resize.

    Interaction model:
      - Middle mouse button : pan the canvas. Works anywhere (over cards,
        handles, empty space) and is never intercepted.
      - Left mouse button on a card body : drag that card.
      - Left mouse button on a resize handle : resize that card.
      - Wheel : cursor-centric zoom.

    bounds: dict with min_x/min_y/max_x/max_y (canvas units) plus
            __nodes__ and __edges__ payloads for the JS.
    fit_params: dict with initial scale/translateX/translateY
    """
    return r"""
(function(){
  const area = document.getElementById('canvas-area');
  const nodeLayer = document.getElementById('node-layer');
  const edgeLayer = document.getElementById('edge-layer');
  const FIT = """ + json.dumps(fit_params) + r""";

  let scale = FIT.scale, tx = FIT.tx, ty = FIT.ty;

  function applyTransform(){
    nodeLayer.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    nodeLayer.style.transformOrigin = '0 0';
    edgeLayer.setAttribute('transform',
      `translate(${tx},${ty}) scale(${scale})`);
    edgeLayer.style.transformOrigin = '0 0';
  }
  applyTransform();

  // Suppress the browser's middle-click autoscroll, which would otherwise
  // hijack our pan gesture.
  area.addEventListener('mousedown', e=>{ if(e.button===1) e.preventDefault(); });
  area.addEventListener('auxclick', e=>{ if(e.button===1) e.preventDefault(); });

  // ---- MIDDLE-BUTTON PAN (never intercepted) ----
  let panning=false, sx=0, sy=0, stx=0, sty=0;
  area.addEventListener('mousedown', e=>{
    if(e.button !== 1) return;            // 1 = middle button
    panning=true; sx=e.clientX; sy=e.clientY; stx=tx; sty=ty;
    area.classList.add('dragging'); e.preventDefault();
  });
  window.addEventListener('mousemove', e=>{
    if(!panning) return;
    tx = stx + (e.clientX-sx); ty = sty + (e.clientY-sy);
    applyTransform();
  });
  window.addEventListener('mouseup', e=>{
    if(e.button===1 && panning){
      panning=false; area.classList.remove('dragging');
    }
  });

  // ---- zoom (cursor-centric) ----
  area.addEventListener('wheel', e=>{
    e.preventDefault();
    const rect = area.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    const delta = e.deltaY < 0 ? 1.12 : 1/1.12;
    const ns = Math.max(0.1, Math.min(6, scale*delta));
    tx = cx - (cx - tx) * (ns/scale);
    ty = cy - (cy - ty) * (ns/scale);
    scale = ns; applyTransform();
  }, {passive:false});

  // ---- edges (built first so redraw fns exist) ----
  const NODES = window.__NODES = """ + json.dumps(bounds['__nodes__']) + r""";
  const EDGES = """ + json.dumps(bounds['__edges__']) + r""";

  function sidePoint(n, side){
    if(!n) return null;
    const x=n.x, y=n.y, w=n.width, h=n.height;
    switch(side){
      case 'top':    return [x+w/2, y];
      case 'bottom': return [x+w/2, y+h];
      case 'left':   return [x, y+h/2];
      case 'right':  return [x+w, y+h/2];
      default:       return [x+w/2, y+h/2];
    }
  }

  function curve(p1, p2){
    const [x1,y1]=p1, [x2,y2]=p2;
    const dx=x2-x1, dy=y2-y1;
    const c1x = x1 + dx*0.5, c1y = y1;
    const c2x = x2 - dx*0.5, c2y = y2;
    return `M ${x1},${y1} C ${c1x},${c1y} ${c2x},${c2y} ${x2},${y2}`;
  }

  // Build a fresh path+text pair for one edge. The text is positioned at the
  // bezier midpoint (t=0.5) so it always tracks the curve.
  function buildEdge(e){
    const a = NODES[e.from], b = NODES[e.to];
    const g = document.createElementNS('http://www.w3.org/2000/svg','g');
    g.setAttribute('data-edge', e.id);
    if(!a || !b){ return g; }
    const p1 = sidePoint(a, e.fromSide||'right');
    const p2 = sidePoint(b, e.toSide||'left');
    const d = curve(p1, p2);
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d', d);
    path.setAttribute('class','edge-path');
    g.appendChild(path);
    if(e.label){
      // cubic bezier point at t=0.5:
      // B(t) = (1-t)^3*P0 + 3(1-t)^2 t*P1 + 3(1-t)t^2*P2 + t^3*P3
      const c1x = p1[0] + (p2[0]-p1[0])*0.5, c1y = p1[1];
      const c2x = p2[0] - (p2[0]-p1[0])*0.5, c2y = p2[1];
      const mx = 0.125*p1[0] + 0.375*c1x + 0.375*c2x + 0.125*p2[0];
      const my = 0.125*p1[1] + 0.375*c1y + 0.375*c2y + 0.125*p2[1];
      const t = document.createElementNS('http://www.w3.org/2000/svg','text');
      t.setAttribute('x', mx); t.setAttribute('y', my-6);
      t.setAttribute('text-anchor','middle');
      t.setAttribute('class','edge-label');
      t.setAttribute('data-edge-label', e.id);
      t.textContent = e.label;
      g.appendChild(t);
    }
    return g;
  }

  function redrawAll(){
    while(edgeLayer.firstChild) edgeLayer.removeChild(edgeLayer.firstChild);
    EDGES.forEach(e=>{
      edgeLayer.appendChild(buildEdge(e));
    });
  }
  // Rebuild the single edge group so BOTH path and label move together.
  function redrawEdgesFor(id){
    EDGES.forEach(e=>{
      if(e.from!==id && e.to!==id) return;
      const old = edgeLayer.querySelector(`[data-edge="${e.id}"]`);
      const fresh = buildEdge(e);
      if(old){ edgeLayer.replaceChild(fresh, old); }
      else { edgeLayer.appendChild(fresh); }
    });
  }
  redrawAll();

  // ---- LEFT-BUTTON: resize handle OR card drag ----
  // Decide based on what was under the cursor when left button went down.
  area.addEventListener('mousedown', e=>{
    if(e.button !== 0) return;             // 0 = left button
    const handle = e.target.closest('.resize-handle');
    const card   = e.target.closest('.node.file, .node.text, .node.link');
    if(handle){
      startResize(handle, e);
    } else if(card){
      startDrag(card, e);
    }
    // else: left-click on empty space -> nothing (use middle to pan)
  });

  function startDrag(card, e){
    e.preventDefault();
    const id = card.dataset.id;
    const startX = e.clientX, startY = e.clientY;
    const data = NODES[id];
    if(!data) return;
    const ox = data.x, oy = data.y;
    card.classList.add('dragging-card');
    const onMove = ev=>{
      data.x = ox + (ev.clientX-startX)/scale;
      data.y = oy + (ev.clientY-startY)/scale;
      card.style.left = data.x + 'px';
      card.style.top  = data.y + 'px';
      redrawEdgesFor(id);
    };
    const onUp = ()=>{
      card.classList.remove('dragging-card');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  function startResize(handle, e){
    e.preventDefault();
    e.stopPropagation();
    const card = handle.closest('.node');
    const id = card.dataset.id;
    const startX = e.clientX, startY = e.clientY;
    const data = NODES[id];
    if(!data) return;
    const ow = data.width, oh = data.height;
    const minW = 80, minH = 40;
    const onMove = ev=>{
      data.width  = Math.max(minW, ow + (ev.clientX-startX)/scale);
      data.height = Math.max(minH, oh + (ev.clientY-startY)/scale);
      card.style.width  = data.width + 'px';
      card.style.height = data.height + 'px';
      redrawEdgesFor(id);
    };
    const onUp = ()=>{
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  // ---- buttons ----
  function fit(){
    const B = """ + json.dumps({
        'min_x': bounds['min_x'], 'min_y': bounds['min_y'],
        'max_x': bounds['max_x'], 'max_y': bounds['max_y']}) + r""";
    const w = B.max_x - B.min_x, h = B.max_y - B.min_y;
    const rect = area.getBoundingClientRect();
    const pad = 60;
    scale = Math.min((rect.width-pad*2)/w, (rect.height-pad*2)/h);
    scale = Math.max(0.1, Math.min(2.5, scale));
    tx = -B.min_x*scale + (rect.width - w*scale)/2;
    ty = -B.min_y*scale + (rect.height - h*scale)/2;
    applyTransform();
  }
  document.getElementById('btn-fit').addEventListener('click', fit);
  document.getElementById('btn-reset').addEventListener('click', ()=>{
    scale=FIT.scale; tx=FIT.tx; ty=FIT.ty; applyTransform();
  });
  window.addEventListener('resize', applyTransform);
  setTimeout(fit, 30);
})();
"""


def compute_fit(area_w, area_h, min_x, min_y, max_x, max_y):
    """Compute initial viewport transform that fits the whole canvas."""
    w = max_x - min_x
    h = max_y - min_y
    pad = 80
    scale = min((area_w - pad * 2) / max(w, 1), (area_h - pad * 2) / max(h, 1))
    scale = max(0.1, min(2.5, scale))
    tx = -min_x * scale + (area_w - w * scale) / 2
    ty = -min_y * scale + (area_h - h * scale) / 2
    return {"scale": scale, "tx": tx, "ty": ty}


def build_node_html(node, md, vault_root, attachments_dir_rel,
                    copied_files):
    """Build the HTML for a single canvas node.

    copied_files: dict mapping absolute attachment source path -> relative
    path inside attachments/ (so we can rewrite links).
    """
    nid = node["id"]
    x = node.get("x", 0)
    y = node.get("y", 0)
    w = node.get("width", 250)
    h = node.get("height", 120)
    ntype = node.get("type", "text")
    color = resolve_color(node.get("color"))
    border_color = color or "#555"

    style = (f"left:{x}px; top:{y}px; width:{w}px; height:{h}px; "
             f"border-color:{border_color};")

    if ntype == "group":
        label = html.escape(node.get("label") or "")
        label_bg = color or "#444"
        inner = (f'<div class="group-label" style="background:{label_bg};'
                 f'color:#fff;">{label}</div>')
        return (f'<div class="node group" data-id="{nid}" id="card-{nid}" '
                f'style="{style}">{inner}</div>')

    if ntype == "text":
        text = node.get("text", "")
        body_html = render_markdown(text, md)
        inner = (f'<div class="md-body">{body_html}</div>'
                 f'<div class="resize-handle"></div>')
        return (f'<div class="node text" data-id="{nid}" id="card-{nid}" '
                f'style="{style}">{inner}</div>')

    if ntype == "file":
        file_ref = node.get("file", "")
        abs_path = resolve_vault_file(vault_root, file_ref)
        fname = Path(file_ref).name if file_ref else "(unknown)"

        head = (f'<div class="node-head">'
                f'<span class="node-type">file</span>'
                f'</div>')

        body_parts = []

        if abs_path is None:
            body_parts.append(
                f'<div class="md-body"><em>missing file:</em> '
                f'<code>{html.escape(file_ref)}</code></div>')
        elif is_image(abs_path.name):
            # copy into attachments and embed
            rel = copied_files.get(str(abs_path))
            if rel is None:
                rel = _safe_copy(abs_path, attachments_dir_rel)
                copied_files[str(abs_path)] = rel
            body_parts.append(
                f'<div class="md-body">'
                f'<img class="embed-img" src="{html.escape(rel)}" '
                f'alt="{html.escape(fname)}"></div>')
        elif abs_path.suffix.lower() == ".md":
            # copy the .md source into attachments so the bundle is complete
            md_rel = copied_files.get(str(abs_path))
            if md_rel is None:
                md_rel = _safe_copy(abs_path, attachments_dir_rel)
                copied_files[str(abs_path)] = md_rel
            # render the markdown content
            try:
                txt = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                txt = abs_path.read_text(encoding="utf-8", errors="replace")
            # rewrite any ![[image]] embeds to point at attachments
            txt = _rewrite_md_embeds(txt, vault_root, attachments_dir_rel,
                                     copied_files)
            body_html = render_markdown(txt, md)
            link_html = (f'<a class="node-link" href="'
                         f'{html.escape(md_rel)}" '
                         f'target="_blank">open .md</a>')
            head = (f'<div class="node-head">'
                    f'<span class="node-type">{html.escape(fname)}</span>'
                    f'{link_html}</div>')
            body_parts.append(f'<div class="md-body">{body_html}</div>')
        else:
            # other binary attachments (pdf, etc) -> link
            rel = copied_files.get(str(abs_path))
            if rel is None:
                rel = _safe_copy(abs_path, attachments_dir_rel)
                copied_files[str(abs_path)] = rel
            body_parts.append(
                f'<div class="md-body"><a class="node-link" href="'
                f'{html.escape(rel)}" target="_blank">'
                f'{html.escape(fname)}</a></div>')

        return (f'<div class="node file" data-id="{nid}" id="card-{nid}" '
                f'style="{style}">{head}{"".join(body_parts)}'
                f'<div class="resize-handle"></div></div>')

    if ntype == "link":
        url = node.get("url", "")
        label = html.escape(node.get("label") or url)
        inner = (f'<div class="md-body">'
                 f'<a href="{html.escape(url)}" target="_blank" '
                 f'rel="noopener">{label}</a></div>'
                 f'<div class="resize-handle"></div>')
        return (f'<div class="node link" data-id="{nid}" id="card-{nid}" '
                f'style="{style}">{inner}</div>')

    # fallback
    return (f'<div class="node" data-id="{nid}" id="card-{nid}" '
            f'style="{style}"><div class="md-body">(unknown node type '
            f'{html.escape(ntype)})</div></div>')


def _safe_copy(src_abs, attachments_dir_rel):
    """Copy src into the attachments dir, dedup by name. Returns rel path."""
    attachments_dir = attachments_dir_rel  # Path object
    name = src_abs.name
    target = attachments_dir / name
    counter = 1
    stem = src_abs.stem
    suffix = src_abs.suffix
    while target.exists():
        # if same file already there, skip copy
        if target.stat().st_size == src_abs.stat().st_size:
            break
        target = attachments_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    else:
        try:
            shutil.copy2(src_abs, target)
        except Exception as e:  # pragma: no cover
            sys.stderr.write(f"[canvas_to_html] WARN copy failed for "
                             f"{src_abs}: {e}\n")
    # return path relative to the html output dir (one level up from
    # attachments/)
    return "attachments/" + quote(target.name)


def _rewrite_md_embeds(md_text, vault_root, attachments_dir, copied_files):
    """Rewrite ![[image.png]] and ![[note]] embeds in markdown text.

    For images -> <img src="attachments/...">.
    For markdown notes -> inline render is too complex here; we keep the
    link text.
    """
    def _embed_repl(m):
        target = m.group(1).strip()
        # support target|width
        target = target.split("|")[0].strip()
        abs_path = resolve_vault_file(vault_root, target)
        if abs_path and is_image(abs_path.name):
            rel = copied_files.get(str(abs_path))
            if rel is None:
                rel = _safe_copy(abs_path, attachments_dir)
                copied_files[str(abs_path)] = rel
            return f'<img class="embed-img" src="{html.escape(rel)}">'
        # not an image -> leave a labelled embed marker
        return f'*[embed: {html.escape(target)}]*'

    return re.sub(r"!\[\[([^\]]+)\]\]", _embed_repl, md_text)


# ============================================================================
# Main conversion
# ============================================================================
def convert(canvas_path, output_dir=None, vault_root=None, title=None,
            open_after=False):
    canvas_path = Path(canvas_path).resolve()
    if not canvas_path.exists():
        raise FileNotFoundError(f"canvas not found: {canvas_path}")

    if vault_root is None:
        vault_root = find_vault_root(canvas_path)
        if vault_root:
            sys.stderr.write(
                f"[canvas_to_html] vault root auto-detected: {vault_root}\n")

    if output_dir is None:
        output_dir = canvas_path.parent / (canvas_path.stem + "_html")
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir = output_dir / "attachments"
    attachments_dir.mkdir(exist_ok=True)

    if title is None:
        title = canvas_path.stem

    # ---- markdown renderer with Obsidian-ish extensions ----
    md = _md.Markdown(extensions=[
        "extra",            # tables, fenced_code, abbr, attr_list, def_list
        "codehilite",       # code highlighting (css classes only)
        "toc",              # table of contents
        "pymdownx.tilde",   # ~~delete~~
        "pymdownx.tasklist",
        "pymdownx.magiclink",
        "pymdownx.betterem",
        "sane_lists",
    ], extension_configs={
        "codehilite": {"css_class": "codehilite", "guess_lang": False},
    })

    data = json.loads(canvas_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    # ---- compute bounds ----
    xs, ys = [], []
    for n in nodes:
        x = n.get("x", 0); y = n.get("y", 0)
        w = n.get("width", 250); h = n.get("height", 120)
        xs += [x, x + w]; ys += [y, y + h]
    min_x = min(xs) if xs else 0
    min_y = min(ys) if ys else 0
    max_x = max(xs) if xs else 1
    max_y = max(ys) if ys else 1
    # add padding
    pad = 100
    min_x -= pad; min_y -= pad; max_x += pad; max_y += pad

    # ---- build node + edge meta for JS ----
    node_meta = {}
    for n in nodes:
        node_meta[n["id"]] = {
            "x": n.get("x", 0), "y": n.get("y", 0),
            "width": n.get("width", 250), "height": n.get("height", 120),
            "type": n.get("type", "text"),
        }
    edge_meta = []
    for e in edges:
        edge_meta.append({
            "id": e.get("id", ""),
            "from": e.get("fromNode"),
            "to": e.get("toNode"),
            "fromSide": e.get("fromSide"),
            "toSide": e.get("toSide"),
            "label": e.get("label", ""),
        })

    # ---- render nodes ----
    copied_files = {}  # abs_path -> attachments-relative
    nodes_html = []
    # render groups first so they sit behind
    ordered = sorted(nodes, key=lambda n: 0 if n.get("type") == "group" else 1)
    for n in ordered:
        nodes_html.append(build_node_html(
            n, md, vault_root, attachments_dir, copied_files))

    # ---- fit ----
    area_w = 1400  # nominal; JS will re-fit on load
    area_h = 900
    fit_params = compute_fit(area_w, area_h, min_x, min_y, max_x, max_y)

    # ---- assemble final HTML ----
    html_doc = HTML_TEMPLATE.format(
        title=html.escape(title),
        date=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        n_nodes=len(nodes),
        n_edges=len(edges),
        n_attach=len(copied_files),
        nodes_html="\n".join(nodes_html),
        styles=build_styles(),
        script=build_script({
            "min_x": min_x, "min_y": min_y,
            "max_x": max_x, "max_y": max_y,
            "__nodes__": node_meta,
            "__edges__": edge_meta,
        }, fit_params),
    )

    out_html = output_dir / (canvas_path.stem + ".html")
    out_html.write_text(html_doc, encoding="utf-8")

    sys.stderr.write(
        f"[canvas_to_html] DONE\n"
        f"  html:         {out_html}\n"
        f"  attachments:  {attachments_dir} ({len(copied_files)} files)\n")

    if open_after:
        try:
            import webbrowser
            webbrowser.open(out_html.as_uri())
        except Exception:
            pass
    return out_html, attachments_dir, copied_files


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Export an Obsidian .canvas to a portable HTML bundle "
                    "with attachments.")
    ap.add_argument("canvas", help="Path to the .canvas file")
    ap.add_argument("--vault-root", default=None,
                    help="Obsidian vault root (auto-detected if omitted)")
    ap.add_argument("--output-dir", default=None,
                    help="Output directory (default: <canvas>_html/)")
    ap.add_argument("--title", default=None, help="HTML page title")
    ap.add_argument("--open", action="store_true",
                    help="Open the exported HTML in the default browser")
    args = ap.parse_args(argv)

    convert(args.canvas, output_dir=args.output_dir,
            vault_root=(Path(args.vault_root) if args.vault_root else None),
            title=args.title, open_after=args.open)


if __name__ == "__main__":
    main()
