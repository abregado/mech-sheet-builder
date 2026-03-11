#!/usr/bin/env python3
"""
For every CSV file in the current directory, produces one output SVG:
  - header-row.svg placed once at the top-left at natural size
  - one mech-row.svg per CSV data row, stacked below, left-aligned
  - text from each CSV column injected into each row at positions
    defined in settings.json under "columns"
  - rows spaced by settings.json "row_spacing_mm"
  - output SVG sized to fit the actual content

settings.json keys:
  row_spacing_mm  – gap between mech rows (mm)
  columns         – map of CSV column name → {
                      "x": <mm>, "y": <mm>,
                      "font_size": <number>          (default 3),
                      "align": "left"|"centre"|"right"  (default "left"),
                      "replace_underscores": true|false  (default false)
                    }
                    coordinates are in mech-row.svg viewBox space

Output files are named after the CSV (e.g. mission.csv → mission.svg).
"""

import copy
import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

# A4 landscape – used only to cap the number of rows
A4_H_MM = 210.0

HEADER_SVG    = "header-row.svg"
ROW_SVG       = "mech-row.svg"
SETTINGS_JSON = "settings.json"

SVG_NS = "http://www.w3.org/2000/svg"

for prefix, uri in [
    ("",         SVG_NS),
    ("xlink",    "http://www.w3.org/1999/xlink"),
    ("dc",       "http://purl.org/dc/elements/1.1/"),
    ("cc",       "http://creativecommons.org/ns#"),
    ("rdf",      "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"),
    ("inkscape", "http://www.inkscape.org/namespaces/inkscape"),
]:
    ET.register_namespace(prefix, uri)

SKIP_TAGS = {
    "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}namedview",
    "{http://www.w3.org/2000/svg}metadata",
}


def parse_mm(value: str) -> float:
    v = value.strip()
    if v.endswith("mm"):
        return float(v[:-2])
    if v.endswith("px"):
        return float(v[:-2]) * (25.4 / 96)
    if v.endswith("pt"):
        return float(v[:-2]) * (25.4 / 72)
    return float(v)


def svg_dims_mm(root: ET.Element) -> tuple[float, float]:
    return parse_mm(root.get("width", "0")), parse_mm(root.get("height", "0"))


def embed(parent: ET.Element, src: ET.Element, x: float, y: float) -> ET.Element:
    """
    Nest src's children inside a new <svg> at (x mm, y mm) at natural size.
    Returns the new <svg> element so callers can append additional children.
    """
    vb = src.get("viewBox") or src.get("viewbox")
    node = ET.SubElement(parent, f"{{{SVG_NS}}}svg")
    node.set("x",      f"{x}mm")
    node.set("y",      f"{y}mm")
    node.set("width",  src.get("width",  "0"))
    node.set("height", src.get("height", "0"))
    if vb:
        node.set("viewBox", vb)
    for child in src:
        if child.tag not in SKIP_TAGS:
            node.append(copy.deepcopy(child))
    return node


ALIGN_TO_ANCHOR = {"left": "start", "centre": "middle", "right": "end"}


def add_text(parent: ET.Element, text: str, x: float, y: float,
             font_size: float = 3.0, align: str = "left",
             replace_underscores: bool = False) -> None:
    """Append a <text> element at (x, y) in the parent's coordinate space."""
    if replace_underscores:
        text = text.replace("_", ", ")
    el = ET.SubElement(parent, f"{{{SVG_NS}}}text")
    el.set("x", str(x))
    el.set("y", str(y))
    el.set("font-size", str(font_size))
    el.set("font-family", "sans-serif")
    el.set("text-anchor", ALIGN_TO_ANCHOR.get(align, "start"))
    el.text = text


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows) from a CSV, skipping blank rows."""
    with csv_path.open(newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [row for row in reader if any(v.strip() for v in row.values())]
    return headers, rows


def build_sheet(csv_path: Path, header_root: ET.Element, row_root: ET.Element,
                row_spacing: float, col_settings: dict) -> None:
    headers, data_rows = read_csv_rows(csv_path)

    _, hh = svg_dims_mm(header_root)
    _, rh = svg_dims_mm(row_root)

    # Total slots the page can hold
    max_rows  = math.floor((A4_H_MM - hh) / (rh + row_spacing))
    data_rows = data_rows[:max_rows]

    svg_w = max(parse_mm(header_root.get("width", "0")),
                parse_mm(row_root.get("width", "0")))
    svg_h = A4_H_MM

    page = ET.Element(f"{{{SVG_NS}}}svg")
    page.set("xmlns",   SVG_NS)
    page.set("version", "1.1")
    page.set("width",   f"{svg_w}mm")
    page.set("height",  f"{svg_h}mm")
    page.set("viewBox", f"0 0 {svg_w} {svg_h}")

    bg = ET.SubElement(page, f"{{{SVG_NS}}}rect")
    bg.set("x", "0"); bg.set("y", "0")
    bg.set("width",  f"{svg_w}mm")
    bg.set("height", f"{svg_h}mm")
    bg.set("fill",   "white")

    embed(page, header_root, 0, 0)

    y = hh
    for i in range(max_rows):
        row_node = embed(page, row_root, 0, y)

        if i < len(data_rows):
            # Inject CSV values as new text elements inside this row's <svg>
            for col_name, pos in col_settings.items():
                value = data_rows[i].get(col_name, "").strip()
                if value:
                    add_text(row_node, value,
                             pos["x"], pos["y"],
                             font_size=pos.get("font_size", 3.0),
                             align=pos.get("align", "left"),
                             replace_underscores=pos.get("replace_underscores", False))

        y += rh + row_spacing

    out_path = csv_path.with_suffix(".svg")
    tree = ET.ElementTree(page)
    ET.indent(tree, space="  ")
    tree.write(str(out_path),
               xml_declaration=True,
               encoding="UTF-8",
               short_empty_elements=True)

    print(f"  {csv_path.name} -> {out_path.name}  "
          f"({len(data_rows)} data + {max_rows - len(data_rows)} empty = {max_rows} rows)")


def main():
    with open(SETTINGS_JSON, encoding="utf-8") as f:
        settings = json.load(f)

    row_spacing  = float(settings["row_spacing_mm"])
    col_settings = settings.get("columns", {})

    header_root = ET.parse(HEADER_SVG).getroot()
    row_root    = ET.parse(ROW_SVG).getroot()

    csv_files = sorted(Path(".").glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    print(f"Row spacing: {row_spacing} mm | Columns mapped: {list(col_settings)}\n")
    for csv_path in csv_files:
        build_sheet(csv_path, header_root, row_root, row_spacing, col_settings)


if __name__ == "__main__":
    main()
