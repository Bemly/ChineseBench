#!/usr/bin/env python3
"""用一个（更强的）裁判模型给 run.py 的结果打分。

  python3 tools/judge.py results/<模型A> [results/<模型B> ...] \\
      --judge-base-url https://你的OpenAI兼容地址/v1 --judge-model 裁判模型名 --api-key KEY

- 普通题：用 评分/裁判提示词.md 的 ```judge 模板整体打分。
- 带 "stages" 的多语言题：按 评分/多语言分段评分规则.md 分阶段独立打分（原文 / 汉化 / 对照 / 本土化），
  再按 STAGE_PRESETS 的公式合成，并给出汉化增益 Δ 与诊断标签。
输出：<模型目录>/judge/<题号>[__阶段].json，汇总 judge_summary.csv 与 judge_stages.csv。
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
from metrics import analyze, slop  # noqa: E402
from run import chat, strip_think  # noqa: E402

DIMS = ["follow", "prose", "human", "structure", "character",
        "logic", "appeal", "genre", "density", "accuracy"]

# 材料来源：("out", n) = 第 n 轮模型输出；("prompt", n) = 第 n 轮用户输入
STAGE_PRESETS = {
    "bilingual3": {
        "stages": [
            {"name": "原文", "rule": "原文", "material": [("题目", ("prompt", 1)), ("原文", ("out", 1))]},
            {"name": "汉化", "rule": "汉化", "material": [("中文小说", ("out", 2))]},
            {"name": "对照", "rule": "对照", "material": [("原文", ("out", 1)), ("译文", ("out", 2))]},
            {"name": "本土化", "rule": "本土化", "material": [("外语原文", ("out", 1)), ("本土化稿", ("out", 3))]},
        ],
        "combine": lambda s: 0.8 * (0.35 * s["原文"] + 0.35 * s["汉化"] + 0.30 * s["对照"]) + 0.2 * s["本土化"],
        "diagnose": True,
    },
    "bilingual2": {
        "stages": [
            {"name": "原文", "rule": "原文", "material": [("题目", ("prompt", 1)), ("原文", ("out", 1))]},
            {"name": "汉化", "rule": "汉化", "material": [("中文小说", ("out", 2))]},
            {"name": "对照", "rule": "对照", "material": [("原文", ("out", 1)), ("译文", ("out", 2))]},
        ],
        "combine": lambda s: 0.35 * s["原文"] + 0.35 * s["汉化"] + 0.30 * s["对照"],
        "diagnose": True,
    },
    "outbound": {
        "stages": [
            {"name": "英译", "rule": "外译", "material": [("英文译文", ("out", 1))]},
            {"name": "日译", "rule": "外译", "material": [("日文译文", ("out", 2))]},
            {"name": "对照", "rule": "对照", "material": [("中文原文（在题目中）", ("prompt", 1)), ("英文译文", ("out", 1)),
                                                        ("日文译文", ("out", 2)), ("译者的处理说明", ("out", 3))]},
        ],
        "combine": lambda s: 0.3 * s["英译"] + 0.3 * s["日译"] + 0.4 * s["对照"],
        "diagnose": False,
    },
}

GENERAL_SCHEMA = ('{"scores": {"follow": n, "prose": n, "human": n, "structure": n, "character": n, "logic": n, '
                  '"appeal": n, "genre": n, "density": n, "accuracy": n}, "rubric": n, '
                  '"hard_violations": [], "highlights": ["最多3条，引用原文"], "problems": ["最多5条，引用原文"], "verdict": "一句话"}')
COMPARE_SCHEMA = ('{"scores": {"fidelity": n, "style": n, "culture": n, "register": n, "completeness": n}, "rubric": n, '
                  '"errors": [{"type": "误译/漏译/增译/风格偏移/文化处理不当", "source": "原文片段", "target": "译文片段", "note": "说明"}], '
                  '"highlights": [], "verdict": "一句话"}')


def md_blocks(path, tag_re):
    md = (ROOT / "评分" / path).read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r"```(" + tag_re + r")\n(.*?)\n```", md, re.S)}


def load_templates():
    general = md_blocks("裁判提示词.md", r"judge").get("judge")
    stage_md = md_blocks("多语言分段评分规则.md", r"judge_stage|rule:[^\n]+")
    if not general or "judge_stage" not in stage_md:
        sys.exit("找不到裁判模板（评分/裁判提示词.md 或 评分/多语言分段评分规则.md）")
    rules = {k[5:]: v for k, v in stage_md.items() if k.startswith("rule:")}
    return general, stage_md["judge_stage"], rules


def clip(text, limit):
    return text if len(text) <= limit else text[:limit // 2] + "\n……（中间省略）……\n" + text[-limit // 2:]


def build_general(tpl, test, rec, metrics_row):
    prompt_parts = ["【系统提示】\n" + test["system"]] if test["system"] else []
    prompt_parts += [f"【第 {i} 轮用户输入】\n{clip(u, 6000)}" for i, u in enumerate(test["turns"], 1)]
    multi = len(rec["turns"]) > 1
    out_parts = [(f"【第 {i} 轮模型输出】\n" if multi else "") + strip_think(t["content"])
                 for i, t in enumerate(rec["turns"], 1)]
    return (tpl.replace("{{ID}}", test["id"]).replace("{{TITLE}}", test["title"])
               .replace("{{DIMS}}", " · ".join(test["dims"]))
               .replace("{{PROMPT}}", "\n\n".join(prompt_parts))
               .replace("{{RUBRIC}}", test["rubric"])
               .replace("{{METRICS}}", json.dumps(metrics_row, ensure_ascii=False))
               .replace("{{OUTPUT}}", "\n\n".join(out_parts)))


def build_stage(tpl, rules, stage, test, rec):
    parts, metric_texts = [], []
    for label, (kind, n) in stage["material"]:
        if kind == "out":
            if n > len(rec["turns"]):
                return None
            text = strip_think(rec["turns"][n - 1]["content"])
            metric_texts.append(text)
        else:
            text = test["turns"][n - 1]
        parts.append(f"【{label}】\n{text}")
    metrics = {f"材料{i + 1}": dict(zip(("lang", "counts", "slop_score"), slop(t)[:3])) for i, t in enumerate(metric_texts)}
    schema = COMPARE_SCHEMA if stage["rule"] == "对照" else GENERAL_SCHEMA
    return (tpl.replace("{{STAGE}}", stage["name"]).replace("{{ID}}", test["id"]).replace("{{TITLE}}", test["title"])
               .replace("{{MATERIAL}}", "\n\n".join(parts)).replace("{{RUBRIC}}", test["rubric"])
               .replace("{{METRICS}}", json.dumps(metrics, ensure_ascii=False, default=dict))
               .replace("{{STAGE_RULES}}", rules[stage["rule"]]).replace("{{SCHEMA}}", schema))


def parse_json(text):
    text = strip_think(text)
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("裁判没有输出 JSON")
    return json.loads(text[s:e + 1])


def stage_total(j):
    """阶段分 = 各维度均分 × 0.5 + 专项分 × 0.5"""
    vals = [v for v in j.get("scores", {}).values() if isinstance(v, (int, float))]
    general = mean(vals) if vals else 0
    return round(general * 0.5 + float(j.get("rubric") or 0) * 0.5, 2), round(general, 2)


def diagnose(s):
    o, h, c = s.get("原文"), s.get("汉化"), s.get("对照")
    if None in (o, h, c):
        return ""
    if c >= 7 and h >= 7:
        return "信达兼备"
    if h >= 7 and c < 6:
        return "漂亮但不忠实（再创作）"
    if c >= 7 and h < 6:
        return "忠实但翻译腔"
    if o - h >= 2:
        return "汉化损耗大"
    if h - o >= 2:
        return "外语原创是短板"
    return "平庸"


def ask(a, prompt, out):
    if out.exists() and not a.force:
        return json.loads(out.read_text(encoding="utf-8"))
    print(f"  评审 {out.parent.parent.name}/{out.stem} …", end="", flush=True)
    try:
        j = parse_json(chat(a, [{"role": "user", "content": prompt}])["content"])
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, TimeoutError) as e:
        print(f" 失败：{e}")
        return None
    out.write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    print(" 完成")
    return j


def write_csv(path, rows):
    fields = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


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
    a.base_url, a.model, a.temperature, a.top_p = a.judge_base_url, a.judge_model, 0.0, None

    general_tpl, stage_tpl, rules = load_templates()
    tests = {t["id"]: t for t in load_all()}
    keys = [k for k in a.ids.split(",") if k]
    for d in map(Path, a.dirs):
        jdir = d / "judge"
        jdir.mkdir(exist_ok=True)
        rows, stage_rows = [], []
        for jp in sorted(d.glob("T-*.json")):
            rec = json.loads(jp.read_text(encoding="utf-8"))
            test = tests.get(rec["id"])
            if not test or not rec.get("turns") or (keys and not any(rec["id"].startswith(k) for k in keys)):
                continue
            preset = STAGE_PRESETS.get(test["check"].get("stages", ""))
            row = {"id": jp.stem, "module": test["module"]}
            if preset:
                scores = {}
                for st in preset["stages"]:
                    prompt = build_stage(stage_tpl, rules, st, test, rec)
                    if prompt is None:
                        continue
                    j = ask(a, prompt, jdir / f"{jp.stem}__{st['name']}.json")
                    if j is None:
                        continue
                    tot, gen = stage_total(j)
                    scores[st["name"]] = tot
                    stage_rows.append({"id": jp.stem, "stage": st["name"], "total": tot, "dims_mean": gen,
                                       "rubric": j.get("rubric"), **{f"s_{k}": v for k, v in j.get("scores", {}).items()},
                                       "errors": len(j.get("errors", [])), "verdict": j.get("verdict", "")})
                if len(scores) < len(preset["stages"]):
                    print(f"  {jp.stem}：阶段不完整（{list(scores)}），跳过合成")
                    continue
                row["total"] = round(preset["combine"](scores), 2)
                row.update({f"S_{k}": v for k, v in scores.items()})
                if preset["diagnose"]:
                    row["delta_汉化"] = round(scores["汉化"] - scores["原文"], 2)
                    row["diagnosis"] = diagnose(scores)
            else:
                j = ask(a, build_general(general_tpl, test, rec, analyze(rec, test["check"])), jdir / jp.name)
                if j is None:
                    continue
                tot, gen = stage_total({"scores": {k: v for k, v in j.get("scores", {}).items() if k in DIMS},
                                        "rubric": j.get("rubric")})
                row.update({"total": tot, "general": gen, "rubric": j.get("rubric"),
                            **{k: j.get("scores", {}).get(k) for k in DIMS},
                            "hard_violations": "；".join(j.get("hard_violations", [])), "verdict": j.get("verdict", "")})
            rows.append(row)
        if not rows:
            continue
        write_csv(d / "judge_summary.csv", rows)
        if stage_rows:
            write_csv(d / "judge_stages.csv", stage_rows)
        print(f"\n== {d.name}：{len(rows)} 题，总均分 {mean(r['total'] for r in rows):.2f}")
        mods = {}
        for r in rows:
            mods.setdefault(r["module"], []).append(r["total"])
        for m, v in mods.items():
            print(f"  {m:<16} {mean(v):.2f}  ({len(v)} 题)")
        for k in DIMS:
            vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
            if vals:
                print(f"    {k:<10} {mean(vals):.2f}")
        bi = [r for r in rows if "diagnosis" in r]
        if bi:
            print("  多语言分段：")
            for r in bi:
                parts = "  ".join(f"{k[2:]} {r[k]}" for k in r if k.startswith("S_"))
                print(f"    {r['id']:<10} {parts}  Δ汉化 {r['delta_汉化']:+}  → {r['diagnosis']}  总 {r['total']}")
            for st in ("原文", "汉化", "对照"):
                vals = [r[f"S_{st}"] for r in bi]
                print(f"    平均 S_{st} {mean(vals):.2f}")


if __name__ == "__main__":
    main()
