#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机械提取评分要点：从 题库/*.md 按小题切出（题头 + 考察行 + check 块 + 评分要点节），
原字节原样写入 手动评分/参考/评分要点/<TID>.md。不改写任何原文一字，不含 user 题干
（题干已在 00_题目/；两处 user 文本是否一致另做核查）。
用法：python3 extract_rubrics.py
"""
import os, re, glob, hashlib

ROOT = "/Volumes//Projects/llmtest"
DST = os.path.join(ROOT, "手动评分", "参考", "评分要点")
T_HEAD = re.compile(r'^(#{2,3})\s+(T-[A-Z]+\d+)')
USER_RE = re.compile(r'```user(.*?)```', re.S)

def main():
    os.makedirs(DST, exist_ok=True)
    n = 0
    anomalies = []
    user_cmp = []
    for f in sorted(glob.glob(os.path.join(ROOT, "题库", "*.md"))):
        text = open(f, encoding="utf-8").read()
        lines = text.split("\n")
        idx = [i for i, l in enumerate(lines) if T_HEAD.match(l)]
        for k, i in enumerate(idx):
            tid = T_HEAD.match(lines[i]).group(2)
            end = idx[k + 1] if k + 1 < len(idx) else len(lines)
            seg = lines[i:end]
            # 考察行（本节内）
            kao = [l for l in seg if l.startswith("> 考察")]
            # check 块（本节内，原文取整块）
            seg_text = "\n".join(seg)
            checks = re.findall(r"```check.*?```", seg_text, re.S)
            # 评分要点节：从 **评分要点 起到节末
            rstart = [j for j, l in enumerate(seg) if l.startswith("**评分要点")]
            if len(rstart) != 1:
                anomalies.append((os.path.basename(f), tid, f"rubric-sections={len(rstart)}"))
                continue
            rub = seg[rstart[0]:]
            # 去掉节末的 --- 分隔与空行
            while rub and (rub[-1].strip() in ("---", "")):
                rub.pop()
            # 节内不应再有别的 T 题头
            if any(T_HEAD.match(l) and not l.startswith(lines[i][:20]) for l in rub[1:]):
                anomalies.append((os.path.basename(f), tid, "nested-T-head"))
                continue
            body = "\n".join([seg[0]] + ([""] if kao or checks else []) + kao + checks + ([""] if (kao or checks) and rub else []) + rub)
            # user 文本一致性核查（题库 vs 手动题库）
            mq = os.path.join(ROOT, "手动题库")
            mfile = glob.glob(os.path.join(mq, "*.md"))
            mu = None
            for mf in mfile:
                mt = open(mf, encoding="utf-8").read()
                m = re.search(r"^##\s+" + tid + r".*?```user(.*?)```", mt, re.S | re.M)
                if m:
                    mu = m.group(1)
                    break
            ou = USER_RE.search(seg_text)
            if ou and mu is not None and ou.group(1).strip() != mu.strip():
                user_cmp.append((tid, "USER-DIFFERS"))
            with open(os.path.join(DST, tid + ".md"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body.rstrip("\n") + "\n")
            n += 1
    print(f"rubrics: {n}")
    print("anomalies:", anomalies if anomalies else "none")
    print("user-text:", user_cmp if user_cmp else "all-match")

if __name__ == "__main__":
    main()
