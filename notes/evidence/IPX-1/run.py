# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""IPX-1 (#152): each fixture's validity against the official IP-XACT 2022 XSD, then
topwrap_ipxact_parser's parse and export of it: whether the export is still valid and whether
it equals the input once both are canonical (comments and blank text dropped).

    python run.py <official XSD dir> <fixtures dir> > results.json
"""
import contextlib, difflib, io, json, re, sys
from pathlib import Path
import lxml.etree as ET
import xmlschema
import topwrap_ipxact_parser as tp

XSD = xmlschema.XMLSchema(str(Path(sys.argv[1]) / "index.xsd"))
FIXTURES = Path(sys.argv[2])

def canon(xml_bytes):
    parser = ET.XMLParser(remove_blank_text=True, remove_comments=True)
    root = ET.fromstring(xml_bytes, parser)
    for el in root.iter():
        if el.text is not None and not el.text.strip():
            el.text = None
        elif el.text is not None:
            el.text = el.text.strip()
        el.tail = None
    return ET.tostring(root, method="c14n2")

def export(obj, root_tag="component"):
    buf = io.StringIO()
    obj.export(buf, 0, name_=root_tag, namespaceprefix_="ipxact:",
               namespacedef_='xmlns:ipxact="http://www.accellera.org/XMLSchema/IPXACT/1685-2022"')
    return buf.getvalue().encode()

def lines(xml_bytes):
    return [l for l in re.sub(rb"><", b">\n<", canon(xml_bytes)).decode().splitlines()]


def run(path):
    raw = path.read_bytes()
    row = {"fixture": path.name, "xsd_valid": XSD.is_valid(str(path))}
    errs = [e.reason for e in XSD.iter_errors(str(path))][:1]
    row["xsd_error"] = errs[0][:160] if errs else ""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            obj = tp.parseString(raw, silence=True, print_warnings=True)
        row["parsed"] = obj is not None
        # the bindings report problems on stdout or stderr, never as exceptions
        row["parse_messages"] = [m for m in (out.getvalue() + err.getvalue()).splitlines()
                                 if m.strip()][:3]
    except Exception as exc:
        row.update(parsed=False, parse_error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return row, None
    try:
        exported = export(obj)
        row["export_xsd_valid"] = XSD.is_valid(exported.decode())
        row["roundtrip_equal"] = canon(raw) == canon(exported)
        if not row["roundtrip_equal"]:
            diff = [d for d in difflib.unified_diff(lines(raw), lines(exported), lineterm="", n=0)
                    if d[:1] in "+-" and d[:3] not in ("---", "+++")]
            row["removed"] = [d[1:] for d in diff if d[0] == "-"][:8]
            row["added"] = [d[1:] for d in diff if d[0] == "+"][:8]
    except Exception as exc:
        row.update(export_error=f"{type(exc).__name__}: {str(exc)[:160]}")
        exported = None
    return row, (obj, exported)


if __name__ == "__main__":
    rows = []
    for p in sorted(FIXTURES.glob("*.xml")):
        row, extra = run(p)
        rows.append(row)
    print(json.dumps(rows, indent=1))
