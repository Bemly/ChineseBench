#!/usr/bin/env python3
"""对 run.py 的输出计算可自动化的客观指标。

  python3 tools/metrics.py results/<模型A> [results/<模型B> ...]   # 评测结果
  python3 tools/metrics.py --text 某本人类小说.txt [更多.txt ...]     # 校准：给人类文本测基线
  python3 tools/metrics.py --text x.txt --show                        # 同时列出命中的原句

每个模型目录下生成 metrics.csv，并在终端打印汇总对比。
指标只是辅助信号：建议先用 --text 给几本你认可的人类小说跑出基线，再看模型偏离多少。
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
import slop_patterns as SP  # noqa: E402

CJK_RE = re.compile(r"[一-鿿]")
SENT_SPLIT = re.compile(r"[。！？!?…]+")


def compile_list(items):
    out = []
    for it in items:
        if it.startswith("re:"):
            out.append((it, re.compile(it[3:], re.I)))
        else:
            out.append((it, re.compile(re.escape(it))))
    return out


ZH_CATS = {k: (w, compile_list(v)) for k, (w, v) in SP.ZH.items()}
OTHER_CATS = {k: compile_list(v) for k, v in SP.OTHER.items()}


def cjk(text):
    return "".join(CJK_RE.findall(text))


def units(text):
    """长度单位：中日韩按非空白字符数，拉丁/西里尔按词数×2（约等于汉字信息量）。"""
    lang = detect_lang(text)
    if lang in ("en", "fr", "es", "ru"):
        return len(re.findall(r"\w+", text)) * 2
    return len(re.sub(r"\s", "", text))


def detect_lang(text):
    n = len(text) or 1
    kana = len(re.findall(r"[぀-ヿ]", text))
    hangul = len(re.findall(r"[가-힯]", text))
    cyr = len(re.findall(r"[Ѐ-ӿ]", text))
    han = len(CJK_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul / n > 0.15:
        return "ko"
    if kana / n > 0.08:
        return "ja"
    if cyr / n > 0.3:
        return "ru"
    if han / n > 0.3:
        return "zh"
    if latin / n > 0.3:
        low = text.lower()
        fr = len(re.findall(r"\b(?:le|la|les|des|est|une|que|pas|dans|avec)\b", low))
        es = len(re.findall(r"\b(?:el|los|las|una|que|por|con|del|para|pero)\b", low))
        en = len(re.findall(r"\b(?:the|and|was|that|with|her|his|she|he)\b", low))
        return max((en, "en"), (fr, "fr"), (es, "es"))[1]
    return "zh"


def slop(text, show=False):
    """返回 {类别: 命中数}、加权分（每千字）、命中示例。"""
    lang = detect_lang(text)
    u = units(text) or 1
    counts, examples, weighted = Counter(), [], 0.0
    if lang == "zh":
        for cat, (w, pats) in ZH_CATS.items():
            for label, rx in pats:
                for m in rx.finditer(text):
                    counts[cat] += 1
                    if show:
                        s = max(0, m.start() - 12)
                        examples.append((cat, text[s:m.end() + 12].replace("\n", " ")))
            weighted += w * counts[cat]
        for name, (ch, w) in SP.ZH_PUNCT.items():
            counts[name] = text.count(ch)
            weighted += w * counts[name]
    else:
        for label, rx in OTHER_CATS.get(lang, []):
            for m in rx.finditer(text):
                counts["slop"] += 1
                if show:
                    s = max(0, m.start() - 20)
                    examples.append(("slop", text[s:m.end() + 20].replace("\n", " ")))
        weighted = 2.0 * counts["slop"]
    return lang, counts, round(weighted * 1000 / u, 2), examples


def rep_ratio(text, n=8):
    s = re.sub(r"\s", "", text)
    grams = [s[i:i + n] for i in range(len(s) - n + 1)]
    return 0.0 if not grams else round(1 - len(set(grams)) / len(grams), 3)


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
        if len([s for s in SENT_SPLIT.split(p) if cjk(s)]) > max_s:
            bad += 1
    return bad


def ends_with_question(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    return lines[-1].rstrip("」』”\"'）)*_ ").endswith(("？", "?"))


def per_k(n, size):
    return round(n * 1000 / size, 2) if size else 0


def text_row(name, text, show=False):
    lang, c, score, ex = slop(text, show)
    u = units(text)
    row = {"id": name, "lang": lang, "units": u, "slop_score": score, "rep8": rep_ratio(text)}
    if lang == "zh":
        for cat in list(SP.ZH) + list(SP.ZH_PUNCT):
            row[cat] = per_k(c[cat], u)
        row["avg_sent"] = avg_sent_len(text)
    else:
        row["slop"] = per_k(c["slop"], u)
    return row, ex


def analyze(rec, check):
    texts = [strip_think(t["content"]) for t in rec["turns"]]
    full = "\n".join(texts)
    row, _ = text_row(rec["id"] + rec.get("_suffix", ""), full)
    langs = [detect_lang(t) for t in texts if t]
    if len(set(langs)) > 1:  # 多语言多轮题（J01–J06）：按轮分别检测，再按长度加权
        us = [units(t) for t in texts if t]
        row["lang"] = "mix"
        row["slop_score"] = round(sum(slop(t)[2] * u for t, u in zip([t for t in texts if t], us)) / (sum(us) or 1), 2)
    row["turns"] = len(texts)
    row["truncated"] = sum(1 for t in rec["turns"] if t.get("finish_reason") == "length")
    per_turn = check.get("per_turn") or len(texts) == 1
    checked = texts if per_turn else texts[-1:]
    if check.get("skip_last") and len(texts) > 1:  # 最后一轮是测验/清单，不计入字数等检查
        checked = texts[:-1]

    if "target_chars" in check:
        tgt = check["target_chars"]
        ratios = [units(t) / tgt for t in checked if t]
        row["len_ratio"] = round(sum(ratios) / len(ratios), 2) if ratios else 0
        row["len_ratio_min"] = round(min(ratios), 2) if ratios else 0
    if "forbid" in check:
        hits = +Counter({w: full.count(w) for w in check["forbid"]})
        row["forbid_hits"] = sum(hits.values())
        row["forbid_detail"] = " ".join(f"{w}×{n}" for w, n in hits.most_common())
        if check.get("per_turn") and len(texts) > 1:
            row["forbid_by_turn"] = "/".join(str(sum(t.count(w) for w in check["forbid"])) for t in texts)
    if "forbid_cats" in check:  # 题目要求禁用某些 AI 味类别（如 contrast、aphorism）
        _, c, _, _ = slop(full)
        row["cat_hits"] = " ".join(f"{k}×{c[k]}" for k in check["forbid_cats"] if c[k]) or "OK"
        row["cat_hits_n"] = sum(c[k] for k in check["forbid_cats"])
    if "count_max" in check:
        viol = [f"{ch}={full.count(ch)}>{mx}" for ch, mx in check["count_max"].items() if full.count(ch) > mx]
        row["count_viol"] = " ".join(viol) or "OK"
    if check.get("end_question"):
        row["end_q_fail"] = sum(1 for t in checked if not ends_with_question(t))
    if "max_sentences_per_para" in check:
        row["para_viol"] = sum(para_violations(t, check["max_sentences_per_para"]) for t in checked)

    # 前后三分之一对比：长输出的质量衰减
    body = "\n".join(texts[:-1]) if check.get("skip_last") and len(texts) > 1 else full
    if units(body) >= 1500:
        third = len(body) // 3
        head, tail = body[:third], body[-third:]
        row["sent_len_head"], row["sent_len_tail"] = avg_sent_len(head), avg_sent_len(tail)
        row["slop_head"], row["slop_tail"] = slop(head)[2], slop(tail)[2]
        row["rep8_tail"] = rep_ratio(tail)
    if len(texts) > 1:
        row["units_by_turn"] = "/".join(str(units(t)) for t in texts)
        row["lang_by_turn"] = "/".join(detect_lang(t) for t in texts)
        row["slop_by_turn"] = "/".join(str(slop(t)[2]) for t in texts)
    return row


def write_csv(path, rows):
    fields = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def text_mode(paths, show):
    print(f"{'文件':<30}{'语言':>4}{'长度':>8}{'加权分':>8}  分项（每千字）")
    for p in paths:
        text = Path(p).read_text(encoding="utf-8", errors="ignore")
        row, ex = text_row(Path(p).name, text, show)
        detail = "  ".join(f"{k}={v}" for k, v in row.items()
                           if k not in ("id", "lang", "units", "slop_score") and v)
        print(f"{row['id'][:28]:<30}{row['lang']:>4}{row['units']:>8}{row['slop_score']:>8}  {detail}")
        if show:
            for cat, snip in ex[:60]:
                print(f"    [{cat}] …{snip}…")


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    show = "--show" in argv
    argv = [a for a in argv if a != "--show"]
    if argv[0] == "--text":
        return text_mode(argv[1:], show)

    checks = {t["id"]: t["check"] for t in load_all()}
    summary = []
    for d in map(Path, argv):
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
        write_csv(d / "metrics.csv", rows)
        zh = [r for r in rows if r["lang"] == "zh"]
        lens = [r["len_ratio"] for r in rows if "len_ratio" in r]
        tot_u = sum(r["units"] for r in zh) or 1

        def wavg(k):
            return round(sum(r.get(k, 0) * r["units"] for r in zh) / tot_u, 2)

        summary.append({
            "model": d.name, "n": len(rows), "units": sum(r["units"] for r in rows),
            "slop": wavg("slop_score"), "contrast": wavg("contrast"), "aphorism": wavg("aphorism"),
            "deep": wavg("pseudo_deep"), "forbid": sum(r.get("forbid_hits", 0) for r in rows),
            "len_ok": f"{sum(1 for x in lens if 0.8 <= x <= 1.3)}/{len(lens)}",
            "trunc": sum(r["truncated"] for r in rows),
        })
        print(f"\n== {d.name}：{len(rows)} 个结果 → {d / 'metrics.csv'}")
        for r in rows:
            extra = []
            for k, label in (("len_ratio", "字数比"), ("forbid_hits", "禁词"), ("cat_hits", "禁用句式"),
                             ("count_viol", "计数"), ("end_q_fail", "末句非问句"), ("para_viol", "超长段")):
                if k in r:
                    extra.append(f"{label} {r[k]}")
            if r["truncated"]:
                extra.append(f"⚠截断 {r['truncated']}")
            print(f"  {r['id']:<12}{r['lang']:>3}{r['units']:>7}  AI味 {r['slop_score']:>6}  重复 {r['rep8']:<6}" + "  ".join(extra))

    if summary:
        print("\n== 模型汇总（AI味各项为每千字，仅统计中文输出）")
        print(f"  {'模型':<28}{'结果':>5}{'总长':>8}{'AI味':>7}{'不是而是':>8}{'金句体':>7}{'伪深刻':>7}{'禁词':>6}{'字数达标':>9}{'截断':>5}")
        for s in summary:
            print(f"  {s['model']:<28}{s['n']:>5}{s['units']:>8}{s['slop']:>7}{s['contrast']:>8}"
                  f"{s['aphorism']:>7}{s['deep']:>7}{s['forbid']:>6}{s['len_ok']:>9}{s['trunc']:>5}")


if __name__ == "__main__":
    main()
