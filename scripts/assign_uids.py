#!/usr/bin/env python3
"""
为清洗后的数据批量补 uid（支持 JSON 列表与 JSONL）。

默认处理:
  data/processed_data/strategies.json
  data/processed_data/knowledge_rag.jsonl
  data/processed_data/chat_samples.jsonl

用法:
  python scripts/assign_uids.py
  python scripts/assign_uids.py --inplace
  python scripts/assign_uids.py --dir data/processed_data --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _stable_hash(payload: dict[str, Any], prefix: str) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _inject_uid_row(row: dict[str, Any], prefix: str, force: bool) -> dict[str, Any]:
    if not force and row.get("uid"):
        return row
    copied = dict(row)
    base = dict(copied)
    base.pop("uid", None)
    copied["uid"] = _stable_hash(base, prefix)
    return copied


def _process_json_list(input_path: Path, output_path: Path, prefix: str, force: bool) -> tuple[int, int]:
    with input_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{input_path} root is not list")

    total = 0
    changed = 0
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        total += 1
        before = item.get("uid")
        new_item = _inject_uid_row(item, prefix, force)
        if new_item.get("uid") != before:
            changed += 1
        out.append(new_item)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return total, changed


def _process_jsonl(input_path: Path, output_path: Path, prefix: str, force: bool) -> tuple[int, int]:
    total = 0
    changed = 0
    with input_path.open(encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for line_num, line in enumerate(fin, 1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError(f"{input_path}:{line_num} invalid JSON line")
            if not isinstance(item, dict):
                continue
            total += 1
            before = item.get("uid")
            new_item = _inject_uid_row(item, prefix, force)
            if new_item.get("uid") != before:
                changed += 1
            fout.write(json.dumps(new_item, ensure_ascii=False) + "\n")
    return total, changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign stable UID for processed data files")
    parser.add_argument("--dir", default="data/processed_data", help="processed data directory")
    parser.add_argument("--inplace", action="store_true", help="overwrite source files")
    parser.add_argument("--force", action="store_true", help="re-generate uid even if exists")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = root / target_dir

    jobs = [
        ("strategies.json", "strategy"),
        ("knowledge_rag.jsonl", "knowledge"),
        ("chat_samples.jsonl", "chat"),
    ]

    for filename, prefix in jobs:
        src = target_dir / filename
        if not src.exists():
            print(f"[skip] {filename}: not found")
            continue
        if args.inplace:
            # 先写临时文件再原子替换，避免同路径读写导致源文件被截断。
            tmp = src.with_name(src.name + ".tmp_uid_work")
            if src.suffix == ".json":
                total, changed = _process_json_list(src, tmp, prefix, args.force)
            else:
                total, changed = _process_jsonl(src, tmp, prefix, args.force)
            os.replace(tmp, src)
            print(f"[ok] {filename} -> {src.name} (inplace) | rows={total} changed={changed}")
        else:
            suffix = ".uid" + src.suffix
            dst = src.with_name(src.name + suffix)
            if src.suffix == ".json":
                total, changed = _process_json_list(src, dst, prefix, args.force)
            else:
                total, changed = _process_jsonl(src, dst, prefix, args.force)
            print(f"[ok] {filename} -> {dst.name} | rows={total} changed={changed}")


if __name__ == "__main__":
    main()
