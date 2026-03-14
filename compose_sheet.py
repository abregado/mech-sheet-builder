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
ARMOR_SVG     = "armor-square.svg"
STRUCTURE_SVG = "structure-square.svg"
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
    Uses unitless coordinate values so renderers don't apply mm-to-user-unit
    conversion (which would scale content ~3.78× when parent 1 unit = 1 mm).
    Returns the new <svg> element so callers can append additional children.
    """
    vb = src.get("viewBox") or src.get("viewbox")
    w, h = svg_dims_mm(src)
    node = ET.SubElement(parent, f"{{{SVG_NS}}}svg")
    node.set("x",      str(x))   # unitless parent user units (= mm)
    node.set("y",      str(y))   # unitless parent user units (= mm)
    node.set("width",  str(w))   # unitless parent user units (= mm)
    node.set("height", str(h))   # unitless parent user units (= mm)
    if vb:
        node.set("viewBox", vb)
    node.set("overflow", "visible")
    for child in src:
        if child.tag not in SKIP_TAGS:
            node.append(copy.deepcopy(child))
    return node


ALIGN_TO_ANCHOR = {"left": "start", "centre": "middle", "right": "end"}


def add_text(parent: ET.Element, text: str, x: float, y: float,
             font_size: float = 3.0, align: str = "left",
             replace_underscores: bool = False,
             font_family: str = "sans-serif") -> None:
    """Append a <text> element at (x, y) in the parent's coordinate space."""
    if replace_underscores:
        text = text.replace("_", ", ")
    el = ET.SubElement(parent, f"{{{SVG_NS}}}text")
    el.set("x", str(x))
    el.set("y", str(y))
    el.set("font-size", str(font_size))
    el.set("font-family", font_family)
    el.set("text-anchor", ALIGN_TO_ANCHOR.get(align, "start"))
    el.text = text


def place_boxes(parent: ET.Element, box_root: ET.Element,
                count: int, x_start: float, y: float, gap: float) -> None:
    """Place `count` copies of box_root in a horizontal strip inside parent.

    Positions and sizes are in user units (= mm for the mech-row viewBox).
    Using unitless values avoids SVG viewport-relative unit resolution that
    can cause apparent scaling errors inside nested <svg> elements.
    """
    bw, bh = svg_dims_mm(box_root)
    vb = box_root.get("viewBox") or box_root.get("viewbox")
    x = x_start
    for _ in range(count):
        node = ET.SubElement(parent, f"{{{SVG_NS}}}svg")
        node.set("x",      str(x))   # unitless user units
        node.set("y",      str(y))   # unitless user units
        node.set("width",  str(bw))  # unitless user units
        node.set("height", str(bh))  # unitless user units
        if vb:
            node.set("viewBox", vb)
        for child in box_root:
            if child.tag not in SKIP_TAGS:
                node.append(copy.deepcopy(child))
        x += bw + gap


def mission_name_from_path(csv_path: Path) -> str:
    """Derive a readable mission name from the CSV filename.
    Replaces dashes/underscores with spaces and title-cases each word.
    Numbers are kept as-is.  e.g. '01-mission-name.csv' -> '01 Mission Name'
    """
    return csv_path.stem.replace("-", " ").replace("_", " ").title()


def clean(value: str) -> str:
    """Strip whitespace and quote characters from a CSV field value."""
    return value.strip().replace('"', '').replace('\u201c', '').replace('\u201d', '')


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows) from a CSV, skipping blank rows."""
    with csv_path.open(newline="", encoding="cp1252") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = [row for row in reader if any(v.strip() for v in row.values())]
    return headers, rows


def build_sheet(csv_path: Path, header_root: ET.Element, row_root: ET.Element,
                armor_root: ET.Element, structure_root: ET.Element,
                row_spacing: float, header_spacing: float,
                col_settings: dict, box_settings: dict,
                mission_name_settings: dict, font_family: str) -> None:
    headers, data_rows = read_csv_rows(csv_path)

    _, hh = svg_dims_mm(header_root)
    _, rh = svg_dims_mm(row_root)

    # Total slots the page can hold (header + spacing + rows)
    max_rows  = math.floor((A4_H_MM - hh - header_spacing) / (rh + row_spacing))
    data_rows = data_rows[:max_rows]

    svg_w = max(parse_mm(header_root.get("width", "0")),
                parse_mm(row_root.get("width", "0")))
    svg_h = A4_H_MM

    page = ET.Element(f"{{{SVG_NS}}}svg")
    page.set("version", "1.1")
    page.set("width",   f"{svg_w}mm")
    page.set("height",  f"{svg_h}mm")
    page.set("viewBox", f"0 0 {svg_w} {svg_h}")

    bg = ET.SubElement(page, f"{{{SVG_NS}}}rect")
    bg.set("x", "0"); bg.set("y", "0")
    bg.set("width",  str(svg_w))
    bg.set("height", str(svg_h))
    bg.set("fill",   "white")

    embed(page, header_root, 0, 0)

    # Mission name overlaid on the header
    mn = mission_name_settings
    add_text(page, mission_name_from_path(csv_path),
             mn["x"], mn["y"],
             font_size=mn.get("font_size", 6),
             align=mn.get("align", "left"),
             font_family=font_family)

    x_start  = box_settings["x_start"]
    armor_y  = box_settings["armor_y"]
    struct_y = box_settings["structure_y"]
    gap      = box_settings.get("gap", 0.5)

    y = hh + header_spacing
    for i in range(max_rows):
        row_node = embed(page, row_root, 0, y)

        if i < len(data_rows):
            row = data_rows[i]

            # Inject CSV values as new text elements inside this row's <svg>
            for col_name, pos in col_settings.items():
                value = clean(row.get(col_name, ""))
                if value:
                    add_text(row_node, value,
                             pos["x"], pos["y"],
                             font_size=pos.get("font_size", 3.0),
                             align=pos.get("align", "left"),
                             replace_underscores=pos.get("replace_underscores", False),
                             font_family=font_family)

            try:
                armor_count = int(clean(row.get("Armor", "0")))
            except ValueError:
                armor_count = 0
            try:
                structure_count = int(clean(row.get("Structure", "0")))
            except ValueError:
                structure_count = 0
        else:
            armor_count     = 10
            structure_count = 10

        place_boxes(row_node, armor_root,     armor_count,     x_start, armor_y,  gap)
        place_boxes(row_node, structure_root, structure_count, x_start, struct_y, gap)

        y += rh + row_spacing

    out_path = Path("output") / csv_path.with_suffix(".svg").name
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

    font_family    = settings.get("font_family", "sans-serif")
    row_spacing    = float(settings["row_spacing_mm"])
    header_spacing = float(settings.get("header_spacing_mm", 0.0))
    col_settings   = settings.get("columns", {})
    box_settings   = settings.get("boxes", {})
    mn_settings    = settings.get("mission_name", {})

    header_root    = ET.parse(HEADER_SVG).getroot()
    row_root       = ET.parse(ROW_SVG).getroot()
    armor_root     = ET.parse(ARMOR_SVG).getroot()
    structure_root = ET.parse(STRUCTURE_SVG).getroot()

    Path("output").mkdir(exist_ok=True)
    csv_files = sorted(Path("data").glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    print(f"Row spacing: {row_spacing} mm | Columns mapped: {list(col_settings)}\n")
    for csv_path in csv_files:
        build_sheet(csv_path, header_root, row_root, armor_root, structure_root,
                    row_spacing, header_spacing, col_settings, box_settings,
                    mn_settings, font_family)


if __name__ == "__main__":
    main()
