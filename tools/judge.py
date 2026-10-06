#!/usr/bin/env python3
"""用一个（更强的）裁判模型给 run.py 的结果打分。

  python3 tools/judge.py results/<模型A> [results/<模型B> ...] \\
      --judge-base-url https://你的OpenAI兼容地址/v1 --judge-model 裁判模型名 --api-key KEY

裁判提示词模板来自 评分/裁判提示词.md 里的 ```judge 代码块。
每个结果的评分写入 <模型目录>/judge/<题号>.json，汇总写入 <模型目录>/judge_summary.csv。
"""
import argparse
import csv
import json
import re
import sys
import urllib.error
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_jsonl import ROOT, load_all  # noqa: E402
from metrics import analyze  # noqa: E402
from run import chat, strip_think  # noqa: E402

DIMS = ["follow", "prose", "human", "structure", "character",
        "logic", "appeal", "genre", "density", "accuracy"]


def load_template():
    md = (ROOT / "评分" / "裁判提示词.md").read_text(encoding="utf-8")
    m = re.search(r"```judge\n(.*?)\n```", md, re.S)
    if not m:
        sys.exit("评分/裁判提示词.md 中找不到 ```judge 模板")
    return m.group(1)


def clip(text, limit):
    return text if len(text) <= limit else text[:limit // 2] + "\n……（中间省略）……\n" + text[-limit // 2:]


def build_prompt(tpl, test, rec, metrics_row):
    prompt_parts = []
    if test["system"]:
        prompt_parts.append("【系统提示】\n" + test["system"])
    for i, u in enumerate(test["turns"], 1):
        prompt_parts.append(f"【第 {i} 轮用户输入】\n{clip(u, 6000)}")
    out_parts = []
    for i, t in enumerate(rec["turns"], 1):
        head = f"【第 {i} 轮模型输出】" if len(rec["turns"]) > 1 else ""
        out_parts.append(head + "\n" + strip_think(t["content"]))
    return (tpl.replace("{{ID}}", test["id"]).replace("{{TITLE}}", test["title"])
               .replace("{{DIMS}}", " · ".join(test["dims"]))
               .replace("{{PROMPT}}", "\n\n".join(prompt_parts))
               .replace("{{RUBRIC}}", test["rubric"])
               .replace("{{METRICS}}", json.dumps(metrics_row, ensure_ascii=False))
               .replace("{{OUTPUT}}", "\n\n".join(out_parts)))


def parse_json(text):
    text = strip_think(text)
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("裁判没有输出 JSON")
    return json.loads(text[s:e + 1])


def total(j):
    vals = [v for k, v in j.get("scores", {}).items() if k in DIMS and isinstance(v, (int, float))]
    general = mean(vals) if vals else 0
    return round(general * 0.5 + float(j.get("rubric", 0)) * 0.5, 2), round(general, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--judge-base-url", required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--api-key", default="local")
    ap.add_argument("--ids", default="")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    # 复用 run.chat 的参数结构
    a.base_url, a.model, a.temperature, a.top_p = a.judge_base_url, a.judge_model, 0.0, None

    tpl = load_template()
    tests = {t["id"]: t for t in load_all()}
    keys = [k for k in a.ids.split(",") if k]
    for d in map(Path, a.dirs):
        jdir = d / "judge"
        jdir.mkdir(exist_ok=True)
        rows = []
        for jp in sorted(d.glob("T-*.json")):
            rec = json.loads(jp.read_text(encoding="utf-8"))
            test = tests.get(rec["id"])
            if not test or not rec.get("turns") or (keys and not any(rec["id"].startswith(k) for k in keys)):
                continue
            out = jdir / jp.name
            if out.exists() and not a.force:
                j = json.loads(out.read_text(encoding="utf-8"))
            else:
                print(f"  评审 {d.name}/{jp.stem} …", end="", flush=True)
                prompt = build_prompt(tpl, test, rec, analyze(rec, test["check"]))
                try:
                    r = chat(a, [{"role": "user", "content": prompt}])
                    j = parse_json(r["content"])
                except (urllib.error.URLError, ValueError, json.JSONDecodeError) as e:
                    print(f" 失败：{e}")
                    continue
                out.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
                print(" 完成")
            tot, gen = total(j)
            rows.append({"id": jp.stem, "module": test["module"], "total": tot, "general": gen,
                         "rubric": j.get("rubric"), **{k: j.get("scores", {}).get(k) for k in DIMS},
                         "hard_violations": "；".join(j.get("hard_violations", [])),
                         "verdict": j.get("verdict", "")})
        if not rows:
            continue
        with (d / "judge_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n== {d.name}：{len(rows)} 题，总均分 {mean(r['total'] for r in rows):.2f}")
        mods = {}
        for r in rows:
            mods.setdefault(r["module"], []).append(r["total"])
        for m, v in mods.items():
            print(f"  {m:<16} {mean(v):.2f}  ({len(v)} 题)")
        for k in DIMS:
            vals = [r[k] for r in rows if isinstance(r[k], (int, float))]
            if vals:
                print(f"    {k:<10} {mean(vals):.2f}")


if __name__ == "__main__":
    main()
