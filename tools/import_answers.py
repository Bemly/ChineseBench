#!/usr/bin/env python3
"""把手写 / 手动复制的回答导入成 run.py 的结果格式，之后可直接用 metrics.py、judge.py。

  python3 tools/import_answers.py answers/<模型名> [--model 显示名]

答案目录下任意 .md 文件，格式：
  ### T-A01
  第一轮回答……
  <<<TURN>>>
  第二轮回答……（多轮题）
  ### T-A02
  ……
输出到 results/<模型名>/。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_jsonl import ROOT, load_all  # noqa: E402
from run import to_markdown  # noqa: E402

HEAD = re.compile(r"^### (T-[A-Z]\d+)\s*$", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--model", default="")
    a = ap.parse_args()
    src = Path(a.src)
    name = a.model or src.name
    tests = {t["id"]: t for t in load_all()}
    out_dir = ROOT / "results" / re.sub(r"[^\w.\-]+", "_", name)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        parts = HEAD.split(text)
        for i in range(1, len(parts), 2):
            tid, body = parts[i], parts[i + 1]
            t = tests.get(tid)
            if not t:
                print(f"  未知题号 {tid}（{f.name}）")
                continue
            answers = [x.strip() for x in body.split("<<<TURN>>>")]
            if len(answers) != len(t["turns"]):
                print(f"  {tid}：回答 {len(answers)} 轮，题目 {len(t['turns'])} 轮，按较少者导入")
            rec = {"id": tid, "title": t["title"], "model": name, "temperature": None,
                   "time": time.strftime("%Y-%m-%d %H:%M:%S"), "system": t["system"],
                   "turns": [{"user": u, "content": c, "reasoning": "", "finish_reason": "stop",
                              "usage": {}, "seconds": 0} for u, c in zip(t["turns"], answers)]}
            (out_dir / f"{tid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            (out_dir / f"{tid}.md").write_text(to_markdown(rec), encoding="utf-8")
            n += 1
    print(f"导入 {n} 题 → {out_dir.relative_to(ROOT)}")
    missing = sorted(set(tests) - {p.stem for p in out_dir.glob('T-*.json')})
    if missing:
        print(f"  未作答 {len(missing)} 题：{' '.join(missing)}")


if __name__ == "__main__":
    main()
