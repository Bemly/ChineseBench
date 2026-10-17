import csv, glob, hashlib, json, os, statistics as st, sys
from collections import defaultdict

L = glob.glob('/Volumes/*/Projects/llmtest')[0]
MAP = f'{L}/手动解盲（主会话专用）/03_映射表/mapping.csv'
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
D = '/Users/bemly/Documents'
JUDGES = {  # 裁判目录 -> 对应参赛模型（用于剔除自评）
    'dsv4p': ('dsv4p/手动评分', 'deepseek-v4-pro'),
    'gemini3.7': ('gemini3.7/手动评分', 'gemini-3.7-flash'),
    'gemini4': ('gemini4/手动评分', 'gemini-4-argon-contributor'),
    'muse1.2': ('muse1.2/手动评分_副本', 'Muse Spark 1.2 Contributor'),
    'muse1.3': ('muse1.3/手动评分', 'Muse-Spark-1.3-Free'),
    'opus5.5': ('opus5.5/手动评分', 'claude-opus-5-5'),
}
DIMS = ['指令遵循', '文笔与文气', '活人感去AI味', '结构与节奏', '人物与对白', '逻辑与一致性',
        '吸引力可读性', '文体类型契合', '信息密度', '准确与诚实']
MODS = {'A': '语言基本功', 'B': '叙事结构', 'C': '人物与对白', 'D': '类型文学', 'E': 'RP与互动',
        'F': '法学社科论文', 'G': '长上下文续航', 'H': '综合实验', 'I': '去AI味', 'J': '多语言'}

STAGED = {f'T-J{i:02d}' for i in [1, 2, 3, 4, 5, 6, 9, 12, 13, 14, 15, 16]}
mapping = {}
for r in csv.DictReader(open(MAP, encoding='utf-8')):
    mapping[(r['题号'], r['匿名ID'])] = r

issues = []
rows = []
for j, (sub, self_model) in JUDGES.items():
    base = f'{D}/{sub}'
    # 盲评包完整性：sha256 与映射表比对
    bad = 0
    for (q, a), r in mapping.items():
        p = f'{base}/01_盲评包/{q}/{a}.md'
        if not os.path.exists(p):
            issues.append(f'[{j}] 盲评包缺失 {q}/{a}'); bad += 1; continue
        if hashlib.sha256(open(p, 'rb').read()).hexdigest() != r['输出sha256']:
            issues.append(f'[{j}] 盲评包被改动 {q}/{a}'); bad += 1
    seen = set()
    # 补评（汇总/补评_<裁判>/<题号>.csv）覆盖裁判原表中未填的题
    patch = {os.path.basename(p)[:-4]: p for p in glob.glob(f'{OUT}/补评_{j}/*.csv')}
    for f in sorted(glob.glob(f'{base}/02_记分表/*.csv')):
        q = os.path.basename(f)[:-4]
        f = patch.get(q, f)
        # 按列位置读（部分裁判改了表头/留空维度名）；点评中未加引号的逗号并回点评
        reader = csv.reader(open(f, encoding='utf-8-sig'))
        next(reader)
        for cells in reader:
            if not cells or not cells[0].strip():
                continue
            if len(cells) < 15:
                issues.append(f'[{j}] 列数不足 {q}/{cells[0]}'); continue
            r = dict(zip(['匿名ID', *DIMS, '通用均分', '专项分', '总分'], cells[:14]))
            r['一句话点评'] = ','.join(cells[14:])
            a = r['匿名ID'].strip()
            m = mapping.get((q, a))
            if not m:
                issues.append(f'[{j}] 记分表多出行 {q}/{a}'); continue
            seen.add((q, a))
            num = lambda s: float(s) if s.strip() else None  # 空 = 裁判判为不适用
            try:
                dims = [num(r[d]) for d in DIMS]
                avg, spec, tot = num(r['通用均分']), num(r['专项分']), float(r['总分'])
            except (ValueError, TypeError):
                issues.append(f'[{j}] 非数值/空缺 {q}/{a}'); continue
            # 分段评分题（外语+汉化）总分按多语言公式合成，十维允许留空，不做公式核对
            if q not in STAGED:
                present = [x for x in dims if x is not None]
                if avg is None or spec is None or not present:
                    issues.append(f'[{j}] 非分段题缺维度分 {q}/{a}')
                else:
                    if abs(st.mean(present) - avg) > 0.06:
                        issues.append(f'[{j}] 通用均分不符 {q}/{a}: 记{avg} 算{st.mean(present):.2f}')
                    if abs((avg + spec) / 2 - tot) > 0.06:
                        issues.append(f'[{j}] 总分不符 {q}/{a}: 记{tot} 算{(avg+spec)/2:.2f}')
            rows.append(dict(题号=q, 模块=q[2], 模型=m['模型'], 裁判=j, 自评=int(m['模型'] == self_model),
                             **dict(zip(DIMS, dims)), 通用均分=avg, 专项分=spec, 总分=tot,
                             点评=r.get('一句话点评', '').strip(), 匿名ID=a))
    for k in mapping:
        if k not in seen:
            issues.append(f'[{j}] 记分表缺行 {k[0]}/{k[1]}')
    print(j, 'sha不符/缺失:', bad)

EXCLUDE = {'glm-5.3'}  # 只答 4 题，按用户要求不纳入汇总
rows = [r for r in rows if r['模型'] not in EXCLUDE]
fields = ['题号', '模块', '模型', '裁判', '自评', *DIMS, '通用均分', '专项分', '总分', '点评', '匿名ID']
with open(f'{OUT}/明细_逐题逐裁判.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fields); w.writeheader(); w.writerows(rows)

models = sorted({r['模型'] for r in rows})
judges = list(JUDGES)
nq = {m: len({q for (q, a), r in mapping.items() if r['模型'] == m}) for m in models}
TOTAL_Q = len({q for q, a in mapping})

def agg(filt, key='总分'):
    """先对每题多裁判取均值，再对题取均值（题等权）。"""
    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if filt(r) and r[key] is not None:
            per[r['模型']][r['题号']].append(r[key])
    return {m: st.mean(st.mean(v) for v in qs.values()) for m, qs in per.items() if qs}

def trim(filt, key='总分'):
    """按裁判分别求均分（剔除自评），去掉最高、最低各一个后取平均；返回 {模型: (均值, 最高-均值, 最低-均值)}。"""
    res = {}
    for m in models:
        vals = [v for j in judges
                if (v := agg(lambda r, j=j: r['裁判'] == j and not r['自评'] and r['模型'] == m and filt(r), key).get(m)) is not None]
        if len(vals) < 3:
            continue
        core = sorted(vals)[1:-1]
        mu = st.mean(core)
        res[m] = (mu, max(vals) - mu, min(vals) - mu)
    return res

r_all = agg(lambda r: True)
r_ns = agg(lambda r: not r['自评'])
out = []
for m in models:
    out.append(dict(模型=m, 作答题数=nq[m], 覆盖率=f'{nq[m]/TOTAL_Q:.0%}',
                    总分_去自评=round(r_ns[m], 3), 总分_含自评=round(r_all[m], 3),
                    自评偏差=round(r_all[m] - r_ns[m], 3),
                    **{f'裁判_{j}': round(agg(lambda r, j=j: r['裁判'] == j).get(m, float('nan')), 3) for j in judges}))
t_tot = trim(lambda r: True)
for o in out:
    mu, up, dn = t_tot[o['模型']]
    o.update(总分_截尾=round(mu, 3), 误差_上=round(up, 3), 误差_下=round(dn, 3))
main = sorted([o for o in out if nq[o['模型']] >= TOTAL_Q * 0.5], key=lambda o: -o['总分_截尾'])
side = [o for o in out if nq[o['模型']] < TOTAL_Q * 0.5]
for i, o in enumerate(main, 1): o['排名'] = i
for o in side: o['排名'] = '不计（覆盖不足）'
board = main + side
with open(f'{OUT}/总榜.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, ['排名', *out[0].keys()]); w.writeheader(); w.writerows(board)

def matrix(name, cols, fn):
    with open(f'{OUT}/{name}', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['模型', *cols])
        for o in board:
            w.writerow([o['模型'], *[fn(o['模型'], c) for c in cols]])

mod_t = {k: trim(lambda r, k=k: r['模块'] == k) for k in MODS}
dim_t = {d: trim(lambda r: True, d) for d in DIMS + ['专项分']}
mod_cache = {k: {m: v[0] for m, v in t.items()} for k, t in mod_t.items()}
dim_cache = {d: {m: v[0] for m, v in t.items()} for d, t in dim_t.items()}
fmt = lambda x: '' if x is None else round(x, 2)
matrix('模块均分_截尾.csv', [f'{k}_{v}' for k, v in MODS.items()], lambda m, c: fmt(mod_cache[c[0]].get(m)))
matrix('维度均分_截尾.csv', DIMS + ['专项分'], lambda m, c: fmt(dim_cache[c].get(m)))

# 每题排名（去自评）
per_q = defaultdict(lambda: defaultdict(list))
for r in rows:
    if not r['自评']:
        per_q[r['题号']][r['模型']].append(r['总分'])
with open(f'{OUT}/逐题排名_去自评.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh); w.writerow(['题号', '名次', '模型', '均分', '裁判数'])
    for q in sorted(per_q):
        for i, (m, v) in enumerate(sorted(per_q[q].items(), key=lambda kv: -st.mean(kv[1])), 1):
            w.writerow([q, i, m, round(st.mean(v), 2), len(v)])

# 裁判宽严 & 一致性
jstat = []
for j in judges:
    v = [r['总分'] for r in rows if r['裁判'] == j]
    jstat.append((j, st.mean(v), st.pstdev(v)))

json.dump(dict(board=board, mods=MODS, dims=DIMS,
               mod={k: mod_cache[k] for k in MODS}, dim=dim_cache, mod_err=mod_t, dim_err=dim_t, judges=judges,
               jstat=jstat, total_q=TOTAL_Q, nq=nq),
          open(f'{OUT}/_data.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(f'{OUT}/校验记录.txt', 'w', encoding='utf-8').write('\n'.join(issues))
print('rows', len(rows), 'issues', len(issues))
for o in board:
    print(o['排名'], o['模型'], o['作答题数'], o['总分_截尾'], o['误差_上'], o['误差_下'], o['总分_去自评'], o['总分_含自评'], o['自评偏差'])
for j, m, s in jstat:
    print(j, round(m, 2), round(s, 2))
