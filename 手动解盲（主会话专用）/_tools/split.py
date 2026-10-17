#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机械切割脚本：把 手动题库/*.md（题目）与 手动题库/答案/*（答题卡）
按小题拆到 手动评分/ 下。只做字节级切割/原样拷贝，不改写任何原文一字。
- 题目：按 ^##\\s+T-XXX 切片，原字节原样写入 00_题目/T-XXX.md
- 答案单题文件（文件名 T-XXX.md）：整文件字节原样拷贝
- 答案合卷：按 ^#{2,3}\\s+T-XXX 切片，原字节原样写入；同一(模型,题)多片按文件名自然排序纯拼接（不加任何分隔符）
- 无 T 头的 part 文件（如 space-bunny G/J 续写）：按文件头“覆盖题目：T-XXX”整文件归题，多文件纯拼接
- 盲评包按题独立随机匿名（seed 固定并记录），内容零添加
用法：python3 split.py
"""
import os, re, json, csv, hashlib, random

ROOT = "/Volumes//Projects/llmtest"
SRC_Q_DIR = os.path.join(ROOT, "手动题库")
SRC_A_DIR = os.path.join(ROOT, "手动题库", "答案")
DST = os.path.join(ROOT, "手动评分")
D_Q = os.path.join(DST, "00_题目")
D_B = os.path.join(DST, "01_盲评包")
D_S = os.path.join(DST, "02_记分表")
D_M = os.path.join(DST, "03_映射表")
D_H = os.path.join(DST, "04_汇总")
D_L = os.path.join(DST, "_log")
SEED = 60917483

T_HEAD = re.compile(r'^(#{2,3})\s+(T-[A-Z]+\d+)')
T_ANY = re.compile(r'T-[A-Z]+\d+')
SINGLE_FN = re.compile(r'^(T-[A-Z]+\d+)\.md$')
PART_NO = re.compile(r'_part(\d+)\.md$')
COVER = re.compile(r'覆盖题目：(T-[A-Z]+\d+)')

def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()

def split_by_thead(data: bytes):
    """按行找 ^#{2,3} T-XXX 头，返回 [(tid, start, end)] 字节区间。无头返回 []。"""
    lines = data.split(b'\n')  # 用 \n 切，行尾 \r 保留在行内，不丢字节；下面用 offsets 重建
    # 为精确字节偏移，逐行累加
    offs = []
    off = 0
    for ln in lines:
        offs.append(off)
        off += len(ln) + 1  # +1 为被 split 吃掉的 \n（末行若无 \n 会多算 1，需修正）
    # 修正：若原数据不以 \n 结尾，最后一个 off 超出，做钳制（不影响切片，因 end 取下一头 start）
    heads = []  # (line_idx, tid)
    for i, ln in enumerate(lines):
        try:
            s = ln.decode('utf-8', errors='strict')
        except Exception:
            try:
                s = ln.decode('utf-8', errors='ignore')
            except Exception:
                continue
        m = T_HEAD.match(s.strip()) if False else T_HEAD.match(s)
        # 允许行首有空白？不允许，必须顶格 ##/###（与题库格式一致，避免误切正文里的引用）
        if m:
            heads.append((i, m.group(2)))
    if not heads:
        return []
    # 末尾 end：文件总字节数（注意 split 丢了 \n，需还原：总长就是 len(data)）
    spans = []
    for k, (li, tid) in enumerate(heads):
        start = offs[li]
        end = offs[heads[k+1][0]] if k+1 < len(heads) else len(data)
        spans.append((tid, start, end))
    return spans

def natkey(name: str):
    parts = re.split(r'(\d+)', name)
    return [int(p) if p.isdigit() else p for p in parts]

def main():
    for d in (D_Q, D_B, D_S, D_M, D_H, D_L):
        os.makedirs(d, exist_ok=True)
    log = {"seed": SEED, "method": "byte-slice-verbatim, no-rewrite",
           "questions": [], "answers": [], "skipped": [], "mapping": []}

    # ---- 1. 题目 ----
    qids = []
    for fn in sorted(os.listdir(SRC_Q_DIR)):
        if not fn.endswith('.md'):
            continue
        src = os.path.join(SRC_Q_DIR, fn)
        if not os.path.isfile(src):
            continue
        data = read_bytes(src)
        spans = split_by_thead(data)
        if not spans:
            log["skipped"].append({"file": f"手动题库/{fn}", "reason": "no-T-head"})
            continue
        for tid, s, e in spans:
            chunk = data[s:e]
            out = os.path.join(D_Q, f"{tid}.md")
            if os.path.exists(out):
                # 题目 ID 全局唯一，若重复则报错（不应发生）
                raise SystemExit(f"duplicate question id {tid} from {fn}")
            with open(out, 'wb') as f:
                f.write(chunk)
            qids.append(tid)
            log["questions"].append({"tid": tid, "src": f"手动题库/{fn}",
                                     "byte_range": [s, e], "sha256": sha256(chunk)})
    qids_sorted = sorted(set(qids))
    print(f"questions: {len(qids_sorted)}")

    # ---- 2. 答案：收集 (tid -> [(model, src_rel, chunk_bytes, desc)]) ----
    per = {}  # tid -> list of dicts
    models = sorted([d for d in os.listdir(SRC_A_DIR)
                     if os.path.isdir(os.path.join(SRC_A_DIR, d))])
    for model in models:
        mdir = os.path.join(SRC_A_DIR, model)
        for fn in sorted(os.listdir(mdir), key=natkey):
            src = os.path.join(mdir, fn)
            if not os.path.isfile(src):
                continue
            rel = f"手动题库/答案/{model}/{fn}"
            if fn == ".DS_Store" or fn.startswith("._"):
                log["skipped"].append({"file": rel, "reason": "system-file"})
                continue
            if not fn.endswith('.md'):
                log["skipped"].append({"file": rel, "reason": "non-md"})
                continue
            m = SINGLE_FN.match(fn)
            data = read_bytes(src)
            if m:
                tid = m.group(1)
                per.setdefault(tid, []).append({"model": model, "src": rel,
                    "kind": "whole-file", "range": [0, len(data)], "bytes": data})
                log["answers"].append({"tid": tid, "model": model, "src": rel,
                    "kind": "whole-file", "sha256": sha256(data), "size": len(data)})
                continue
            spans = split_by_thead(data)
            if spans:
                # 同文件同 tid 多片（如 G 合卷）先按文件内顺序拼
                by_tid = {}
                for tid, s, e in spans:
                    by_tid.setdefault(tid, []).append((s, e))
                for tid, ses in by_tid.items():
                    blob = b''.join(data[s:e] for s, e in ses)
                    per.setdefault(tid, []).append({"model": model, "src": rel,
                        "kind": f"slices:{len(ses)}", "range": ses, "bytes": blob})
                    log["answers"].append({"tid": tid, "model": model, "src": rel,
                        "kind": f"slices:{len(ses)}", "ranges": ses,
                        "sha256": sha256(blob), "size": len(blob)})
            else:
                # 无 T 头：看 preamble 覆盖题目（space-bunny G/J 续写 part）
                head = data[:3000].decode('utf-8', errors='ignore')
                cm = COVER.search(head)
                if cm:
                    tid = cm.group(1)
                    per.setdefault(tid, []).append({"model": model, "src": rel,
                        "kind": "whole-file-by-cover", "range": [0, len(data)], "bytes": data})
                    log["answers"].append({"tid": tid, "model": model, "src": rel,
                        "kind": "whole-file-by-cover", "sha256": sha256(data), "size": len(data)})
                else:
                    log["skipped"].append({"file": rel, "reason": "no-T-head-no-cover"})

    # ---- 3. 同(模型,题)多源拼接（space-bunny G/J 同题多 part）：按源文件名自然排序纯拼接 ----
    # per[tid] 目前是按 model 目录序、文件 natkey 序加入的；为确保确定性，再按 (model, src-natkey) 稳定排序并合并同 model
    combined = {}  # tid -> {model: blob}
    combined_src = {}
    for tid, items in per.items():
        # 按 src 自然排序，保证 part1..partN 顺序
        items_sorted = sorted(items, key=lambda x: (x["model"], natkey(x["src"])))
        bucket = {}
        order = {}
        for it in items_sorted:
            bucket.setdefault(it["model"], []).append(it)
        for model, lst in bucket.items():
            if len(lst) == 1:
                blob = lst[0]["bytes"]
            else:
                blob = b''.join(x["bytes"] for x in lst)
            combined.setdefault(tid, {})[model] = blob
            combined_src.setdefault(tid, {})[model] = [x["src"] for x in lst]

    # ---- 4. 匿名化 + 写盲评包/记分表/映射表 ----
    rng = random.Random(SEED)
    tids_all = sorted(set(qids_sorted) | set(combined.keys()))
    n_blind_files = 0
    with open(os.path.join(D_M, "mapping.csv"), 'w', newline='', encoding='utf-8') as mf:
        w = csv.writer(mf)
        w.writerow(["题号", "匿名ID", "模型", "源文件", "源总字节", "输出sha256"])
        for tid in tids_all:
            models_here = sorted(combined.get(tid, {}).keys())
            shuffled = models_here[:]
            rng.shuffle(shuffled)
            tdir = os.path.join(D_B, tid)
            if shuffled:
                os.makedirs(tdir, exist_ok=True)
            for i, model in enumerate(shuffled, 1):
                mid = f"M{i:02d}"
                blob = combined[tid][model]
                out = os.path.join(tdir, f"{mid}.md")
                with open(out, 'wb') as f:
                    f.write(blob)
                n_blind_files += 1
                srcs = combined_src[tid][model]
                w.writerow([tid, mid, model, ";".join(srcs), len(blob), sha256(blob)])
                log["mapping"].append({"tid": tid, "mid": mid, "model": model,
                                       "srcs": srcs, "sha256": sha256(blob), "size": len(blob)})
            # 记分表骨架
            sfile = os.path.join(D_S, f"{tid}.csv")
            with open(sfile, 'w', newline='', encoding='utf-8') as sf:
                sw = csv.writer(sf)
                sw.writerow(["匿名ID", "指令遵循", "文笔与文气", "活人感去AI味", "结构与节奏",
                             "人物与对白", "逻辑与一致性", "吸引力可读性", "文体类型契合",
                             "信息密度", "准确与诚实", "通用均分", "专项分", "总分", "一句话点评"])
                for i in range(1, len(shuffled)+1):
                    sw.writerow([f"M{i:02d}"] + [""]*14)
    log["stats"] = {"question_ids": len(tids_all), "blind_files": n_blind_files,
                    "models": models}
    with open(os.path.join(D_L, "split_log.json"), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"tids: {len(tids_all)}, blind files: {n_blind_files}")
    # 缺口报告
    for tid in tids_all:
        if tid not in combined:
            print(f"  {tid}: NO answers (question only)")
        elif tid not in qids_sorted:
            print(f"  {tid}: NO question file (answer only)")

if __name__ == "__main__":
    main()
