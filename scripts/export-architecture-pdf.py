#!/usr/bin/env python3
"""Render the GM Studio architecture Markdown guide as a dependency-free PDF."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


PAGE_W = 595.28
PAGE_H = 841.89
LEFT = 54.0
RIGHT = 54.0
TOP = 62.0
BOTTOM = 55.0
CONTENT_W = PAGE_W - LEFT - RIGHT

NAVY = (0.067, 0.176, 0.302)
BLUE = (0.09, 0.31, 0.47)
CYAN = (0.27, 0.72, 0.78)
PALE_BLUE = (0.93, 0.97, 0.98)
PALE_CYAN = (0.90, 0.97, 0.97)
INK = (0.10, 0.15, 0.19)
MUTED = (0.34, 0.39, 0.42)
LINE = (0.82, 0.85, 0.86)
WHITE = (1.0, 1.0, 1.0)


def clean_text(value: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("`", "")
    replacements = {
        "—": " - ", "–": "-", "‘": "'", "’": "'",
        "“": '"', "”": '"', "→": "->", "↔": "<->",
        "…": "...", " ": " ", "≥": ">=", "≤": "<=",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.encode("cp1252", errors="replace").decode("cp1252")


def pdf_escape(value: str) -> str:
    return clean_text(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def rgb(color: tuple[float, float, float], stroke: bool = False) -> str:
    suffix = "RG" if stroke else "rg"
    return f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} {suffix}"


def approximate_width(value: str, size: float, mono: bool = False) -> float:
    factor = 0.60 if mono else 0.51
    return len(clean_text(value)) * size * factor


def wrap(value: str, width: float, size: float, mono: bool = False) -> list[str]:
    value = clean_text(value).strip()
    if not value:
        return [""]
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if approximate_width(candidate, size, mono) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        if approximate_width(word, size, mono) <= width:
            current = word
            continue
        max_chars = max(2, int(width / (size * (0.60 if mono else 0.51))))
        while len(word) > max_chars:
            lines.append(word[:max_chars])
            word = word[max_chars:]
        current = word
    if current:
        lines.append(current)
    return lines


@dataclass
class Page:
    commands: list[str] = field(default_factory=list)

    def fill_rect(self, x: float, y: float, width: float, height: float, color=WHITE) -> None:
        self.commands.append(f"q {rgb(color)} {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f Q")

    def stroke_rect(self, x: float, y: float, width: float, height: float, color=LINE, line_width: float = 0.7) -> None:
        self.commands.append(f"q {rgb(color, True)} {line_width:.2f} w {x:.2f} {y:.2f} {width:.2f} {height:.2f} re S Q")

    def line(self, x1: float, y1: float, x2: float, y2: float, color=LINE, line_width: float = 1.0) -> None:
        self.commands.append(f"q {rgb(color, True)} {line_width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q")

    def text(self, x: float, y: float, value: str, size: float = 10, font: str = "F1", color=INK) -> None:
        self.commands.append(
            f"BT /{font} {size:.2f} Tf {rgb(color)} 1 0 0 1 {x:.2f} {y:.2f} Tm ({pdf_escape(value)}) Tj ET"
        )

    def polygon(self, points: list[tuple[float, float]], color=INK) -> None:
        if not points:
            return
        path = f"{points[0][0]:.2f} {points[0][1]:.2f} m " + " ".join(
            f"{x:.2f} {y:.2f} l" for x, y in points[1:]
        )
        self.commands.append(f"q {rgb(color)} {path} h f Q")


class PdfGuide:
    def __init__(self) -> None:
        self.pages: list[Page] = []
        self.page = Page()
        self.pages.append(self.page)
        self.y = PAGE_H - TOP
        self.diagram_index = 0

    def new_page(self) -> None:
        self.page = Page()
        self.pages.append(self.page)
        self.y = PAGE_H - TOP

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.new_page()

    def text_lines(self, lines: list[str], x: float, width: float, size: float, leading: float,
                   font: str = "F1", color=INK) -> None:
        for line in lines:
            self.page.text(x, self.y, line, size, font, color)
            self.y -= leading

    def paragraph(self, value: str) -> None:
        lines = wrap(value, CONTENT_W, 9.6)
        height = len(lines) * 13.4 + 6
        self.ensure(height)
        self.text_lines(lines, LEFT, CONTENT_W, 9.6, 13.4, color=INK)
        self.y -= 6

    def heading(self, level: int, value: str) -> None:
        value = clean_text(value)
        if level == 1:
            if len(self.pages) > 1 or self.y < PAGE_H - TOP - 20:
                self.new_page()
            height, size, gap = 55, 23, 18
            self.page.fill_rect(0, PAGE_H - 126, PAGE_W, 126, NAVY)
            self.page.fill_rect(LEFT, PAGE_H - 130, 92, 4, CYAN)
            self.page.text(LEFT, PAGE_H - 82, value, size, "F2", WHITE)
            self.y = PAGE_H - 156
            return
        size = 15.5 if level == 2 else 11.8
        leading = 20 if level == 2 else 16
        top_gap = 13 if level == 2 else 7
        lines = wrap(value, CONTENT_W, size)
        self.ensure(top_gap + len(lines) * leading + 8)
        self.y -= top_gap
        if level == 2:
            self.page.fill_rect(LEFT, self.y + 4, 4, 15, CYAN)
            x = LEFT + 12
            color = NAVY
        else:
            x = LEFT
            color = BLUE
        self.text_lines(lines, x, CONTENT_W - (x - LEFT), size, leading, "F2", color)
        self.y -= 5

    def bullet(self, value: str, number: str | None = None) -> None:
        indent = 18
        lines = wrap(value, CONTENT_W - indent, 9.4)
        self.ensure(len(lines) * 13 + 4)
        marker = number if number is not None else "-"
        self.page.text(LEFT + 2, self.y, marker, 9.4, "F2", CYAN if number is None else BLUE)
        self.text_lines(lines, LEFT + indent, CONTENT_W - indent, 9.4, 13, color=INK)
        self.y -= 3

    def quote(self, value: str) -> None:
        lines = wrap(value, CONTENT_W - 32, 11)
        height = len(lines) * 15 + 28
        self.ensure(height + 8)
        top = self.y
        self.page.fill_rect(LEFT, top - height + 8, CONTENT_W, height, PALE_CYAN)
        self.page.fill_rect(LEFT, top - height + 8, 5, height, CYAN)
        self.y -= 14
        self.text_lines(lines, LEFT + 18, CONTENT_W - 32, 11, 15, "F3", NAVY)
        self.y -= 14

    def code(self, lines: list[str]) -> None:
        rendered: list[str] = []
        for line in lines:
            rendered.extend(wrap(line if line else " ", CONTENT_W - 24, 7.3, mono=True))
        height = len(rendered) * 10 + 22
        self.ensure(height + 7)
        top = self.y
        self.page.fill_rect(LEFT, top - height + 4, CONTENT_W, height, (0.965, 0.969, 0.965))
        self.page.stroke_rect(LEFT, top - height + 4, CONTENT_W, height, LINE)
        self.y -= 11
        self.text_lines(rendered, LEFT + 12, CONTENT_W - 24, 7.3, 10, "F4", INK)
        self.y -= 11

    def table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        columns = max(len(row) for row in rows)
        widths = [CONTENT_W / columns] * columns
        if columns == 2:
            widths = [CONTENT_W * 0.31, CONTENT_W * 0.69]
        prepared: list[tuple[list[list[str]], float]] = []
        for row in rows:
            cells = [wrap(row[index] if index < len(row) else "", widths[index] - 14, 8.1) for index in range(columns)]
            height = max(len(cell) for cell in cells) * 10.4 + 14
            prepared.append((cells, height))
        self.ensure(min(sum(height for _, height in prepared) + 8, 180))
        for row_index, (cells, height) in enumerate(prepared):
            if self.y - height < BOTTOM:
                self.new_page()
            y_bottom = self.y - height + 4
            self.page.fill_rect(LEFT, y_bottom, CONTENT_W, height, NAVY if row_index == 0 else (WHITE if row_index % 2 else PALE_BLUE))
            self.page.stroke_rect(LEFT, y_bottom, CONTENT_W, height, LINE, 0.5)
            x = LEFT
            for column_index, cell in enumerate(cells):
                if column_index:
                    self.page.line(x, y_bottom, x, y_bottom + height, LINE, 0.5)
                color = WHITE if row_index == 0 else INK
                font = "F2" if row_index == 0 or column_index == 0 else "F1"
                line_y = self.y - 8
                for line in cell:
                    self.page.text(x + 7, line_y, line, 8.1, font, color)
                    line_y -= 10.4
                x += widths[column_index]
            self.y -= height
        self.y -= 7

    def arrow(self, x1: float, y1: float, x2: float, y2: float, color=BLUE) -> None:
        self.page.line(x1, y1, x2, y2, color, 1.4)
        if abs(x2 - x1) >= abs(y2 - y1):
            direction = 1 if x2 > x1 else -1
            self.page.polygon([(x2, y2), (x2 - direction * 7, y2 + 4), (x2 - direction * 7, y2 - 4)], color)
        else:
            direction = 1 if y2 > y1 else -1
            self.page.polygon([(x2, y2), (x2 - 4, y2 - direction * 7), (x2 + 4, y2 - direction * 7)], color)

    def node(self, x: float, y: float, width: float, height: float, title: str, subtitle: str = "",
             fill=WHITE, stroke=LINE) -> None:
        self.page.fill_rect(x, y, width, height, fill)
        self.page.stroke_rect(x, y, width, height, stroke, 1.0)
        title_lines = wrap(title, width - 12, 8.1)
        ty = y + height - 14
        for line in title_lines[:2]:
            self.page.text(x + 6, ty, line, 8.1, "F2", NAVY)
            ty -= 10
        if subtitle:
            for line in wrap(subtitle, width - 12, 6.5)[:2]:
                self.page.text(x + 6, ty - 1, line, 6.5, "F1", MUTED)
                ty -= 8

    def diagram(self) -> None:
        self.diagram_index += 1
        height = 220 if self.diagram_index in {2, 3} else 168
        self.ensure(height + 12)
        x, top = LEFT, self.y
        y = top - height
        self.page.fill_rect(x, y, CONTENT_W, height, PALE_BLUE)
        self.page.stroke_rect(x, y, CONTENT_W, height, LINE)
        self.page.text(x + 14, top - 18, f"SYSTEM DIAGRAM {self.diagram_index}", 7.4, "F2", BLUE)
        if self.diagram_index == 1:
            labels = ["Private UI", "Media memory", "Local analysis", "Story evidence", "AI director", "Validated plan", "GPU render"]
            node_w, gap = 58, 9
            start_x = x + 14
            node_y = y + 69
            for index, label in enumerate(labels):
                nx = start_x + index * (node_w + gap)
                self.node(nx, node_y, node_w, 48, label, fill=WHITE)
                if index < len(labels) - 1:
                    self.arrow(nx + node_w, node_y + 24, nx + node_w + gap - 2, node_y + 24)
            self.node(x + 190, y + 12, 108, 34, "Review", "approve or revise", PALE_CYAN, CYAN)
            self.arrow(x + 433, node_y, x + 298, y + 46, CYAN)
        elif self.diagram_index == 2:
            panels = [
                ("PRIVATE ACCESS", ["Phone / computer", "Tailscale Serve", "Next.js interface"]),
                ("CONTROL PLANE", ["FastAPI", "PostgreSQL", "Redis signal"]),
                ("MEDIA PLANE", ["Resumable uploads", "Durable worker", "RTX 3050"]),
                ("EDITORIAL PLANE", ["Evidence", "AI director", "Validator + FFmpeg"]),
            ]
            panel_w = (CONTENT_W - 42) / 2
            panel_h = 74
            for index, (title, items) in enumerate(panels):
                px = x + 14 + (index % 2) * (panel_w + 14)
                py = y + 18 + (1 - index // 2) * 86
                self.page.fill_rect(px, py, panel_w, panel_h, WHITE)
                self.page.stroke_rect(px, py, panel_w, panel_h, CYAN)
                self.page.text(px + 10, py + panel_h - 16, title, 8, "F2", BLUE)
                for row, item in enumerate(items):
                    self.page.text(px + 12, py + panel_h - 31 - row * 12, f"- {item}", 7.5, "F1", INK)
        elif self.diagram_index == 3:
            states = ["Draft", "Upload", "Analyze", "Plan", "Preview", "Review", "Export", "Delivered"]
            node_w, gap = 47, 11
            sy = y + 126
            for index, state in enumerate(states):
                sx = x + 12 + index * (node_w + gap)
                self.node(sx, sy, node_w, 32, state, fill=WHITE)
                if index < len(states) - 1:
                    self.arrow(sx + node_w, sy + 16, sx + node_w + gap - 2, sy + 16)
            self.node(x + 115, y + 35, 92, 38, "Failed", "safe retry", (1.0, 0.95, 0.93), (0.75, 0.30, 0.22))
            self.node(x + 282, y + 35, 92, 38, "Revision", "new preview", PALE_CYAN, CYAN)
            self.arrow(x + 299, sy, x + 328, y + 73, CYAN)
            self.arrow(x + 282, y + 54, x + 264, sy, CYAN)
        elif self.diagram_index == 4:
            labels = [("Upload staging", 18), ("Read-only original", 122), ("Derived files", 235), ("Encrypted USB", 344), ("OneDrive mirror", 441)]
            for index, (label, offset) in enumerate(labels):
                self.node(x + offset, y + 76, 86, 46, label, fill=WHITE)
                if index < len(labels) - 1:
                    next_offset = labels[index + 1][1]
                    self.arrow(x + offset + 86, y + 99, x + next_offset - 3, y + 99)
            self.node(x + 177, y + 15, 132, 36, "PostgreSQL dump", fill=PALE_CYAN, stroke=CYAN)
            self.arrow(x + 243, y + 51, x + 387, y + 76, CYAN)
        elif self.diagram_index == 5:
            labels = [
                ("Whisper / CLIP / FFmpeg", "application process"),
                ("CUDA + cuDNN runtime", "inside the container"),
                ("NVIDIA Container Toolkit", "grants device access"),
                ("Ubuntu NVIDIA driver", "owns the hardware"),
                ("Physical RTX 3050", "CUDA + Tensor + NVENC + VRAM"),
            ]
            nw, nh = 230, 25
            nx = x + (CONTENT_W - nw) / 2
            for index, (title, subtitle) in enumerate(labels):
                ny = top - 43 - index * 29
                self.node(nx, ny, nw, nh, title, subtitle, WHITE if index < 4 else PALE_CYAN, CYAN)
                if index < len(labels) - 1:
                    self.arrow(nx + nw / 2, ny, nx + nw / 2, ny - 4, BLUE)
        else:
            labels = ["Tailnet identity", "Tailscale Serve", "Web permissions", "Private API", "PostgreSQL"]
            nw, gap = 77, 14
            ny = y + 83
            for index, label in enumerate(labels):
                nx = x + 16 + index * (nw + gap)
                self.node(nx, ny, nw, 42, label, fill=WHITE)
                if index < len(labels) - 1:
                    self.arrow(nx + nw, ny + 21, nx + nw + gap - 2, ny + 21)
            self.node(x + 164, y + 20, 160, 36, "Bounded model evidence", "no shell or storage paths", PALE_CYAN, CYAN)
        self.y -= height + 12

    def title_page(self) -> None:
        self.page.fill_rect(0, 0, PAGE_W, PAGE_H, NAVY)
        self.page.fill_rect(LEFT, PAGE_H - 178, 86, 6, CYAN)
        self.page.text(LEFT, PAGE_H - 122, "GM STUDIO", 12, "F2", CYAN)
        self.page.text(LEFT, PAGE_H - 216, "System Architecture", 30, "F2", WHITE)
        self.page.text(LEFT, PAGE_H - 253, "A visual guide to the editing appliance,", 16, "F1", WHITE)
        self.page.text(LEFT, PAGE_H - 276, "its AI workflow, and CUDA acceleration", 16, "F1", WHITE)
        self.page.fill_rect(LEFT, 174, CONTENT_W, 110, (0.09, 0.23, 0.36))
        self.page.text(LEFT + 18, 251, "MEMORY", 8, "F2", CYAN)
        self.page.text(LEFT + 18, 227, "BRAIN", 8, "F2", CYAN)
        self.page.text(LEFT + 18, 203, "HANDS", 8, "F2", CYAN)
        self.page.text(LEFT + 94, 251, "Media, transcripts, visual index, and project history", 9.5, "F1", WHITE)
        self.page.text(LEFT + 94, 227, "A bounded editorial model choosing the story", 9.5, "F1", WHITE)
        self.page.text(LEFT + 94, 203, "FFmpeg, local models, and the NVIDIA GPU", 9.5, "F1", WHITE)
        self.page.text(LEFT, 82, "Private by design  |  Source-led  |  Recoverable", 9, "F2", WHITE)
        self.new_page()
        self.page.text(LEFT, PAGE_H - 86, "How to read this guide", 22, "F2", NAVY)
        self.page.fill_rect(LEFT, PAGE_H - 98, 90, 4, CYAN)
        self.y = PAGE_H - 132
        self.paragraph("The first half explains GM Studio as a simple flow that is easy to share. The second half goes deeper into services, durable jobs, storage, security, and the exact role of CUDA and the NVIDIA GPU.")
        self.heading(2, "Contents")
        contents = [
            "The short explanation", "What happens to an uploaded video", "The main system areas",
            "Services and responsibilities", "The job lifecycle", "The evidence sent to the editorial brain",
            "The edit plan", "Storage and recovery", "CUDA and the GPU", "Phase 13 story intelligence",
        ]
        for index, item in enumerate(contents, 1):
            self.bullet(item, f"{index:02d}")
        self.new_page()

    def render_markdown(self, markdown: str) -> None:
        self.title_page()
        lines = markdown.splitlines()
        index = 1  # The title is supplied by the PDF cover.
        paragraph: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                self.paragraph(" ".join(part.strip() for part in paragraph))
                paragraph.clear()

        while index < len(lines):
            raw = lines[index]
            stripped = raw.strip()
            if stripped.startswith("```"):
                flush_paragraph()
                language = stripped[3:].strip()
                block: list[str] = []
                index += 1
                while index < len(lines) and not lines[index].strip().startswith("```"):
                    block.append(lines[index])
                    index += 1
                if language == "mermaid":
                    self.diagram()
                else:
                    self.code(block)
            elif stripped.startswith("#"):
                flush_paragraph()
                match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
                if match:
                    self.heading(len(match.group(1)), match.group(2))
            elif stripped.startswith("> "):
                flush_paragraph()
                self.quote(stripped[2:])
            elif re.match(r"^\d+\.\s+", stripped):
                flush_paragraph()
                match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
                assert match
                self.bullet(match.group(2), match.group(1))
            elif stripped.startswith("- "):
                flush_paragraph()
                self.bullet(stripped[2:])
            elif stripped.startswith("|"):
                flush_paragraph()
                rows: list[list[str]] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                        rows.append(cells)
                    index += 1
                self.table(rows)
                continue
            elif not stripped:
                flush_paragraph()
            else:
                paragraph.append(stripped)
            index += 1
        flush_paragraph()

    def save(self, path: Path) -> None:
        total = len(self.pages)
        for number, page in enumerate(self.pages, 1):
            if number == 1:
                continue
            page.line(LEFT, 35, PAGE_W - RIGHT, 35, LINE, 0.5)
            page.text(LEFT, 21, "GM Studio System Architecture", 7.2, "F1", MUTED)
            page.text(PAGE_W - RIGHT - 34, 21, f"{number} / {total}", 7.2, "F2", MUTED)

        objects: list[bytes] = []

        def add(payload: str | bytes) -> int:
            objects.append(payload.encode("latin-1") if isinstance(payload, str) else payload)
            return len(objects)

        catalog_id = add("")
        pages_id = add("")
        font_regular = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font_bold = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        font_oblique = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>")
        font_mono = add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
        page_ids: list[int] = []
        for page in self.pages:
            stream = ("\n".join(page.commands) + "\n").encode("latin-1")
            stream_id = add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream")
            page_id = add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R /F3 {font_oblique} 0 R /F4 {font_mono} 0 R >> >> "
                f"/Contents {stream_id} 0 R >>"
            )
            page_ids.append(page_id)
        objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
        ).encode()

        header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        output = bytearray(header)
        offsets = [0]
        for object_id, payload in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode())
            output.extend(payload)
            output.extend(b"\nendobj\n")
        xref = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode())
        output.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        )
        path.write_bytes(output)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "docs" / "system-architecture-guide.md"
    destination = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "docs" / "GM-Studio-System-Architecture-Guide.pdf"
    guide = PdfGuide()
    guide.render_markdown(source.read_text(encoding="utf-8"))
    guide.save(destination)
    print(f"Created {destination} ({len(guide.pages)} pages, {destination.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
