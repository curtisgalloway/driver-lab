# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Argument errors that preserve the calling command's JSON response shape."""

import argparse
import json
import sys


class Parser(argparse.ArgumentParser):
    """Keep normal argparse help; emit structured usage failures for --json."""

    def __init__(self, *, error_fields=None, **kwargs):
        super().__init__(**kwargs)
        self.error_fields = error_fields or {}
        self.json_requested = False

    def parse_args(self, args=None, namespace=None):
        args = list(sys.argv[1:] if args is None else args)
        self.json_requested = "--json" in args
        return super().parse_args(args, namespace)

    def error(self, message):
        if self.json_requested:
            print(
                json.dumps(
                    dict(self.error_fields, ok=False, findings=[message]),
                    sort_keys=True,
                )
            )
            self.exit(2)
        super().error(message)
