#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Print the private run store's location, or a run's directory within it.

Usage: run-store.py [RUN_ID]

The location is each user's own setting, never recorded in this repository:
  1. the DRIVER_LAB_RUNS environment variable, if set; otherwise
  2. `run_store` in $XDG_CONFIG_HOME/driver-lab/config.toml
     (XDG_CONFIG_HOME defaults to ~/.config).

Exit status: 0 printed the path; 1 no location is configured or it is not a directory.
"""
import os
import pathlib
import sys
import tomllib


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config"
    return pathlib.Path(base) / "driver-lab" / "config.toml"


def run_store():
    env = os.environ.get("DRIVER_LAB_RUNS")
    if env:
        return pathlib.Path(env).expanduser(), "DRIVER_LAB_RUNS"
    cfg = config_path()
    if cfg.is_file():
        with cfg.open("rb") as f:
            value = tomllib.load(f).get("run_store")
        if value:
            return pathlib.Path(value).expanduser(), str(cfg)
    return None, str(cfg)


def main():
    path, source = run_store()
    if path is None:
        print(f"run store not configured: set run_store in {source} "
              "or DRIVER_LAB_RUNS", file=sys.stderr)
        return 1
    if not path.is_dir():
        print(f"run store {path} (from {source}) is not a directory", file=sys.stderr)
        return 1
    if len(sys.argv) > 1:
        path = path / sys.argv[1]
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
