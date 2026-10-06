#!/usr/bin/env python3
"""把 题库/*.md 解析为 tests.jsonl，供 run.py / judge.py 使用。

题目格式约定（见 README）：
  ## T-A01｜标题
  > 考察：a · b ｜ 难度：★★☆ ｜ 模式：单轮
  ```system ...```   可选，系统提示
  ```user ...```     一个或多个，每个是一轮用户输入
  ```check {json}``` 可选，自动指标配置
  **评分要点** 之后到下一个 --- / ## 为止是评分要点
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "题库"

HEAD_RE = re.compile(r"^## (T-[A-Z]\d+)｜(.+?)\s*$")
FENCE_RE = re.compile(r"^```(system|user|check)\s*$")


def parse_meta(line: str) -> dict:
    meta = {}
    for part in line.lstrip("> ").split("｜"):
        if "：" in part:
            k, v = part.split("：", 1)
            meta[k.strip()] = v.strip()
    return meta


def parse_file(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tests, cur, i = [], None, 0
    while i < len(lines):
        line = lines[i]
        m = HEAD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "module": path.stem,
                   "dims": [], "difficulty": "", "mode": "", "system": None,
                   "turns": [], "check": {}, "rubric": ""}
            tests.append(cur)
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        if line.startswith("> 考察："):
            meta = parse_meta(line)
            cur["dims"] = [d.strip() for d in meta.get("考察", "").split("·") if d.strip()]
            cur["difficulty"] = meta.get("难度", "")
            cur["mode"] = meta.get("模式", "")
            i += 1
            continue
        fm = FENCE_RE.match(line)
        if fm:
            kind, body = fm.group(1), []
            i += 1
            while i < len(lines) and lines[i].rstrip() != "```":
                body.append(lines[i])
                i += 1
            text = "\n".join(body).strip()
            if kind == "system":
                cur["system"] = text
            elif kind == "user":
                cur["turns"].append(text)
            else:
                cur["check"] = json.loads(text)
            i += 1
            continue
        if line.startswith("**评分要点"):
            body = [line.strip("*")]
            i += 1
            while i < len(lines) and not lines[i].startswith("---") and not HEAD_RE.match(lines[i]):
                body.append(lines[i])
                i += 1
            cur["rubric"] = "\n".join(body).strip()
            continue
        i += 1
    return tests


def load_all() -> list[dict]:
    tests = []
    for p in sorted(BANK.glob("*.md")):
        tests.extend(parse_file(p))
    seen = set()
    for t in tests:
        if t["id"] in seen:
            sys.exit(f"重复的题号：{t['id']}")
        if not t["turns"]:
            sys.exit(f"{t['id']} 没有 user 块")
        seen.add(t["id"])
    return tests


def main():
    tests = load_all()
    out = ROOT / "tests.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for t in tests:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    by_mod = {}
    for t in tests:
        by_mod[t["module"]] = by_mod.get(t["module"], 0) + 1
    print(f"共 {len(tests)} 题 → {out.name}")
    for k, v in by_mod.items():
        print(f"  {k}: {v}")
    multi = sum(1 for t in tests if len(t["turns"]) > 1)
    print(f"  其中多轮题 {multi} 道")


if __name__ == "__main__":
    main()
