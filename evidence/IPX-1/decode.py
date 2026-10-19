# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""IPX-1 (#152): what the bindings lose, set beside xmlschema's schema-driven decode of the same
fixtures. Each check reads both sides, so either can fail.

    python decode.py <official XSD dir> <fixtures dir>
"""
import json
import sys
from pathlib import Path

import lxml.etree as ET
import topwrap_ipxact_parser as tp
import xmlschema

XSD = xmlschema.XMLSchema(str(Path(sys.argv[1]) / "index.xsd"))
FX = Path(sys.argv[2])
NS = "{http://www.accellera.org/XMLSchema/IPXACT/1685-2022}"


def many(v):
    return v if isinstance(v, list) else [] if v is None else [v]


def one(v):
    return many(v)[0]


def decoded(name, **kw):
    return XSD.to_dict(str(FX / name), use_defaults=False, **kw)


def block(d):
    return one(one(d["ipxact:memoryMaps"]["ipxact:memoryMap"])["ipxact:addressBlock"])


def bindings_block(name):
    obj = tp.parseString((FX / name).read_bytes(), silence=True)
    return obj.memoryMaps.memoryMap[0].addressBlock[0]


def source_order(name):
    root = ET.parse(str(FX / name)).getroot()
    blk = root.find(f".//{NS}addressBlock")
    return [(c.tag.replace(NS, ""), c.findtext(f"{NS}name")) for c in blk
            if c.tag in (f"{NS}register", f"{NS}registerFile")]


def attributes(node, out):
    """Every non-namespace attribute in a decoded tree, as (name, value)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.startswith("@") and not k.startswith("@xmlns"):
                out.append((k[1:], str(v).lower() if isinstance(v, bool) else str(v)))
            else:
                attributes(v, out)
    elif isinstance(node, list):
        for v in node:
            attributes(v, out)
    return out


def source_attributes(name):
    root = ET.parse(str(FX / name)).getroot()
    return sorted((ET.QName(k).localname, v) for el in root.iter() for k, v in el.attrib.items()
                  if not k.startswith("{http://www.w3.org/2001/XMLSchema-instance}"))


out = {}
ab = block(decoded("full.xml"))
out["registers in full.xml"] = {
    "source": [n for t, n in source_order("full.xml") if t == "register"],
    "xmlschema": [r["ipxact:name"] for r in many(ab["ipxact:register"])],
    "bindings": [r.name for r in many(bindings_block("full.xml").register)],
}
rf = bindings_block("full.xml").registerFile
out["registers in full.xml's register file"] = {
    "xmlschema": [r["ipxact:name"] for r in many(one(ab["ipxact:registerFile"])["ipxact:register"])],
    # generateDS turned the registerData group into an element: <register> children are skipped
    "bindings registerData": [repr(x) for x in many(rf.registerData)],
}
blk = block(decoded("two-register-files.xml"))
out["register files in two-register-files.xml"] = {
    "xmlschema": [f["ipxact:name"] for f in many(blk["ipxact:registerFile"])],
    "bindings": [f.name for f in many(bindings_block("two-register-files.xml").registerFile)],
}
out["register and register-file order in mixed-order.xml"] = {
    "source": source_order("mixed-order.xml"),
    "bindings": [("register", r.name) for r in many(bindings_block("mixed-order.xml").register)]
                + [("registerFile", f.name)
                   for f in many(bindings_block("mixed-order.xml").registerFile)],
}
field = one(one(block(decoded("explicit-properties.xml"))["ipxact:register"])["ipxact:field"])
out["explicit volatile false"] = {"xmlschema": field.get("ipxact:volatile")}
policy = one(one(one(block(decoded("access-policies.xml"))["ipxact:register"])["ipxact:field"])
             ["ipxact:fieldAccessPolicies"]["ipxact:fieldAccessPolicy"])
bpol = many(bindings_block("access-policies.xml").register.field)[0] \
    .fieldAccessPolicies.fieldAccessPolicy[0]
out["access policy"] = {
    "xmlschema keys": sorted(policy),
    "bindings reserved right after parse": getattr(bpol, "reserved", None),
}
attrs = {}
for p in sorted(FX.glob("*.xml")):
    if not XSD.is_valid(str(p)):
        continue
    src = source_attributes(p.name)
    dflt = sorted(attributes(XSD.to_dict(str(p)), []))
    nodflt = sorted(attributes(decoded(p.name), []))
    if dflt != src or nodflt != src:
        attrs[p.name] = {"source": src,
                         "added by to_dict defaults": sorted(set(dflt) - set(src)),
                         "differs with use_defaults=False": nodflt != src}
out["attributes: decoded versus source (fixtures that differ)"] = attrs
out["schema-invalid fixtures the decoder refuses"] = sorted(
    p.name for p in FX.glob("bad-*.xml") if not XSD.is_valid(str(p)))
print(json.dumps(out, indent=1, default=str))
