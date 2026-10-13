# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Optional, bounded PDF evidence extraction for the resolver."""

import re
import shutil
import subprocess
import tempfile

import resolve
import speccheck


class PdfPages:
    """Cache only requested pages; never interpret printed page numbers."""

    def __init__(self, path, timeout, limit):
        self.path = path
        self.timeout = timeout
        self.limit = limit
        self.cache = {}
        self.size = 0

    def page(self, number):
        if number in self.cache:
            value = self.cache[number]
            if isinstance(value, resolve.ResolutionError):
                raise value
            return value
        try:
            value = self.extract(number)
        except resolve.ResolutionError as exc:
            self.cache[number] = exc
            raise
        self.cache[number] = value
        return value

    def extract(self, number):
        executable = shutil.which("pdftotext")
        if executable is None:
            raise resolve.LimitExceeded("pdftotext unavailable")
        try:
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                proc = subprocess.run(
                    [
                        executable,
                        "-f",
                        str(number),
                        "-l",
                        str(number),
                        "-layout",
                        "-enc",
                        "UTF-8",
                        str(self.path.resolve()),
                        "-",
                    ],
                    stdout=out,
                    stderr=err,
                    timeout=self.timeout,
                    check=False,
                )
                if proc.returncode:
                    err.seek(0)
                    reason = err.read(1024).decode("utf-8", errors="replace").strip()
                    raise resolve.ResolutionError(f"PDF extraction failed: {reason}")
                if self.size + out.tell() > self.limit:
                    raise resolve.LimitExceeded("PDF text size limit exceeded")
                self.size += out.tell()
                out.seek(0)
                return out.read().decode("utf-8", errors="replace").splitlines()
        except subprocess.TimeoutExpired as exc:
            raise resolve.LimitExceeded("PDF extraction time limit exceeded") from exc
        except OSError as exc:
            raise resolve.ResolutionError(f"cannot run pdftotext: {exc}") from exc


def locator_pattern(kind, value):
    """Match complete locator tokens, allowing PDF whitespace in captions."""
    label = f"{kind} " if kind in ("table", "figure") else ""
    token = r"\s+".join(re.escape(part) for part in (label + value).split())
    return re.compile(r"(?<![\w.])" + token + r"(?![\w.]|[-–]\d)", re.I)


def citations(record, base, documents, add):
    """Return document citations and only the owner's directly cited text."""
    items, own_lines = [], []
    for support, at in speccheck.supports(record, base):
        if support.get("class") not in speccheck.DOC_CLASS:
            continue
        name = support["doc"]
        for index, locator in enumerate(support.get("at", [])):
            where = at + ("at", index)
            item = dict(
                doc=name, locator=locator, fact=record["id"], status="failed", source=[]
            )
            items.append(item)
            doc, reader = documents.get(name, ({}, "document is not declared"))
            try:
                if isinstance(reader, resolve.ResolutionError):
                    raise reader
                if isinstance(reader, str):
                    raise resolve.LimitExceeded(reader)
                if doc.get("page_numbering") != "pdf":
                    raise resolve.LimitExceeded("page_numbering is not pdf")
                bounds = locator.get("pages", [locator.get("page")] * 2)
                if not all(
                    isinstance(p, str) and p.isascii() and p.isdecimal() for p in bounds
                ):
                    raise resolve.LimitExceeded("locator needs numeric PDF page(s)")
                normalized = [p.lstrip("0") or "0" for p in bounds]
                if any(
                    len(p) > 10 or (len(p) == 10 and p > "2147483647")
                    for p in normalized
                ):
                    raise resolve.ResolutionError(
                        "PDF page exceeds extractor integer range"
                    )
                first, last = map(int, normalized)
                count = doc.get("pages")
                if not 1 <= first <= last or (count is not None and last > count):
                    raise resolve.ResolutionError(
                        "PDF page range outside declared pages"
                    )
                lines = []
                for page in range(first, last + 1):
                    page_lines = reader.page(page)
                    item["source"].extend(
                        (page, n, line) for n, line in enumerate(page_lines, 1)
                    )
                    lines.extend(page_lines)
                if not any(line.strip() for line in lines):
                    raise resolve.LimitExceeded(
                        "cited PDF pages have no extractable text"
                    )
                text = "\n".join(lines)
                for kind in ("section", "table", "figure"):
                    if kind not in locator:
                        continue
                    pattern = locator_pattern(kind, locator[kind])
                    if pattern.search(text):
                        continue
                    nearby = []
                    for page in (first - 1, last + 1):
                        if page < 1 or (count is not None and page > count):
                            continue
                        try:
                            if pattern.search("\n".join(reader.page(page))):
                                nearby.append(str(page))
                        except resolve.ResolutionError:
                            pass
                    suffix = (
                        "; found on adjacent PDF page(s): " + ", ".join(nearby)
                        if nearby
                        else ""
                    )
                    add(
                        where + (kind,),
                        f"{record['id']}: {name}: {kind} "
                        f"{locator[kind]!r} absent from cited PDF pages{suffix}",
                        "warning",
                    )
                item["status"] = "resolved"
                if at[:-1] == base + ("support",):
                    own_lines.extend(lines)
            except resolve.LimitExceeded as exc:
                item["status"] = "skipped"
                add(
                    where,
                    f"{record['id']}: {name}: PDF evidence skipped: {exc}",
                    "warning",
                )
            except resolve.ResolutionError as exc:
                add(where, f"{record['id']}: {name}: {exc}")
    return items, own_lines
