#!/usr/bin/env python3
"""对 run.py 的输出计算可自动化的客观指标。

  python3 tools/metrics.py results/<模型A> [results/<模型B> ...]

每个模型目录下生成 metrics.csv，并在终端打印汇总对比。
指标只是辅助信号：AI 味词频高不等于写得差，但能稳定地区分"套话型"模型。
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_jsonl import load_all  # noqa: E402
from run import strip_think  # noqa: E402

# 中文 AI 味高频词表（参考指标，可按需增删）
AI_WORDS = [
    "仿佛", "宛如", "犹如", "似乎", "一抹", "一丝", "不禁", "缓缓", "静静地", "深邃", "璀璨",
    "交织", "编织", "低语", "呢喃", "涟漪", "心中一紧", "心头一颤", "嘴角上扬", "嘴角勾起",
    "勾起一抹", "眼中闪过", "眸中", "眸光", "空气仿佛凝固", "时间仿佛静止", "命运的齿轮",
    "岁月的长河", "无声地诉说", "这一刻", "那一刻", "某种", "难以言喻", "五味杂陈", "百感交集",
    "深吸一口气", "见证", "不仅仅是", "而是一种", "承载着", "斑驳", "熠熠生辉", "意味深长",
    "若有所思", "不由得", "一股暖流", "喃喃自语", "指节发白", "骨节分明", "倒吸一口凉气",
    "全场哗然", "微微一笑", "淡淡的", "光晕", "沉默了片刻", "心照不宣", "温柔地",
]

CJK_RE = re.compile(r"[一-鿿]")
SENT_SPLIT = re.compile(r"[。！？!?…]+")


def cjk(text):
    return "".join(CJK_RE.findall(text))


def ai_hits(text):
    c = Counter({w: text.count(w) for w in AI_WORDS})
    return +c


def rep_ratio(text, n=8):
    s = cjk(text)
    grams = [s[i:i + n] for i in range(len(s) - n + 1)]
    return 0.0 if not grams else 1 - len(set(grams)) / len(grams)


def avg_sent_len(text):
    sents = [cjk(s) for s in SENT_SPLIT.split(text)]
    sents = [s for s in sents if s]
    return round(sum(map(len, sents)) / len(sents), 1) if sents else 0


def para_violations(text, max_s):
    bad = 0
    for p in text.split("\n"):
        p = p.strip()
        if not p or p.startswith("#") or re.match(r"^第\s*\S+\s*章", p):
            continue
        n = len([s for s in SENT_SPLIT.split(p) if cjk(s)])
        if n > max_s:
            bad += 1
    return bad


def ends_with_question(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    last = lines[-1].rstrip("」』”\"'）)*_ ")
    return last.endswith(("？", "?"))


def per_k(n, chars):
    return round(n * 1000 / chars, 2) if chars else 0


def analyze(rec, check):
    texts = [strip_think(t["content"]) for t in rec["turns"]]
    full = "\n".join(texts)
    chars = len(cjk(full))
    ai = ai_hits(full)
    row = {
        "id": rec["id"] + rec.get("_suffix", ""),
        "turns": len(texts),
        "truncated": sum(1 for t in rec["turns"] if t.get("finish_reason") == "length"),
        "chars": chars,
        "ai_per_k": per_k(sum(ai.values()), chars),
        "ai_top": " ".join(f"{w}×{n}" for w, n in ai.most_common(5)),
        "rep8": round(rep_ratio(full), 3),
    }
    per_turn = check.get("per_turn") or len(texts) == 1
    checked = texts if per_turn else texts[-1:]

    if "target_chars" in check:
        tgt = check["target_chars"]
        ratios = [len(cjk(t)) / tgt for t in checked if t]
        row["len_ratio"] = round(sum(ratios) / len(ratios), 2) if ratios else 0
        row["len_ratio_min"] = round(min(ratios), 2) if ratios else 0
    if "forbid" in check:
        hits = Counter()
        for w in check["forbid"]:
            hits[w] = full.count(w)
        hits = +hits
        row["forbid_hits"] = sum(hits.values())
        row["forbid_detail"] = " ".join(f"{w}×{n}" for w, n in hits.most_common())
        if check.get("per_turn") and len(texts) > 1:
            row["forbid_by_turn"] = "/".join(str(sum(t.count(w) for w in check["forbid"])) for t in texts)
    if "count_max" in check:
        viol = []
        for ch, mx in check["count_max"].items():
            n = full.count(ch)
            if n > mx:
                viol.append(f"{ch}={n}>{mx}")
        row["count_viol"] = " ".join(viol) or "OK"
    if check.get("end_question"):
        row["end_q_fail"] = sum(1 for t in checked if not ends_with_question(t))
    if "max_sentences_per_para" in check:
        row["para_viol"] = sum(para_violations(t, check["max_sentences_per_para"]) for t in checked)

    # 前后半段对比（长输出质量衰减 / 节奏变化）
    body = "\n".join(texts[:-1]) if rec["id"] == "T-G01" else full  # G01 最后一轮是测验
    if len(cjk(body)) >= 1500:
        third = len(body) // 3
        head, tail = body[:third], body[-third:]
        row["sent_len_head"] = avg_sent_len(head)
        row["sent_len_tail"] = avg_sent_len(tail)
        row["ai_per_k_head"] = per_k(sum(ai_hits(head).values()), len(cjk(head)))
        row["ai_per_k_tail"] = per_k(sum(ai_hits(tail).values()), len(cjk(tail)))
        row["rep8_tail"] = round(rep_ratio(tail), 3)
    if len(texts) > 1:
        row["chars_by_turn"] = "/".join(str(len(cjk(t))) for t in texts)
    return row


def main():
    dirs = [Path(p) for p in sys.argv[1:]]
    if not dirs:
        sys.exit(__doc__)
    checks = {t["id"]: t["check"] for t in load_all()}
    summary = []
    for d in dirs:
        rows = []
        for jp in sorted(d.glob("T-*.json")):
            rec = json.loads(jp.read_text(encoding="utf-8"))
            if not rec.get("turns"):
                continue
            rec["_suffix"] = jp.stem[len(rec["id"]):]
            rows.append(analyze(rec, checks.get(rec["id"], {})))
        if not rows:
            print(f"{d}: 没有结果")
            continue
        fields = []
        for r in rows:
            fields += [k for k in r if k not in fields]
        with (d / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        total = sum(r["chars"] for r in rows)
        ai_total = sum(r["ai_per_k"] * r["chars"] / 1000 for r in rows)
        lens = [r["len_ratio"] for r in rows if "len_ratio" in r]
        summary.append({
            "model": d.name, "n": len(rows), "chars": total,
            "ai_per_k": per_k(ai_total, total),
            "forbid": sum(r.get("forbid_hits", 0) for r in rows),
            "len_ok": f"{sum(1 for x in lens if 0.8 <= x <= 1.3)}/{len(lens)}",
            "rep8": round(sum(r["rep8"] for r in rows) / len(rows), 3),
            "trunc": sum(r["truncated"] for r in rows),
        })
        print(f"\n== {d.name}：{len(rows)} 个结果 → {d / 'metrics.csv'}")
        for r in rows:
            extra = []
            if "len_ratio" in r:
                extra.append(f"字数比 {r['len_ratio']}")
            if "forbid_hits" in r:
                extra.append(f"禁词 {r['forbid_hits']}")
            if "count_viol" in r:
                extra.append(f"计数 {r['count_viol']}")
            if "end_q_fail" in r:
                extra.append(f"末句非问句 {r['end_q_fail']}")
            if "para_viol" in r:
                extra.append(f"超长段 {r['para_viol']}")
            if r["truncated"]:
                extra.append(f"⚠截断 {r['truncated']}")
            print(f"  {r['id']:<10} {r['chars']:>6}字  AI味 {r['ai_per_k']:>5}/千字  重复 {r['rep8']:<5}  " + "  ".join(extra))

    if len(summary) > 0:
        print("\n== 模型汇总")
        print(f"  {'模型':<28}{'结果数':>6}{'总字数':>9}{'AI味/千字':>10}{'禁词':>6}{'字数达标':>9}{'重复率':>8}{'截断':>6}")
        for s in summary:
            print(f"  {s['model']:<28}{s['n']:>6}{s['chars']:>9}{s['ai_per_k']:>10}{s['forbid']:>6}{s['len_ok']:>9}{s['rep8']:>8}{s['trunc']:>6}")


if __name__ == "__main__":
    main()
