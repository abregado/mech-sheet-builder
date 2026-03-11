#!/usr/bin/env python3
"""
Builds an A4 landscape printable SVG by placing header-row.svg once at the
top-left at its natural size, then stacking mech-row.svg elements (also at
natural size, left-aligned) until the page height is filled.

Output: sheet.svg
"""

import copy
import json
import math
import xml.etree.ElementTree as ET

# A4 landscape
A4_W_MM = 297.0
A4_H_MM = 210.0

HEADER_SVG   = "header-row.svg"
ROW_SVG      = "mech-row.svg"
OUTPUT_SVG   = "sheet.svg"
SETTINGS_JSON = "settings.json"

SVG_NS = "http://www.w3.org/2000/svg"

# Register namespaces to preserve prefixes on round-trip
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
    """Convert an SVG dimension string to millimetres."""
    v = value.strip()
    if v.endswith("mm"):
        return float(v[:-2])
    if v.endswith("px"):
        return float(v[:-2]) * (25.4 / 96)   # 96 dpi
    if v.endswith("pt"):
        return float(v[:-2]) * (25.4 / 72)
    return float(v)  # assume mm (Inkscape default)


def svg_dims_mm(root: ET.Element) -> tuple[float, float]:
    return parse_mm(root.get("width", "0")), parse_mm(root.get("height", "0"))


def embed(parent: ET.Element, src: ET.Element,
          x: float, y: float) -> None:
    """
    Nest src's content inside a <svg> child of parent at natural size,
    positioned at (x mm, y mm). The source width/height and viewBox are
    carried through unchanged so there is no scaling.
    """
    vb = src.get("viewBox") or src.get("viewbox")
    w  = src.get("width",  "0")
    h  = src.get("height", "0")
    node = ET.SubElement(parent, f"{{{SVG_NS}}}svg")
    node.set("x",      f"{x}mm")
    node.set("y",      f"{y}mm")
    node.set("width",  w)
    node.set("height", h)
    if vb:
        node.set("viewBox", vb)
    for child in src:
        if child.tag not in SKIP_TAGS:
            node.append(copy.deepcopy(child))


def main():
    with open(SETTINGS_JSON) as f:
        settings = json.load(f)
    row_spacing = float(settings["row_spacing_mm"])

    header_root = ET.parse(HEADER_SVG).getroot()
    row_root    = ET.parse(ROW_SVG).getroot()

    _, hh = svg_dims_mm(header_root)
    _, rh = svg_dims_mm(row_root)

    # How many rows fit, accounting for spacing between them
    num_rows = math.floor((A4_H_MM - hh) / (rh + row_spacing))

    total_h = hh + num_rows * rh + max(0, num_rows - 1) * row_spacing

    print(f"Row spacing:   {row_spacing:.3f} mm  (from {SETTINGS_JSON})")
    print(f"Header height: {hh:.3f} mm")
    print(f"Row height:    {rh:.3f} mm")
    print(f"Rows that fit: {num_rows}")
    print(f"Used height:   {total_h:.3f} mm  (page = {A4_H_MM} mm)")

    # --- Compose output SVG ---
    # SVG size matches actual content, not the full A4 page
    svg_w = A4_W_MM
    svg_h = total_h

    page = ET.Element(f"{{{SVG_NS}}}svg")
    page.set("xmlns",   SVG_NS)
    page.set("version", "1.1")
    page.set("width",   f"{svg_w}mm")
    page.set("height",  f"{svg_h}mm")
    page.set("viewBox", f"0 0 {svg_w} {svg_h}")

    # White background
    bg = ET.SubElement(page, f"{{{SVG_NS}}}rect")
    bg.set("x", "0"); bg.set("y", "0")
    bg.set("width",  f"{svg_w}mm")
    bg.set("height", f"{svg_h}mm")
    bg.set("fill",   "white")

    embed(page, header_root, 0, 0)

    y = hh
    for i in range(num_rows):
        embed(page, row_root, 0, y)
        y += rh + row_spacing

    tree = ET.ElementTree(page)
    ET.indent(tree, space="  ")
    tree.write(OUTPUT_SVG,
               xml_declaration=True,
               encoding="UTF-8",
               short_empty_elements=True)
    print(f"\nWritten: {OUTPUT_SVG}")


if __name__ == "__main__":
    main()
