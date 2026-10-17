"""从 汇总/_data.json 生成「文笔坐标」竖版卡片（仿图灵坐标排版，简洁版）。用法: build2.py <汇总目录>

分数展示：灰线 = 最低裁判分 → 最高裁判分（已剔除自评），圆点 = 去掉最高最低后的均分。
雷达图：各维度先在 10 个模型间做 z 分数，再减去该模型自身 z 均值，经 tanh 压缩成半径，
       蓝色（相对自身）r = 0.55 + 0.38·tanh((z_i − z̄)/σ_z)，突出模型内部的相对强弱；
       黄色（对标全模型）r = 0.15 + 0.8·(x_i − min_i)/(max_i − min_i)，该单项在 10 个模型中的位置。
"""
import html, json, math, os, statistics as st, sys

OUT = sys.argv[1]
D = json.load(open(f'{OUT}/_data.json', encoding='utf-8'))
CARD_DIR = f'{OUT}/文笔坐标'
os.makedirs(CARD_DIR, exist_ok=True)
esc = html.escape

NAMES = {
    'claude-opus-5-5': ('Claude Opus 5.5', 'Anthropic'),
    'gemini-4-argon-contributor': ('Gemini 4 Argon', 'Google'),
    'Muse Spark 1.2 Contributor': ('Muse Spark 1.2', 'Meta AI'),
    'deepseek-v4-pro': ('DeepSeek V4 Pro 0813', 'DeepSeek'),
    'Muse-Spark-1.3-Free': ('Muse Spark 1.3', 'Meta AI'),
    'LongCat-2.0': ('LongCat 2.0', '美团'),
    'space-bunny-free': ('space-bunny', '未公开'),
    'gemini-3.7-flash': ('Gemini 3.7 Flash', 'Google'),
    'LongCat-2.5-Preview-Free': ('LongCat 2.5 Preview', '美团'),
    'Qwen3.6-27B-FP8': ('Qwen3.6 27B', 'Alibaba'),
}
JUDGES = {'dsv4p': ('DeepSeek', 'deepseek-v4-pro'), 'gemini3.7': ('Gemini 3.7', 'gemini-3.7-flash'),
          'gemini4': ('Gemini 4', 'gemini-4-argon-contributor'), 'muse1.2': ('Muse 1.2', 'Muse Spark 1.2 Contributor'),
          'muse1.3': ('Muse 1.3', 'Muse-Spark-1.3-Free'), 'opus5.5': ('Opus 5.5', 'claude-opus-5-5')}
DIMS = D['dims']

# ---- 图标与使用环境 ----
import base64
LOGO_DIR = f'{OUT}/_logos'


def logo(f, h, extra=''):
    if not f:
        return ''
    raw = open(f'{LOGO_DIR}/{f}', 'rb').read()
    mime = 'image/svg+xml' if f.endswith('.svg') else 'image/png'
    return f'<img src="data:{mime};base64,{base64.b64encode(raw).decode()}" style="height:{h}px;vertical-align:middle;{extra}">'


VENDOR = {  # 厂商标识（美团无现成图标，用 LongCat 字标代替；space-bunny 未公开）
    'claude-opus-5-5': 'anthropic-text.svg', 'gemini-4-argon-contributor': 'google-brand-color.svg',
    'gemini-3.7-flash': 'google-brand-color.svg', 'Muse Spark 1.2 Contributor': 'meta-brand-color.svg',
    'Muse-Spark-1.3-Free': 'meta-brand-color.svg', 'deepseek-v4-pro': 'deepseek-text.svg',
    'LongCat-2.0': 'longcat-text.svg', 'LongCat-2.5-Preview-Free': 'longcat-text.svg',
    'Qwen3.6-27B-FP8': 'alibaba-text.svg', 'space-bunny-free': None}
MLOGO = {
    'claude-opus-5-5': 'claude-color.svg', 'gemini-4-argon-contributor': 'gemini-color.svg',
    'gemini-3.7-flash': 'gemini-color.svg', 'Muse Spark 1.2 Contributor': 'muse.png',
    'Muse-Spark-1.3-Free': 'muse.png', 'deepseek-v4-pro': 'deepseek-color.svg',
    'LongCat-2.0': 'longcat-color.svg', 'LongCat-2.5-Preview-Free': 'longcat-color.svg',
    'Qwen3.6-27B-FP8': 'qwen-color.svg', 'space-bunny-free': None}
HARNESS = {'ClaudeCode': ('Claude Code', 'claudecode-color.svg'), 'Air': ('JetBrains Air', 'air.png'),
           'Junie': ('Junie', 'junie-color.svg'), 'OpenCode': ('OpenCode', 'opencode.svg'),
           'DSH': ('DeepSeek Harness 极简模式', 'deepseek-harness.png')}
ENV = {  # 参赛：(harness, 推理强度)
    'claude-opus-5-5': ('ClaudeCode', 'High'), 'gemini-3.7-flash': ('Air', 'High'),
    'Qwen3.6-27B-FP8': ('Junie', ''), 'Muse Spark 1.2 Contributor': ('OpenCode', 'xHigh'),
    'LongCat-2.0': ('OpenCode', 'Max'), 'LongCat-2.5-Preview-Free': ('OpenCode', 'Max'),
    'Muse-Spark-1.3-Free': ('OpenCode', 'xHigh'), 'space-bunny-free': ('OpenCode', 'Max'),
    'deepseek-v4-pro': ('DSH', 'High'), 'gemini-4-argon-contributor': ('OpenCode', 'High')}
JENV = {  # 裁判（教师）：(模型图标, 显示名, harness, 强度)
    'dsv4p': ('deepseek-color.svg', 'DeepSeek V4 Pro 0813', 'DSH', ''),
    'gemini3.7': ('gemini-color.svg', 'Gemini 3.7 Flash', 'Air', ''),
    'gemini4': ('gemini-color.svg', 'Gemini 4 Argon', 'OpenCode', 'High'),
    'muse1.2': ('muse.png', 'Muse Spark 1.2 Contributor', 'OpenCode', 'xHigh'),
    'muse1.3': ('muse.png', 'Muse Spark 1.3 Contributor', 'OpenCode', 'xHigh'),
    'opus5.5': ('claude-color.svg', 'Claude Opus 5.5', 'ClaudeCode', 'High')}


SPACER = '<span style="display:inline-block;width:42px"></span>'


def env_chip(h, effort, size=24):
    n, f = HARNESS[h]
    e = f' · {effort}' if effort else ''
    return (f'<span style="display:inline-flex;align-items:center;gap:8px;background:#f1f3f7;border-radius:999px;'
            f'padding:6px 16px 6px 10px;font-size:{size}px;color:#4b5263;white-space:nowrap">{logo(f, size + 6, "border-radius:6px")}{n}{e}</span>')

SHORT = ['指令遵循', '文笔', '活人感', '结构', '人物对白', '逻辑', '吸引力', '文体', '密度', '准确']
MODS = D['mods']
MOD_SHORT = {'A': '语言基本功', 'B': '叙事结构', 'C': '人物对白', 'D': '类型文学', 'E': 'RP 互动',
             'F': '法学社科', 'G': '长上下文', 'H': '综合实验', 'I': '去AI味', 'J': '多语言'}

board = [o for o in D['board'] if isinstance(o['排名'], int)]
models = [o['模型'] for o in board]
N = len(models)

CSS = """
:root{--bg:#eceef2;--panel:#fff;--ink:#1b2230;--sub:#8a91a0;--line:#e6e9ef;--acc:#4a6fb0;--rng:#c9ced8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);font-family:"PingFang SC","Hiragino Sans GB","Noto Sans SC",system-ui,sans-serif;color:var(--ink)}
.card{width:1080px;height:1920px;padding:60px;display:flex;flex-direction:column;gap:24px;background:var(--bg);overflow:hidden}
.top{display:flex;justify-content:space-between;align-items:center;font-size:26px;color:var(--sub)}
.brand{font-size:30px;color:var(--ink);letter-spacing:10px;font-weight:600}
h1{font-size:76px;font-weight:500;line-height:1.05}
.panel{background:var(--panel);border-radius:20px;padding:28px 32px}
.pt{font-size:24px;color:var(--sub);margin-bottom:10px}
.big{display:flex;align-items:baseline;gap:22px}
.big .s{font-size:100px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1}
.big .r{font-size:40px;color:var(--acc);font-weight:600}
.big .q{font-size:26px;color:var(--sub);margin-left:auto}
.foot{margin-top:auto;font-size:19px;color:var(--sub);display:flex;justify-content:space-between}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td{padding:3px 6px;border-bottom:1px solid var(--line);font-size:26px;vertical-align:middle}
td.n{text-align:right;white-space:nowrap}
.heat td{text-align:center;font-size:24px;padding:13px 4px;border:none}
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px 14px}
.tile{background:#f6f7fa;border-radius:14px;padding:10px 12px;min-width:0}
.tk{font-size:19px;color:var(--sub)}
.tv{display:flex;align-items:center;gap:10px;margin-top:6px}
.tv span{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tv b{font-size:30px;font-variant-numeric:tabular-nums}
.tg{font-size:15px;color:var(--sub);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

.heat th{font-size:22px;color:var(--sub);font-weight:400;padding:6px 2px}
.heat td.m{text-align:left;font-size:25px;white-space:nowrap}
"""
FOOT = '<div class="foot"><span>灰线：裁判最低 → 最高 · 点：去极值均分</span><span>文笔坐标 2026.10.17</span></div>'


ANIM_JS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'anim.js'), encoding='utf-8').read()


def page(title, body):
    return (f'<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{CSS}</style></head>'
            f'<body>{body}<script>{ANIM_JS}</script></body></html>')


def rng(mu, up, dn, lo, hi, w=420, h=34, dot='#4a6fb0', ends=False):
    """灰色区间线（最低→最高）+ 圆点（去极值均分）。"""
    pad = 50 if ends else 10
    x = lambda v: pad + (v - lo) / (hi - lo) * (w - 2 * pad)
    a, b, c = x(mu + dn), x(mu + up), x(mu)
    y = h / 2
    lab = (f'<text x="{a - 14:.1f}" y="{y + 7}" text-anchor="end" font-size="20" fill="#8a91a0">{mu + dn:.2f}</text>'
           f'<text x="{b + 14:.1f}" y="{y + 7}" font-size="20" fill="#8a91a0">{mu + up:.2f}</text>') if ends else ''
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<line class="rl" style="transform-box:view-box;transform-origin:{c:.1f}px {y}px" x1="{a:.1f}" y1="{y}" x2="{b:.1f}" y2="{y}" stroke="#c9ced8" stroke-width="8" stroke-linecap="round"/>'
            f'<circle class="rd" style="transform-box:fill-box;transform-origin:center" cx="{c:.1f}" cy="{y}" r="10" fill="{dot}"/>{lab}</svg>')


def axis(lo, hi, w):
    x = lambda v: 10 + (v - lo) / (hi - lo) * (w - 20)
    t = ''.join(f'<line x1="{x(v):.1f}" y1="0" x2="{x(v):.1f}" y2="8" stroke="#c9ced8" stroke-width="2"/>'
                f'<text x="{x(v):.1f}" y="30" text-anchor="middle" font-size="19" fill="#8a91a0">{v}</text>'
                for v in range(math.ceil(lo), math.floor(hi) + 1))
    return f'<svg width="{w}" height="36" viewBox="0 0 {w} 36">{t}</svg>'


def scale_of(triples):
    lo = min(mu + dn for mu, up, dn in triples)
    hi = max(mu + up for mu, up, dn in triples)
    return math.floor(lo * 2) / 2, math.ceil(hi * 2) / 2


def radar(m):
    """蓝：z 分数去均值 + tanh（相对自身）；黄：单项 min-max（对标全模型）。"""
    z, peer = [], []
    for d in DIMS:
        vals = [D['dim'][d][x] for x in models]
        mu, sd = st.mean(vals), st.pstdev(vals) or 1
        z.append((D['dim'][d][m] - mu) / sd)
        lo, hi = min(vals), max(vals)
        peer.append(0.15 + 0.8 * (D['dim'][d][m] - lo) / ((hi - lo) or 1))
    zbar, zsd = st.mean(z), st.pstdev(z) or 1
    radii = [0.55 + 0.38 * math.tanh((zi - zbar) / zsd) for zi in z]
    cx, cy, R, n = 470, 255, 190, len(DIMS)
    ang = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
    P = lambda r, a: f'{cx + R * r * math.cos(a):.1f},{cy + R * r * math.sin(a):.1f}'
    grid = ''.join(f'<polygon points="{" ".join(P(f, a) for a in ang)}" fill="none" stroke="#e6e9ef" stroke-width="1.5"/>' for f in (.15, .55, .95))
    org = f'class="rp" style="transform-box:view-box;transform-origin:{cx}px {cy}px"'
    base = f'<polygon {org} points="{" ".join(P(r, a) for r, a in zip(peer, ang))}" fill="#e3a27a" fill-opacity=".35" stroke="#e3a27a" stroke-width="3"/>'
    poly = f'<polygon {org} points="{" ".join(P(r, a) for r, a in zip(radii, ang))}" fill="#4a6fb0" fill-opacity=".45" stroke="#4a6fb0" stroke-width="3"/>'
    labels = ''
    for i, a in enumerate(ang):
        lx, ly = cx + (R + 62) * math.cos(a), cy + (R + 40) * math.sin(a)
        labels += (f'<text class="rlab" x="{lx:.0f}" y="{ly - 4:.0f}" text-anchor="middle" font-size="24" fill="#1b2230">{SHORT[i]}</text>'
                   f'<text class="rlab" x="{lx:.0f}" y="{ly + 24:.0f}" text-anchor="middle" font-size="21" fill="#8a91a0">{D["dim"][DIMS[i]][m]:.2f} · <tspan fill="#e3a27a" font-weight="600">#{sorted(models, key=lambda x: -D["dim"][DIMS[i]][x]).index(m) + 1}</tspan></text>')
    return f'<svg viewBox="0 0 940 530" width="940" height="530">{grid}{base}{poly}{labels}</svg>'


def model_card(o):
    m = o['模型']
    name, org = NAMES[m]
    trip = [D['mod_err'][k][m] for k in MODS if m in D['mod_err'][k]]
    lo, hi = scale_of([v for k in MODS for v in D['mod_err'][k].values()])
    rows = ''.join(
        f'<tr><td>{MOD_SHORT[k]}</td><td>{rng(*D["mod_err"][k][m], lo, hi, w=470)}</td>'
        f'<td class="n">{D["mod_err"][k][m][0]:.2f}</td></tr>'
        for k in MODS if m in D['mod_err'][k])
    blo, bhi = scale_of([(b['总分_截尾'], b['误差_上'], b['误差_下']) for b in board])
    judges = ''.join(
        f'<td class="n" style="font-size:22px;color:{"#c4573f" if JUDGES[j][1] == m else "#1b2230"}">'
        f'<div style="color:#8a91a0;font-size:18px">{logo(JENV[j][0], 18)} {JUDGES[j][0]}</div>{o["裁判_" + j]:.2f}{"*" if JUDGES[j][1] == m else ""}</td>'
        for j in D['judges'])
    body = f'''<div class="card">
<div class="top"><span style="height:40px;display:flex;align-items:center">{logo(VENDOR[m], 34) or esc(org)}</span><span class="brand">文笔坐标</span></div>
<h1 style="display:flex;align-items:center;gap:22px">{logo(MLOGO[m], 72)}{esc(name)}</h1>
<div class="panel"><div class="big"><span class="s cnt">{o["总分_截尾"]:.2f}</span><span class="r">#{o["排名"]}</span>
<span class="q" style="text-align:right">{env_chip(*ENV[m])}<div style="margin-top:10px">{o["作答题数"]}/{D["total_q"]} 题</div></span></div>
<div style="margin-top:10px">{rng(o["总分_截尾"], o["误差_上"], o["误差_下"], blo, bhi, w=896, h=40, ends=True)}</div></div>
<div class="panel"><div class="pt" style="display:flex;gap:28px"><span><span style="color:#4a6fb0">●</span> 相对自身</span><span><span style="color:#e3a27a">●</span> 对标全模型</span></div>{radar(m)}</div>
<div class="panel"><table>{rows}</table></div>
<div class="panel" style="padding:18px 24px"><table><tr>{judges}</tr></table></div>
{FOOT}</div>'''
    return page(f'{name} 文笔坐标', body)


def board_page():
    lo, hi = scale_of([(o['总分_截尾'], o['误差_上'], o['误差_下']) for o in board])
    rows = ''.join(
        f'<tr><td style="width:46px;color:#8a91a0;font-size:26px">{o["排名"]}</td><td style="white-space:nowrap;padding:5px 6px">'
        f'<div style="display:flex;align-items:center;gap:12px;font-size:26px">{logo(MLOGO[o["模型"]], 30) or SPACER}{esc(NAMES[o["模型"]][0])}</div>'
        f'<div style="margin:2px 0 0 42px;font-size:17px;color:#8a91a0;display:flex;align-items:center;gap:6px">'
        f'{logo(HARNESS[ENV[o["模型"]][0]][1], 19, "border-radius:4px")}{HARNESS[ENV[o["模型"]][0]][0]}'
        f'{" · " + ENV[o["模型"]][1] if ENV[o["模型"]][1] else ""}</div></td>'
        f'<td>{rng(o["总分_截尾"], o["误差_上"], o["误差_下"], lo, hi, w=360, h=40)}</td>'
        f'<td class="n" style="font-size:38px;font-weight:600"><span class="cnt">{o["总分_截尾"]:.2f}</span></td></tr>'
        for o in board)

    def champs(title, keys, names, table):
        tiles = ''
        for k, nm in zip(keys, names):
            best = max(models, key=lambda x: table[k][x])
            second = sorted((table[k][x] for x in models), reverse=True)[1]
            tiles += (f'<div class="tile"><div class="tk">{nm}</div>'
                      f'<div class="tv">{logo(MLOGO[best], 34) or SPACER}<b>{table[k][best]:.2f}</b></div>'
                      f'<div class="tg">{esc(NAMES[best][0])} · +{table[k][best] - second:.2f}</div></div>')
        return f'<div class="panel"><div class="pt">{title}</div><div class="tiles">{tiles}</div></div>'

    body = f'''<div class="card"><div class="top"><span>中文创意写作 · 107 题盲评</span><span class="brand">文笔坐标</span></div>
<h1>总榜</h1>
<div class="panel" style="padding:18px 28px"><table>{rows}</table>
<table><tr><td style="border:none;width:46px"></td><td style="border:none"></td><td style="border:none;width:360px">{axis(lo, hi, 360)}</td><td style="border:none;width:104px"></td></tr></table></div>
{champs("模块冠军", list(MODS), [MOD_SHORT[k] for k in MODS], D["mod"])}
{champs("维度冠军", DIMS, SHORT, D["dim"])}
{FOOT}</div>'''
    return page('文笔坐标 总榜', body)


def heat_color(v, lo, hi):
    t = 0 if hi == lo else (v - lo) / (hi - lo)
    r, g, b = int(240 + (74 - 240) * t), int(214 + (111 - 214) * t), int(196 + (176 - 196) * t)
    return f'background:rgb({r},{g},{b});color:{"#fff" if t > .55 else "#1b2230"}'


def strips(cols, labels, table, w=936 - 64):
    """每项一条横轴，10 个模型的图标按分数落位；上下错位避免重叠。"""
    vals = [table[c][m] for c in cols for m in models]
    lo, hi = math.floor(min(vals)), math.ceil(max(vals))
    lab_w, pad = 120, 18
    x = lambda v: lab_w + pad + (v - lo) / (hi - lo) * (w - lab_w - 2 * pad)
    rowh, out = 72, ''
    for i, (c, l) in enumerate(zip(cols, labels)):
        y = i * rowh + 26
        out += (f'<text x="0" y="{y + 7}" font-size="21" fill="#4b5263">{l}</text>'
                f'<line x1="{x(lo):.1f}" y1="{y}" x2="{x(hi):.1f}" y2="{y}" stroke="#e6e9ef" stroke-width="2"/>')
        placed = []
        for m in sorted(models, key=lambda m: table[c][m]):
            px = x(table[c][m])
            lane = 0
            while any(abs(px - q) < 26 and ln == lane for q, ln in placed):
                lane += 1
            placed.append((px, lane))
            dy = [0, -16, 16][lane % 3]
            f = MLOGO[m]
            if f:
                raw = open(f'{LOGO_DIR}/{f}', 'rb').read()
                mime = 'image/svg+xml' if f.endswith('.svg') else 'image/png'
                out += (f'<image class="sp" href="data:{mime};base64,{base64.b64encode(raw).decode()}" x="{px - 13:.1f}" y="{y + dy - 13:.1f}" width="26" height="26"/>')
            else:
                out += f'<circle class="sp" cx="{px:.1f}" cy="{y + dy}" r="7" fill="#9aa1ae"/>'
    ax = ''.join(f'<text x="{x(v):.1f}" y="{len(cols) * rowh + 22}" text-anchor="middle" font-size="19" fill="#8a91a0">{v}</text>'
                 for v in range(lo, hi + 1))
    h = len(cols) * rowh + 32
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{out}{ax}</svg>'


def heat_table(cols, labels, table, fs=24):
    def two(l):
        l = l.replace(' ', '')
        return l if len(l) <= 2 else f'{l[:len(l) // 2 + len(l) % 2]}<br>{l[len(l) // 2 + len(l) % 2:]}'
    head = ''.join(f'<th style="font-size:19px;line-height:1.25">{two(l)}</th>' for l in labels)
    cw = (936 - 36 - 272) / len(cols)
    colg = '<colgroup><col style="width:272px">' + ''.join(f'<col style="width:{cw:.0f}px">' for _ in cols) + '</colgroup>'
    rows = ''
    for o in board:
        m = o['模型']
        cells = ''
        for c in cols:
            vs = [table[c][x] for x in models]
            cells += f'<td style="{heat_color(table[c][m], min(vs), max(vs))};font-size:{fs}px">{table[c][m]:.2f}</td>'
        rows += f'<tr><td class="m" style="font-size:21px">{logo(MLOGO[m], 24)} {esc(NAMES[m][0])}</td>{cells}</tr>'
    return f'<table class="heat" style="table-layout:fixed">{colg}<tr><th></th>{head}</tr>{rows}</table>'


def heat_page(title, cols, labels, table, strip_cols, strip_labels):
    body = f'''<div class="card"><div class="top"><span>去极值均分 · 每列由浅到深 = 低到高</span><span class="brand">文笔坐标</span></div>
<h1>{title}</h1>
<div class="panel" style="padding:18px 18px">{heat_table(cols, labels, table)}</div>
<div class="panel"><div class="pt">分布</div>{strips(strip_cols, strip_labels, table)}</div>
<div class="foot"><span></span><span>文笔坐标 2026.10.17</span></div></div>'''
    return page(title, body)


def judge_corr():
    """裁判两两之间在同一份作答上的总分 Pearson 相关。"""
    import csv as _csv
    sc = {}
    for r in _csv.DictReader(open(f'{OUT}/明细_逐题逐裁判.csv', encoding='utf-8-sig')):
        sc.setdefault(r['裁判'], {})[(r['题号'], r['模型'])] = float(r['总分'])
    js = D['judges']
    M = {}
    for a in js:
        for b in js:
            ks = sorted(set(sc[a]) & set(sc[b]))
            xa, xb = [sc[a][k] for k in ks], [sc[b][k] for k in ks]
            ma, mb = st.mean(xa), st.mean(xb)
            num = sum((p - ma) * (q - mb) for p, q in zip(xa, xb))
            den = math.sqrt(sum((p - ma) ** 2 for p in xa) * sum((q - mb) ** 2 for q in xb))
            M[a, b] = num / den
    off = [M[a, b] for a in js for b in js if a != b]
    lo, hi = min(off), max(off)
    head = ''.join(f'<th>{logo(JENV[j][0], 24)}<br>{JUDGES[j][0]}</th>' for j in js)
    rows = ''
    for a in js:
        cells = ''.join(
            f'<td style="background:#f4f5f8;color:#c0c5cf">—</td>' if a == b else
            f'<td style="{heat_color(M[a, b], lo, hi)}">{M[a, b]:.2f}</td>' for b in js)
        rows += f'<tr><td class="m" style="font-size:21px">{logo(JENV[a][0], 24)} {JUDGES[a][0]}</td>{cells}</tr>'
    return f'<table class="heat" style="table-layout:fixed"><colgroup><col style="width:190px"></colgroup><tr><th></th>{head}</tr>{rows}</table>'


def judge_page():
    head = ''.join(f'<th>{logo(JENV[j][0], 24)}<br>{JUDGES[j][0]}</th>' for j in D['judges'])
    rows = ''
    for o in board:
        m = o['模型']
        cells = ''.join(f'<td style="{heat_color(o["裁判_" + j], 4, 9)}">{o["裁判_" + j]:.2f}{"*" if JUDGES[j][1] == m else ""}</td>' for j in D['judges'])
        rows += f'<tr><td class="m" style="font-size:21px">{logo(MLOGO[m], 24)} {esc(NAMES[m][0])}</td>{cells}</tr>'
    strict = ''.join(
        f'<tr><td style="white-space:nowrap;font-size:23px">{logo(JENV[j][0], 24)} {JENV[j][1]}</td>'
        f'<td>{env_chip(JENV[j][2], JENV[j][3], 18)}</td><td class="n" style="font-size:23px">{mu:.2f}</td></tr>'
        for j, mu, sd in sorted(D['jstat'], key=lambda x: x[1]))
    body = f'''<div class="card"><div class="top"><span>* 自评，不计分</span><span class="brand">文笔坐标</span></div>
<h1>裁判</h1>
<div class="panel" style="padding:18px 18px"><table class="heat" style="table-layout:fixed"><colgroup><col style="width:272px"></colgroup><tr><th></th>{head}</tr>{rows}</table></div>
<div class="panel" style="padding:18px 18px"><div class="pt" style="padding-left:10px">打分一致性（裁判两两相关系数）</div>{judge_corr()}</div>
<div class="panel" style="padding:18px 28px"><div class="pt">环境 · 平均给分（严 → 宽）</div><table>{strict}</table></div>
<div class="foot"><span></span><span>文笔坐标 2026.10.17</span></div></div>'''
    return page('文笔坐标 裁判', body)



# ---- 分榜：每个模块 / 维度单独一页 ----
import csv as _csv, glob as _glob
_L = _glob.glob('/Volumes/*/Projects/llmtest')[0]
QTITLE = {}
for _f in _glob.glob(f'{_L}/手动评分/00_题目/T-*.md'):
    _h = open(_f, encoding='utf-8').readline().strip()
    _q, _, _t = _h[3:].partition('｜')
    QTITLE[_q] = _t

_PQ = {}  # (key, 题号, 模型) -> [分数...]（剔除自评）
for _r in _csv.DictReader(open(f'{OUT}/明细_逐题逐裁判.csv', encoding='utf-8-sig')):
    if _r['自评'] == '1' or _r['模型'] not in models:
        continue
    for _k in DIMS + ['专项分', '总分']:
        if _r[_k]:
            _PQ.setdefault((_k, _r['题号'], _r['模型']), []).append(float(_r[_k]))


def spread_qs(key, qfilter, n=8):
    """该项里模型间分差最大的题：每题各模型先对裁判取均值，再看最高-最低。"""
    out = []
    for q in sorted(QTITLE):
        if not qfilter(q):
            continue
        sc = {m: st.mean(_PQ[key, q, m]) for m in models if (key, q, m) in _PQ}
        if len(sc) < 5:
            continue
        hi_m, lo_m = max(sc, key=sc.get), min(sc, key=sc.get)
        out.append((sc[hi_m] - sc[lo_m], q, hi_m, sc[hi_m], lo_m, sc[lo_m]))
    return sorted(out, reverse=True)[:n]


def split_page(kicker, title, sub, err, key, qfilter):
    order = sorted(models, key=lambda m: -err[m][0])
    lo, hi = scale_of([err[m] for m in order])
    rows = ''.join(
        f'<tr><td style="width:46px;color:#8a91a0;font-size:26px">{i}</td><td style="white-space:nowrap;padding:5px 6px">'
        f'<div style="display:flex;align-items:center;gap:12px;font-size:26px">{logo(MLOGO[m], 30) or SPACER}{esc(NAMES[m][0])}</div>'
        f'<div style="margin:2px 0 0 42px;font-size:17px;color:#8a91a0;display:flex;align-items:center;gap:6px">'
        f'{logo(HARNESS[ENV[m][0]][1], 19, "border-radius:4px")}{HARNESS[ENV[m][0]][0]}{" · " + ENV[m][1] if ENV[m][1] else ""}</div></td>'
        f'<td>{rng(*err[m], lo, hi, w=360, h=40)}</td>'
        f'<td class="n" style="font-size:38px;font-weight:600"><span class="cnt">{err[m][0]:.2f}</span></td></tr>'
        for i, m in enumerate(order, 1))
    qs = spread_qs(key, qfilter)
    qrows = ''.join(
        f'<tr><td style="font-size:20px;color:#8a91a0;width:84px">{q}</td>'
        f'<td style="font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:330px">{esc(QTITLE[q])}</td>'
        f'<td class="n" style="font-size:22px">{logo(MLOGO[hm], 24) or SPACER} {hv:.1f}</td>'
        f'<td class="n" style="font-size:22px;color:#8a91a0">{logo(MLOGO[lm], 24) or SPACER} {lv:.1f}</td>'
        f'<td class="n" style="font-size:24px;font-weight:600">{d:.1f}</td></tr>'
        for d, q, hm, hv, lm, lv in qs)
    overall = {o['模型']: o['排名'] for o in board}
    shift = ''
    for i, m in enumerate(sorted(models, key=lambda m: overall[m]), 0):
        here = order.index(m) + 1
        dlt = overall[m] - here
        col, arr = ('#3f8f6b', f'↑{dlt}') if dlt > 0 else (('#c4573f', f'↓{-dlt}') if dlt < 0 else ('#9aa1ae', '—'))
        shift += (f'<div class="tile" style="display:flex;align-items:center;gap:10px">{logo(MLOGO[m], 30) or SPACER}'
                  f'<div style="min-width:0"><div class="tg" style="margin:0;font-size:16px">{esc(NAMES[m][0])}</div>'
                  f'<div style="font-size:24px;font-weight:600;color:{col}">{arr}<span style="font-size:16px;color:#8a91a0;font-weight:400;margin-left:6px">#{overall[m]}→#{here}</span></div></div></div>')
    body = f'''<div class="card"><div class="top"><span>{kicker}</span><span class="brand">文笔坐标</span></div>
<h1>{title}<span style="font-size:30px;color:#8a91a0;margin-left:18px;font-weight:400">{sub}</span></h1>
<div class="panel" style="padding:18px 28px"><table>{rows}</table>
<table><tr><td style="border:none;width:46px"></td><td style="border:none"></td><td style="border:none;width:360px">{axis(lo, hi, 360)}</td><td style="border:none;width:104px"></td></tr></table></div>
<div class="panel" style="padding:20px 28px"><div class="pt">最拉开差距的题</div>
<table style="table-layout:fixed"><colgroup><col style="width:84px"><col><col style="width:110px"><col style="width:110px"><col style="width:70px"></colgroup>
<tr><td style="border:none"></td><td style="border:none"></td><td class="n" style="border:none;font-size:17px;color:#8a91a0">最高</td><td class="n" style="border:none;font-size:17px;color:#8a91a0">最低</td><td class="n" style="border:none;font-size:17px;color:#8a91a0">分差</td></tr>{qrows}</table></div>
<div class="panel" style="padding:20px 28px"><div class="pt">对比总榜名次</div><div class="tiles">{shift}</div></div>
{FOOT}</div>'''
    return page(f'文笔坐标 {title}', body)


MOD_FULL = {k: v for k, v in MODS.items()}
nq_mod = {k: sum(1 for q in QTITLE if q[2] == k) for k in MODS}
SPLIT = []
for i, k in enumerate(MODS):
    SPLIT.append((f'2{i}_模块{k}_{MOD_SHORT[k]}',
                  split_page('分榜 · 模块', f'{k} {MOD_FULL[k]}', f'{nq_mod[k]} 题', D['mod_err'][k], '总分', lambda q, k=k: q[2] == k)))
for i, (d, sh) in enumerate(zip(DIMS + ['专项分'], SHORT + ['专项分']), 0):
    SPLIT.append((f'{40 + i}_维度_{sh}',
                  split_page('分榜 · 维度', d if d != '专项分' else '专项分', '通用十维' if d != '专项分' else '对照评分要点', D['dim_err'][d], d, lambda q: True)))


pages = [('00_总榜', board_page())]
pages += [(f'{i:02d}_{NAMES[o["模型"]][0]}', model_card(o)) for i, o in enumerate(board, 1)]
pages.append(('90_模块榜', heat_page('模块', list(MODS), [MOD_SHORT[k] for k in MODS], D['mod'], list(MODS), [MOD_SHORT[k] for k in MODS])))
pages.append(('91_维度榜', heat_page('维度', DIMS + ['专项分'], SHORT + ['专项'], D['dim'], DIMS, SHORT)))
pages.append(('92_裁判', judge_page()))
pages += SPLIT
for name, h in pages:
    open(f'{CARD_DIR}/{name}.html', 'w', encoding='utf-8').write(h)
inner = ''.join(h.split('<body>')[1].split('</body>')[0] for _, h in pages)
open(f'{OUT}/文笔坐标.html', 'w', encoding='utf-8').write(page('文笔坐标', f'<div style="display:flex;flex-direction:column;align-items:center;gap:40px;padding:40px 0">{inner}</div>'))
print(len(pages), 'pages')
