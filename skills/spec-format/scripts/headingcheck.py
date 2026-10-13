# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Opt-in network checks for cited GitHub heading locators."""

import explorer
import speccheck


def check(checker):
    """Reuse explorer fetches, then warn at each unresolved citation's YAML location.

    A clean structural check is required before requesting document URLs. Context
    roots are inputs for references, not targets of this optional network check.
    Unsupported URLs and request failures do not establish an absent heading.
    """
    if any(f.level == "error" for f in checker.findings):
        return
    # Reuse the explorer's request limits and token/redirect policy unchanged.
    resolved = explorer.resolve_anchors(checker, get=explorer._get)  # pylint: disable=protected-access
    unresolved = {
        (item["url"], item["heading"]): item["reason"]
        for item in resolved["unresolved"]
    }
    for file in checker.files:
        if file.root.context:
            continue
        for record in file.records.values():
            for support, at in speccheck.supports(record.data, record.path):
                doc = file.documents.get(support.get("doc"), (None,))[0]
                if doc is None:
                    continue
                for index, locator in enumerate(support.get("at", [])):
                    if "heading" not in locator:
                        continue
                    heading = locator["heading"]
                    reason = unresolved.get((doc["url"], heading))
                    if explorer.fetch_url(doc["url"]) is None:
                        reason = (
                            "unsupported document URL "
                            "(needs a full-commit GitHub blob or wiki page)"
                        )
                    if reason is not None:
                        checker.add(
                            file,
                            at + ("at", index, "heading"),
                            f"{record.id}: heading {heading!r}: {reason}",
                            level="warning",
                        )
