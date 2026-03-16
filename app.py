import html
import os
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from downloader import WebsiteDownloader, get_site_name, zip_directory

load_dotenv()

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_FOLDER = BASE_DIR / "downloads"
GENERATED_FOLDER = BASE_DIR / "generated"

DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
GENERATED_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_REQUEST_BYTES", str(6 * 1024 * 1024)))

MAX_URL_LENGTH = int(os.getenv("MAX_URL_LENGTH", "2048"))
MAX_INDEX_HTML_CHARS = int(os.getenv("MAX_INDEX_HTML_CHARS", "250000"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))
DOWNLOAD_RETENTION_SECONDS = int(os.getenv("DOWNLOAD_RETENTION_SECONDS", "3600"))
OUTPUT_RETENTION_SECONDS = int(os.getenv("OUTPUT_RETENTION_SECONDS", "3600"))

UUID_PATTERN = re.compile(r"^[a-f0-9-]{36}$", re.IGNORECASE)
LOCAL_DEV_ORIGIN_PATTERN = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)
HTML_MARKER_TAG = "<html"
HTML_DOCTYPE_MARKER = "<!doctype html"
HTML_CLOSE_TAG = "</html>"
HTML_PARSER = "html.parser"
ERROR_JOB_ID_INVALID = "job_id invalido."
ERROR_JOB_ID_NOT_FOUND = "job_id nao encontrado."

EXTRA_CORS_ORIGINS = {
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}

download_jobs = {}
download_queues = {}
designer_outputs = {}
store_lock = threading.Lock()

DESIGNER_SYSTEM_INSTRUCTION = """You are a Design System Showcase Builder.

You are given SITE_URL and INDEX_HTML.

Your task is to create one new intermediate HTML file that acts as a living design

system + pattern library for this exact design.

Generate one single file called: design-system.html and place it in the same folder of

the html file.

This file must preserve the exact look & behavior of the reference design by

reusing the original HTML, CSS classes, animations, keyframes, transitions,

effects, and layout patterns - not approximations.

Build a single page composed of canonical examples of the design system,

organized in sections.

Extract HTML Design System v2

GOAL

HARD RULES (NON-NEGOTIABLE)

Do not redesign or invent new styles.

Reuse exact class names, animations, timing, easing, hover/focus states.

Reference the same CSS/JS assets used by the original.

If a style/component is not used in the reference HTML, do not add it.

The file must be self-explanatory by structure (sections = documentation).

Include a top horizontal nav with anchor links to each section.

OBJECTIVE

The first section MUST be a direct clone of the original Hero:

Allowed change (only this):

Forbidden:

Create a Typography section rendered as a spec table / vertical list.

Each row MUST contain:

Include ONLY styles that exist in the reference HTML, in this order:

Hero (Exact Clone, Text Adapted)
Same HTML structure

Same class names

Same layout

Same images and components

Same animations and interactions

Same buttons and background

Same UI components (if any)

Replace the hero text content to present the Design System

Keep similar text length and hierarchy

Do not change layout, spacing, alignment, or animations

Do not add or remove elements

Typography
Style name (e.g. "Heading 1", "Bold M")

Live text preview using the exact original HTML element and CSS classes

Font size / line-height label aligned right (format: 40px / 48px)

Heading 1

Heading 2

Rules:

This section must communicate hierarchy, scale, and rhythm at a glance.

Heading 3

Heading 4

Bold L / Bold M / Bold S

Paragraph (larger body, if exists)

Regular L / Regular M / Regular S

No inline styles

No normalization

Typography, colors, spacing, and gradients MUST come from original CSS

If a style uses gradient text, show it exactly the same

If a style does not exist, do NOT include it

Colors & Surfaces
Backgrounds (page, section, card, glass/blur if exists)

Borders, dividers, overlays

Gradients (as swatches + usage context)

UI Components
Buttons, inputs, cards, etc. (only those that exist)

Show states side-by-side: default / hover / active / focus / disabled

Inputs only if present (default/focus/error if applicable)

Layout & Spacing
Containers, grids, columns, section paddings

Show 2-3 real layout patterns from the reference (hero layout, grid, split)

Show all motion behaviors present:

Include a small Motion Gallery demonstrating each animation class.

If the reference uses icons:

If icons are not present, omit this section entirely.

Motion & Interaction
Entrance animations (if any)

Hover lifts/glows

Button hover transitions

Scroll/reveal behavior (only if present)

Icons
Display the same icon style/system

Show size variants and color inheritance

Use the same markup and classes

Return only one complete HTML document. Do not return markdown code fences.
"""


def _cleanup_folder(folder_path):
    for item in folder_path.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def _bootstrap_cleanup():
    _cleanup_folder(DOWNLOAD_FOLDER)
    _cleanup_folder(GENERATED_FOLDER)


def _is_uuid(value):
    if not value or not isinstance(value, str) or not UUID_PATTERN.match(value):
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _normalize_and_validate_url(raw_url):
    if not isinstance(raw_url, str):
        return None, "SITE_URL precisa ser uma string."

    candidate = raw_url.strip()
    if not candidate:
        return None, "SITE_URL nao pode ser vazio."

    if len(candidate) > MAX_URL_LENGTH:
        return None, f"SITE_URL excede o limite de {MAX_URL_LENGTH} caracteres."

    if any(char in candidate for char in ["\n", "\r", "\x00"]):
        return None, "SITE_URL contem caracteres invalidos."

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None, "SITE_URL deve iniciar com http:// ou https://."
    if not parsed.netloc:
        return None, "SITE_URL esta sem dominio."

    try:
        _ = parsed.port
    except ValueError:
        return None, "SITE_URL contem porta invalida."

    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))
    return normalized, None


def _cors_origin_for_request():
    origin = request.headers.get("Origin", "").strip()
    if not origin:
        return None

    if origin in EXTRA_CORS_ORIGINS:
        return origin

    if LOCAL_DEV_ORIGIN_PATTERN.match(origin):
        return origin

    return None


def _validate_index_html(index_html):
    if not isinstance(index_html, str):
        return False, "INDEX_HTML precisa ser uma string.", None

    content = index_html.strip()
    if not content:
        return False, "INDEX_HTML nao pode ser vazio.", None

    if len(content) > MAX_INDEX_HTML_CHARS:
        return False, f"INDEX_HTML excede o limite de {MAX_INDEX_HTML_CHARS} caracteres.", None

    lowered = content.lower()
    if HTML_MARKER_TAG not in lowered and HTML_DOCTYPE_MARKER not in lowered:
        return False, "INDEX_HTML precisa conter marcador HTML valido.", None

    soup = BeautifulSoup(content, HTML_PARSER)
    if soup.find(HTML_MARKER_TAG.replace("<", "")) is None:
        return False, "INDEX_HTML nao contem tag <html> valida.", None

    metadata = {
        "char_count": len(content),
        "has_head": soup.find("head") is not None,
        "has_body": soup.find("body") is not None,
    }
    return True, None, metadata


def _push_download_log(job_id, message):
    clean_message = str(message).replace("\n", " ").replace("\r", " ").strip()
    if not clean_message:
        return

    with store_lock:
        job = download_jobs.get(job_id)
        if job is not None:
            logs = job.setdefault("logs", [])
            logs.append(clean_message)
            if len(logs) > 300:
                job["logs"] = logs[-300:]
            job["updated_at"] = time.time()

    events_queue = download_queues.get(job_id)
    if events_queue is not None:
        events_queue.put({"event": "log", "message": clean_message})


def _push_download_done(job_id, status):
    events_queue = download_queues.get(job_id)
    if events_queue is not None:
        events_queue.put({"event": "done", "status": status})


def _run_download_job(job_id, site_url):
    job_dir = DOWNLOAD_FOLDER / job_id
    zip_path = DOWNLOAD_FOLDER / f"{job_id}.zip"

    def logger(message):
        _push_download_log(job_id, message)

    try:
        logger("Iniciando processo de download...")
        downloader = WebsiteDownloader(site_url, str(job_dir), log_callback=logger)
        success = downloader.process()
        if not success:
            raise RuntimeError("Falha ao baixar o site de referencia.")

        logger("Criando arquivo ZIP...")
        zip_directory(str(job_dir), str(zip_path))

        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)

        filename = f"{get_site_name(site_url)}.zip"

        with store_lock:
            download_jobs[job_id].update(
                {
                    "status": "complete",
                    "zip_path": str(zip_path),
                    "filename": filename,
                    "error": None,
                    "updated_at": time.time(),
                }
            )

        logger("Download finalizado com sucesso.")
        _push_download_done(job_id, "complete")
    except Exception as exc:
        err = str(exc)

        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)

        with store_lock:
            if job_id in download_jobs:
                download_jobs[job_id].update(
                    {
                        "status": "error",
                        "error": err,
                        "updated_at": time.time(),
                    }
                )

        _push_download_log(job_id, f"Erro no download: {err}")
        _push_download_done(job_id, "error")


def _cleanup_download_after_send(job_id):
    time.sleep(5)

    with store_lock:
        job = download_jobs.pop(job_id, None)
        download_queues.pop(job_id, None)

    if not job:
        return

    zip_path = job.get("zip_path")
    if zip_path:
        Path(zip_path).unlink(missing_ok=True)


def _collect_stale_ids(items, timestamp_key, max_age_seconds, now):
    stale_ids = []
    for item_id, payload in items.items():
        item_age = now - payload.get(timestamp_key, now)
        if item_age > max_age_seconds:
            stale_ids.append(item_id)
    return stale_ids


def _remove_download_artifact(job_id):
    with store_lock:
        job = download_jobs.pop(job_id, None)
        download_queues.pop(job_id, None)

    if job and job.get("zip_path"):
        Path(job["zip_path"]).unlink(missing_ok=True)


def _remove_output_artifact(output_id):
    with store_lock:
        output = designer_outputs.pop(output_id, None)

    if not output:
        return

    output_dir = Path(output["file_path"]).parent
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)


def _cleanup_stale_artifacts_loop():
    while True:
        time.sleep(300)
        now = time.time()

        with store_lock:
            stale_download_ids = _collect_stale_ids(
                download_jobs,
                "updated_at",
                DOWNLOAD_RETENTION_SECONDS,
                now,
            )
            stale_output_ids = _collect_stale_ids(
                designer_outputs,
                "created_at",
                OUTPUT_RETENTION_SECONDS,
                now,
            )

        for job_id in stale_download_ids:
            _remove_download_artifact(job_id)

        for output_id in stale_output_ids:
            _remove_output_artifact(output_id)


def _build_generation_prompt(site_url, index_html):
    return f"""{DESIGNER_SYSTEM_INSTRUCTION}

SITE_URL:
{site_url}

INDEX_HTML:
{index_html}
"""


def _serialize_html_attrs(attrs):
    if not attrs:
        return ""

    parts = []
    for key, value in attrs.items():
        if value is None:
            continue

        if isinstance(value, (list, tuple, set)):
            normalized = " ".join(str(item) for item in value if item is not None)
        else:
            normalized = str(value)

        normalized = normalized.strip()
        if not normalized:
            continue

        parts.append(f'{key}="{html.escape(normalized, quote=True)}"')

    if not parts:
        return ""
    return " " + " ".join(parts)


def _remove_scripts(fragment):
    for script in fragment.find_all("script"):
        script.decompose()
    for iframe in fragment.find_all("iframe"):
        iframe.decompose()


def _replace_first_text_node(tag, new_text):
    if tag is None:
        return

    for node in tag.descendants:
        if isinstance(node, NavigableString) and node.strip():
            node.replace_with(new_text)
            return


def _clean_fragment_html(tag):
    if tag is None:
        return ""

    fragment = BeautifulSoup(str(tag), HTML_PARSER)
    _remove_scripts(fragment)
    return str(fragment)


def _pick_hero_section(root):
    if root is None:
        return None

    h1 = root.find("h1")
    if h1 is None:
        return None

    fallback = None
    for ancestor in h1.parents:
        name = getattr(ancestor, "name", "")
        if name not in {"section", "div"}:
            continue

        snippet = str(ancestor)
        length = len(snippet)
        if 2500 <= length <= 65000:
            return ancestor
        if fallback is None and 300 <= length <= 65000:
            fallback = ancestor

    return fallback


def _retouch_hero_html(hero_tag):
    if hero_tag is None:
        return ""

    hero_soup = BeautifulSoup(str(hero_tag), HTML_PARSER)
    _remove_scripts(hero_soup)

    h1 = hero_soup.find("h1")
    if h1 is not None:
        _replace_first_text_node(h1, "Design System da Interface")

    first_heading = hero_soup.find(["h2", "p"])
    if first_heading is not None:
        _replace_first_text_node(first_heading, "Biblioteca viva de estilos, componentes e padroes")

    first_paragraph = hero_soup.find("p")
    if first_paragraph is not None:
        _replace_first_text_node(
            first_paragraph,
            "Guia visual extraido da pagina original para manter consistencia e acelerar novas implementacoes.",
        )

    return str(hero_soup)


def _collect_typography_samples(root):
    sample_specs = [
        ("Heading 1", "h1", "42px / 52px"),
        ("Heading 2", "h2", "36px / 44px"),
        ("Heading 3", "h3", "20px / 30px"),
        ("Heading 4", "h4", "18px / 28px"),
        ("Bold L", "strong", "16px / 24px"),
        ("Bold M", "b", "14px / 22px"),
        ("Bold S", "span", "13px / 20px"),
        ("Paragraph", "p", "16px / 26px"),
    ]

    rows = []
    seen_html = set()

    for style_name, tag_name, metrics in sample_specs:
        element = root.find(tag_name) if root else None
        if element is None:
            continue

        sample_html = _clean_fragment_html(element)
        if sample_html in seen_html:
            continue
        seen_html.add(sample_html)

        rows.append(
            {
                "name": style_name,
                "metrics": metrics,
                "sample_html": sample_html,
            }
        )

    return rows


def _extract_color_tokens(source_soup):
    style_text = "\n".join(style.get_text("\n") for style in source_soup.find_all("style"))
    if not style_text:
        return []

    tokens = []
    seen = set()

    for name, value in re.findall(r"(--[\w-]*(?:color|gradient|shadow)[\w-]*)\s*:\s*([^;]+);", style_text):
        token_name = name.strip()
        token_value = value.strip()
        if token_name in seen:
            continue
        seen.add(token_name)
        tokens.append((token_name, token_value))

    return tokens[:18]


def _collect_button_samples(root):
    if root is None:
        return []

    buttons = []
    for anchor in root.find_all("a"):
        classes = anchor.get("class") or []
        if not any("elementor-button" in cls for cls in classes):
            continue

        buttons.append(_clean_fragment_html(anchor))
        if len(buttons) >= 6:
            break

    return buttons


def _collect_layout_patterns(root):
    if root is None:
        return []

    patterns = []
    for container in root.find_all("div"):
        classes = container.get("class") or []
        if "e-parent" not in classes:
            continue

        if container.get("data-e-type") != "container":
            continue

        snippet = _clean_fragment_html(container)
        if len(snippet) > 50000:
            continue

        patterns.append(snippet)
        if len(patterns) >= 3:
            break

    return patterns


def _collect_motion_classes(root):
    if root is None:
        return []

    keys = ("swiper", "lazy", "animate", "motion", "fade", "transition", "scroll")
    found = set()

    for tag in root.find_all(class_=True):
        for cls in tag.get("class", []):
            lowered = cls.lower()
            if any(key in lowered for key in keys):
                found.add(cls)

    return sorted(found)[:24]


def _collect_icon_samples(root):
    if root is None:
        return []

    samples = []
    seen = set()

    for svg in root.find_all("svg"):
        parent = svg.parent if svg.parent else svg
        html_fragment = _clean_fragment_html(parent)
        if html_fragment in seen:
            continue
        seen.add(html_fragment)
        samples.append(html_fragment)
        if len(samples) >= 10:
            break

    return samples


def _build_head_for_local_fallback(source_soup, site_url):
    source_head = source_soup.find("head")

    if source_head is None:
        return (
            "<head>"
            "<meta charset=\"utf-8\"/>"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
            "<title>Design System Local Fallback</title>"
            "</head>"
        )

    head_soup = BeautifulSoup(str(source_head), HTML_PARSER)
    head_tag = head_soup.find("head")
    _remove_scripts(head_tag)

    title_tag = head_tag.find("title")
    title_text = "Design System"
    if site_url:
        title_text = f"Design System - {urlparse(site_url).netloc}"
    if title_tag is None:
        title_tag = head_soup.new_tag("title")
        head_tag.append(title_tag)
    title_tag.string = title_text

    fallback_style = head_soup.new_tag("style", attrs={"id": "layoutgenome-local-fallback-css"})
    fallback_style.string = """
    .ds-shell { max-width: 1240px; margin: 0 auto; padding: 24px 16px 72px; }
    .ds-nav { position: sticky; top: 0; z-index: 40; background: rgba(255,255,255,.92); backdrop-filter: blur(8px); border: 1px solid rgba(0,0,0,.08); border-radius: 14px; padding: 10px; margin-bottom: 20px; display: flex; gap: 8px; flex-wrap: wrap; }
    .ds-nav a { text-decoration: none; font-size: 13px; font-weight: 600; padding: 8px 12px; border-radius: 10px; border: 1px solid rgba(0,0,0,.12); }
    .ds-section { margin-top: 20px; padding: 22px; border: 1px solid rgba(0,0,0,.08); border-radius: 16px; background: rgba(255,255,255,.55); }
    .ds-section h2 { margin-top: 0; }
    .ds-type-row { display: grid; grid-template-columns: 200px minmax(0,1fr) 140px; gap: 12px; align-items: center; padding: 12px 0; border-bottom: 1px dashed rgba(0,0,0,.15); }
    .ds-type-row:last-child { border-bottom: none; }
    .ds-type-metrics { text-align: right; font-size: 12px; opacity: .72; }
    .ds-color-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(220px,1fr)); gap: 10px; }
    .ds-color-item { border: 1px solid rgba(0,0,0,.1); border-radius: 12px; padding: 10px; }
    .ds-swatch { width: 100%; height: 42px; border-radius: 10px; border: 1px solid rgba(0,0,0,.08); display: block; margin-bottom: 8px; }
    .ds-component-grid, .ds-icon-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(220px,1fr)); gap: 12px; }
    .ds-component-card, .ds-icon-card { border: 1px solid rgba(0,0,0,.1); border-radius: 12px; padding: 12px; background: #fff; }
    .ds-layout-grid { display: grid; gap: 14px; }
    .ds-motion-list { margin: 0; padding-left: 20px; columns: 2; }
    @media (max-width: 900px) {
      .ds-type-row { grid-template-columns: 1fr; }
      .ds-type-metrics { text-align: left; }
      .ds-motion-list { columns: 1; }
    }
    """
    head_tag.append(fallback_style)

    return str(head_tag)


def _build_local_designer_system(site_url, index_html):
    source_soup = BeautifulSoup(index_html, HTML_PARSER)
    source_body = source_soup.find("body")
    if source_body is None:
        return ""

    source_main = source_body.find("main") or source_body

    hero_source = _pick_hero_section(source_main)
    hero_html = _retouch_hero_html(hero_source)
    if not hero_html:
        hero_html = "<section><h1>Design System da Interface</h1><p>Fallback local gerado automaticamente.</p></section>"

    typography_rows = _collect_typography_samples(source_main)
    color_tokens = _extract_color_tokens(source_soup)
    button_samples = _collect_button_samples(source_main)
    layout_patterns = _collect_layout_patterns(source_main)
    motion_classes = _collect_motion_classes(source_main)
    icon_samples = _collect_icon_samples(source_main)

    typography_html = ""
    for row in typography_rows:
        typography_html += (
            "<div class=\"ds-type-row\">"
            f"<div><strong>{html.escape(row['name'])}</strong></div>"
            f"<div>{row['sample_html']}</div>"
            f"<div class=\"ds-type-metrics\">{html.escape(row['metrics'])}</div>"
            "</div>"
        )
    if not typography_html:
        typography_html = "<p>Nao foi possivel extrair estilos tipograficos desta pagina.</p>"

    color_html = ""
    for token_name, token_value in color_tokens:
        color_html += (
            "<div class=\"ds-color-item\">"
            f"<span class=\"ds-swatch\" style=\"background:{html.escape(token_value, quote=True)}\"></span>"
            f"<div><code>{html.escape(token_name)}</code></div>"
            f"<small>{html.escape(token_value)}</small>"
            "</div>"
        )
    if not color_html:
        color_html = "<p>Nenhum token de cor foi identificado no CSS carregado.</p>"

    components_html = ""
    for button in button_samples:
        components_html += f"<div class=\"ds-component-card\">{button}</div>"
    if not components_html:
        components_html = "<p>Nenhum componente de botao foi encontrado no HTML de referencia.</p>"

    layouts_html = ""
    for pattern in layout_patterns:
        layouts_html += f"<div class=\"ds-component-card\">{pattern}</div>"
    if not layouts_html:
        layouts_html = "<p>Nenhum padrao de layout principal foi identificado.</p>"

    motion_html = ""
    if motion_classes:
        motion_html = "<ul class=\"ds-motion-list\">"
        motion_html += "".join(f"<li><code>{html.escape(cls)}</code></li>" for cls in motion_classes)
        motion_html += "</ul>"
    else:
        motion_html = "<p>Nenhuma classe de movimento/interacao foi detectada automaticamente.</p>"

    icons_section_html = ""
    if icon_samples:
        icons_grid = "".join(f"<div class=\"ds-icon-card\">{sample}</div>" for sample in icon_samples)
        icons_section_html = (
            "<section id=\"icons\" class=\"ds-section\">"
            "<h2>Icons</h2>"
            "<div class=\"ds-icon-grid\">"
            f"{icons_grid}"
            "</div>"
            "</section>"
        )

    body_attrs = _serialize_html_attrs(source_body.attrs)
    head_html = _build_head_for_local_fallback(source_soup, site_url)

    site_url_safe = html.escape(site_url)

    return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
{head_html}
<body{body_attrs}>
  <main id=\"ds-content\" class=\"ds-shell\">
    <nav class=\"ds-nav\" aria-label=\"Navegacao do design system\">
      <a href=\"#hero-clone\">Hero</a>
      <a href=\"#typography\">Typography</a>
      <a href=\"#colors\">Colors &amp; Surfaces</a>
      <a href=\"#components\">UI Components</a>
      <a href=\"#layout\">Layout &amp; Spacing</a>
      <a href=\"#motion\">Motion &amp; Interaction</a>
      {"<a href=\"#icons\">Icons</a>" if icon_samples else ""}
    </nav>

    <section id=\"hero-clone\" class=\"ds-section\">
      <h2>Hero (Exact Clone, Text Adapted)</h2>
      <p><small>Fonte: {site_url_safe}</small></p>
      {hero_html}
    </section>

    <section id=\"typography\" class=\"ds-section\">
      <h2>Typography</h2>
      {typography_html}
    </section>

    <section id=\"colors\" class=\"ds-section\">
      <h2>Colors &amp; Surfaces</h2>
      <div class=\"ds-color-grid\">{color_html}</div>
    </section>

    <section id=\"components\" class=\"ds-section\">
      <h2>UI Components</h2>
      <div class=\"ds-component-grid\">{components_html}</div>
    </section>

    <section id=\"layout\" class=\"ds-section\">
      <h2>Layout &amp; Spacing</h2>
      <div class=\"ds-layout-grid\">{layouts_html}</div>
    </section>

    <section id=\"motion\" class=\"ds-section\">
      <h2>Motion &amp; Interaction</h2>
      {motion_html}
    </section>

    {icons_section_html}
  </main>
</body>
</html>
"""


def _extract_html_document(raw_text):
    if not raw_text:
        return ""

    content = str(raw_text).strip()

    fenced_blocks = re.findall(r"```(?:html)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    if fenced_blocks:
        content = max(fenced_blocks, key=len).strip()

    lowered = content.lower()
    start = lowered.find(HTML_DOCTYPE_MARKER)
    if start == -1:
        start = lowered.find(HTML_MARKER_TAG)

    end = lowered.rfind(HTML_CLOSE_TAG)

    if start != -1 and end != -1 and end > start:
        doc = content[start : end + len(HTML_CLOSE_TAG)].strip()
    else:
        doc = content.strip()

    doc_lower = doc.lower()
    if HTML_MARKER_TAG not in doc_lower:
        if "<body" in doc_lower:
            doc = f"<!DOCTYPE html>\n<html>\n{doc}\n{HTML_CLOSE_TAG}"
        else:
            return ""

    if HTML_CLOSE_TAG not in doc.lower():
        doc = f"{doc}\n{HTML_CLOSE_TAG}"

    if "<!doctype" not in doc.lower():
        doc = f"<!DOCTYPE html>\n{doc}"

    return doc.strip()


def _openrouter_models():
    models_env = os.getenv("OPENROUTER_MODELS", "").strip()
    models = [item.strip() for item in models_env.split(",") if item.strip()]
    if models:
        return models

    return [
        os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it:free").strip(),
        "deepseek/deepseek-chat-v3-0324:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


def _openrouter_extract_message(response_data):
    message = (
        response_data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    if isinstance(message, list):
        message = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in message
        )

    if isinstance(message, str):
        return message.strip()
    return ""


def _openrouter_request(headers, model, prompt):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Generate one single HTML document only. Never use markdown code fences.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"http {response.status_code} ({response.text[:160]})")

    content = _openrouter_extract_message(response.json())
    if not content:
        raise RuntimeError("resposta vazia")
    return content


def _call_openrouter(prompt):
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY nao configurada.")

    models = [model for model in _openrouter_models() if model]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:5001"),
        "X-Title": "LayoutGenome Bridge",
    }

    errors = []
    for model in models:
        try:
            return _openrouter_request(headers, model, prompt), model
        except Exception as exc:
            errors.append(f"{model}: {exc}")

    raise RuntimeError(" | ".join(errors) if errors else "Nenhum modelo OpenRouter disponivel.")


def _call_google_ai_studio(prompt):
    api_key = os.getenv("GOOGLE_AI_STUDIO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_AI_STUDIO_API_KEY nao configurada.")

    model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash").strip()
    if not model:
        model = "gemini-1.5-flash"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)

    if response.status_code >= 400:
        raise RuntimeError(f"{model}: http {response.status_code} ({response.text[:160]})")

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"{model}: resposta sem candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise RuntimeError(f"{model}: texto vazio")

    return text, model


def _call_openai(prompt):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not model:
        model = "gpt-4o-mini"

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Generate one single HTML document only. Never use markdown code fences.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"{model}: http {response.status_code} ({response.text[:160]})")

    data = response.json()
    message = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not isinstance(message, str) or not message.strip():
        raise RuntimeError(f"{model}: resposta vazia")

    return message, model


def _generate_designer_system(site_url, index_html):
    prompt = _build_generation_prompt(site_url, index_html)

    provider_chain = [
        ("openrouter", _call_openrouter),
        ("google_ai_studio", _call_google_ai_studio),
        ("openai", _call_openai),
    ]

    attempts = []

    for provider_name, provider_fn in provider_chain:
        try:
            raw_content, model_name = provider_fn(prompt)
            html_doc = _extract_html_document(raw_content)
            if not html_doc:
                raise RuntimeError("resposta nao contem HTML valido")
            return {
                "success": True,
                "provider": provider_name,
                "model": model_name,
                "designer_system_html": html_doc,
                "attempts": attempts,
            }
        except Exception as exc:
            attempts.append(f"{provider_name}: {exc}")

    local_html = _build_local_designer_system(site_url, index_html)
    if local_html:
        attempts.append("local_fallback: heuristica aplicada sem provider externo")
        return {
            "success": True,
            "provider": "local_fallback",
            "model": "heuristic-v1",
            "designer_system_html": local_html,
            "attempts": attempts,
            "fallback_mode": "automatic_local",
        }

    return {
        "success": False,
        "attempts": attempts,
        "manual_prompt": prompt,
    }


def _save_designer_output(html_content):
    output_id = str(uuid.uuid4())
    output_dir = GENERATED_FOLDER / output_id
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / "designer_system.html"
    file_path.write_text(html_content, encoding="utf-8")

    with store_lock:
        designer_outputs[output_id] = {
            "file_path": str(file_path),
            "created_at": time.time(),
        }

    return output_id, file_path


def _load_designer_output(output_id):
    with store_lock:
        output = designer_outputs.get(output_id)
    if output is None:
        return None

    path = Path(output["file_path"])
    if not path.exists():
        return None

    return path


def _next_stream_event(job_id, events_queue):
    try:
        return events_queue.get(timeout=30)
    except queue.Empty:
        with store_lock:
            current_job = download_jobs.get(job_id)
        if current_job is None:
            return None
        return {"event": "keepalive"}


def _stream_download_events(job_id, initial_logs, events_queue):
    for log_line in initial_logs:
        yield f"data: {log_line}\n\n"

    while True:
        event = _next_stream_event(job_id, events_queue)
        if event is None:
            break
        if event["event"] == "keepalive":
            yield ": keepalive\n\n"
            continue
        if event["event"] == "done":
            yield f"event: done\ndata: {event['status']}\n\n"
            break
        yield f"data: {event['message']}\n\n"


_bootstrap_cleanup()
cleanup_thread = threading.Thread(target=_cleanup_stale_artifacts_loop, daemon=True)
cleanup_thread.start()


@app.after_request
def append_cors_headers(response):
    origin = _cors_origin_for_request()
    if not origin:
        return response

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "86400"

    vary = response.headers.get("Vary")
    if vary:
        if "Origin" not in vary:
            response.headers["Vary"] = f"{vary}, Origin"
    else:
        response.headers["Vary"] = "Origin"

    return response


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    return jsonify({"error": "Payload excede o limite permitido para a requisicao."}), 413


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/validate-url", methods=["POST"])
def validate_url():
    payload = request.get_json(silent=True) or {}
    site_url = payload.get("site_url") or payload.get("url")

    normalized_url, error = _normalize_and_validate_url(site_url)
    if error:
        return jsonify({"valid": False, "error": error}), 400

    return jsonify(
        {
            "valid": True,
            "normalized_url": normalized_url,
            "message": "URL validada com sucesso.",
        }
    )


@app.route("/api/download-site", methods=["POST"])
def download_site():
    payload = request.get_json(silent=True) or {}
    site_url = payload.get("site_url") or payload.get("url")

    normalized_url, error = _normalize_and_validate_url(site_url)
    if error:
        return jsonify({"error": error}), 400

    job_id = str(uuid.uuid4())

    with store_lock:
        download_jobs[job_id] = {
            "job_id": job_id,
            "site_url": normalized_url,
            "status": "processing",
            "error": None,
            "zip_path": None,
            "filename": None,
            "logs": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        download_queues[job_id] = queue.Queue()

    thread = threading.Thread(target=_run_download_job, args=(job_id, normalized_url), daemon=True)
    thread.start()

    _push_download_log(job_id, "Job criado. Processamento iniciado em background.")

    return (
        jsonify(
            {
                "job_id": job_id,
                "status": "processing",
                "filename": f"{get_site_name(normalized_url)}.zip",
                "events_url": f"/api/download-events/{job_id}",
                "download_url": f"/api/download-zip/{job_id}",
            }
        ),
        202,
    )


@app.route("/api/download-events/<job_id>", methods=["GET"])
def download_events(job_id):
    if not _is_uuid(job_id):
        return jsonify({"error": ERROR_JOB_ID_INVALID}), 400

    with store_lock:
        job = download_jobs.get(job_id)
        events_queue = download_queues.get(job_id)
        initial_logs = list(job.get("logs", [])) if job else []

    if job is None or events_queue is None:
        return jsonify({"error": ERROR_JOB_ID_NOT_FOUND}), 404

    return Response(
        _stream_download_events(job_id, initial_logs, events_queue),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/download-status/<job_id>", methods=["GET"])
def download_status(job_id):
    if not _is_uuid(job_id):
        return jsonify({"error": ERROR_JOB_ID_INVALID}), 400

    with store_lock:
        job = download_jobs.get(job_id)

    if job is None:
        return jsonify({"error": ERROR_JOB_ID_NOT_FOUND}), 404

    response = {
        "job_id": job_id,
        "status": job["status"],
        "error": job.get("error"),
    }
    if job["status"] == "complete":
        response["download_url"] = f"/api/download-zip/{job_id}"
        response["filename"] = job.get("filename")
    return jsonify(response)


@app.route("/api/download-zip/<job_id>", methods=["GET"])
def download_zip(job_id):
    if not _is_uuid(job_id):
        return jsonify({"error": ERROR_JOB_ID_INVALID}), 400

    with store_lock:
        job = download_jobs.get(job_id)

    if job is None:
        return jsonify({"error": ERROR_JOB_ID_NOT_FOUND}), 404

    if job["status"] == "processing":
        return jsonify({"error": "ZIP ainda nao esta pronto."}), 409

    if job["status"] == "error":
        return jsonify({"error": job.get("error") or "Falha no processamento."}), 400

    zip_path = Path(job.get("zip_path") or "")
    if not zip_path.exists():
        return jsonify({"error": "Arquivo ZIP nao encontrado."}), 404

    filename = job.get("filename") or f"{job_id}.zip"
    response = send_file(str(zip_path), as_attachment=True, download_name=filename)

    cleanup_after_send = threading.Thread(target=_cleanup_download_after_send, args=(job_id,), daemon=True)
    cleanup_after_send.start()

    return response


@app.route("/api/validate-index", methods=["POST"])
def validate_index():
    payload = request.get_json(silent=True) or {}
    index_html = payload.get("index_html")

    is_valid, error, metadata = _validate_index_html(index_html)
    if not is_valid:
        return jsonify({"valid": False, "error": error}), 400

    return jsonify(
        {
            "valid": True,
            "message": "INDEX_HTML validado com sucesso.",
            "metadata": metadata,
        }
    )


@app.route("/api/generate-designer-system", methods=["POST"])
def generate_designer_system():
    payload = request.get_json(silent=True) or {}
    site_url = payload.get("site_url") or payload.get("url")
    index_html = payload.get("index_html")

    normalized_url, url_error = _normalize_and_validate_url(site_url)
    if url_error:
        return jsonify({"error": url_error}), 400

    is_valid, index_error, _metadata = _validate_index_html(index_html)
    if not is_valid:
        return jsonify({"error": index_error}), 400

    result = _generate_designer_system(normalized_url, index_html)
    if result["success"]:
        html_content = result["designer_system_html"]
        output_id, _file_path = _save_designer_output(html_content)

        return jsonify(
            {
                "success": True,
                "provider": result["provider"],
                "model": result["model"],
                "designer_system_html": html_content,
                "output_id": output_id,
                "preview_url": f"/api/designer-system/{output_id}/preview",
                "download_url": f"/api/designer-system/{output_id}/download",
                "attempts_before_success": result["attempts"],
            }
        )

    return jsonify(
        {
            "success": False,
            "fallback_required": True,
            "error": "Todos os provedores de IA falharam no momento.",
            "provider_attempts": result["attempts"],
            "manual_fallback_prompt": result["manual_prompt"],
            "manual_fallback_hint": (
                "Copie o prompt, cole em qualquer provider gratuito disponivel e "
                "cole o HTML gerado no campo de fallback manual da interface."
            ),
        }
    )


@app.route("/api/designer-system/<output_id>/preview", methods=["GET"])
def preview_designer_system(output_id):
    if not _is_uuid(output_id):
        return jsonify({"error": "output_id invalido."}), 400

    file_path = _load_designer_output(output_id)
    if file_path is None:
        return jsonify({"error": "output_id nao encontrado."}), 404

    return send_file(str(file_path), mimetype="text/html")


@app.route("/api/designer-system/<output_id>/download", methods=["GET"])
def download_designer_system(output_id):
    if not _is_uuid(output_id):
        return jsonify({"error": "output_id invalido."}), 400

    file_path = _load_designer_output(output_id)
    if file_path is None:
        return jsonify({"error": "output_id nao encontrado."}), 404

    return send_file(str(file_path), as_attachment=True, download_name="designer_system.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", port=port, threaded=True)