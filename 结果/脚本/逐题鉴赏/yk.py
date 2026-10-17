"""逐题鉴赏视频（优库里解说风格，竖屏 1080×1920）。

三位裁判 Claude Opus 5.5 / Gemini 4 Argon / DeepSeek V4 Pro 以小头像出镜，轮流读自己的点评（edge-tts 配音），
说话者的头像跟随音量弹跳、拉伸。画面：题目卡 → 按得分从低到高逐个作答卡（点评引用原句高亮 + 三人维度得分）→ 本题排名。

用法: python3 yk.py <题号> <输出mp4>
"""
import base64, csv, glob, hashlib, html, json, math, os, re, statistics as st, subprocess, sys, wave
from array import array
from PIL import Image

QID, OUT_MP4 = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
SUM = glob.glob('/Volumes/*/影片/文笔/汇总')[0]
PROJ = os.path.dirname(SUM)
LLM = glob.glob('/Volumes/*/Projects/llmtest')[0]
PACK = '/Users/bemly/Documents/opus5.5/手动评分/01_盲评包'
EDGE = os.path.join(HERE, 'venv/bin/edge-tts')
WORK = os.path.join(HERE, 'work', QID)
os.makedirs(WORK, exist_ok=True)
CACHE = os.path.join(HERE, 'tts_cache')
os.makedirs(CACHE, exist_ok=True)
esc = html.escape
FPS, SR, GAP = 30, 24000, 0.28

# ---------- 角色 ----------
CAST = {  # 裁判目录名 -> 角色
    'opus5.5': dict(name='Claude', full='Claude Opus 5.5', img='Claude', color='#d9773f',
                    voice='zh-CN-XiaoxiaoNeural', pitch='+35Hz', rate='+14%', self='claude-opus-5-5'),
    'gemini4': dict(name='Gemini', full='Gemini 4 Argon', img='Gemini', color='#7b5cf0',
                    voice='manbo', pitch='', rate='+10', self='gemini-4-argon-contributor'),  # 曼波 TTS（MiloraAPI）
    'dsv4p': dict(name='DeepSeek', full='DeepSeek V4 Pro', img='DeepSeek', color='#3a5fc8',
                  voice='zh-CN-XiaoyiNeural', pitch='+20Hz', rate='+12%', self='deepseek-v4-pro'),
}
ORDER = ['opus5.5', 'gemini4', 'dsv4p']

NAMES = {
    'claude-opus-5-5': 'Claude Opus 5.5', 'gemini-4-argon-contributor': 'Gemini 4 Argon',
    'Muse Spark 1.2 Contributor': 'Muse Spark 1.2', 'deepseek-v4-pro': 'DeepSeek V4 Pro 0813',
    'Muse-Spark-1.3-Free': 'Muse Spark 1.3', 'LongCat-2.0': 'LongCat 2.0', 'space-bunny-free': 'space-bunny',
    'gemini-3.7-flash': 'Gemini 3.7 Flash', 'LongCat-2.5-Preview-Free': 'LongCat 2.5 Preview', 'Qwen3.6-27B-FP8': 'Qwen3.6 27B',
}
SPOKEN = {  # 念给 TTS 的名字
    'claude-opus-5-5': 'Claude Opus 五点五', 'gemini-4-argon-contributor': 'Gemini 4 Argon',
    'Muse Spark 1.2 Contributor': 'Muse Spark 一点二', 'deepseek-v4-pro': 'DeepSeek V4 Pro',
    'Muse-Spark-1.3-Free': 'Muse Spark 一点三', 'LongCat-2.0': 'LongCat 二点零', 'space-bunny-free': 'space bunny',
    'gemini-3.7-flash': 'Gemini 三点七 Flash', 'LongCat-2.5-Preview-Free': 'LongCat 二点五 Preview', 'Qwen3.6-27B-FP8': '千问三点六',
}
MLOGO = {'claude-opus-5-5': 'claude-color.svg', 'gemini-4-argon-contributor': 'gemini-color.svg', 'gemini-3.7-flash': 'gemini-color.svg',
         'Muse Spark 1.2 Contributor': 'muse.png', 'Muse-Spark-1.3-Free': 'muse.png', 'deepseek-v4-pro': 'deepseek-color.svg',
         'LongCat-2.0': 'longcat-color.svg', 'LongCat-2.5-Preview-Free': 'longcat-color.svg', 'Qwen3.6-27B-FP8': 'qwen-color.svg',
         'space-bunny-free': None}
DIMS = ['指令遵循', '文笔与文气', '活人感去AI味', '结构与节奏', '人物与对白', '逻辑与一致性', '吸引力可读性', '文体类型契合', '信息密度', '准确与诚实']
SHORT = ['遵循', '文笔', '活人', '结构', '人物', '逻辑', '吸引', '文体', '密度', '准确']


def uri(path):
    mime = 'image/svg+xml' if path.endswith('.svg') else 'image/png'
    return f'data:{mime};base64,{base64.b64encode(open(path, "rb").read()).decode()}'


def mlogo(m, h):
    f = MLOGO.get(m)
    return f'<img src="{uri(os.path.join(SUM, "_logos", f))}" style="height:{h}px;vertical-align:middle">' if f else ''


# ---------- 头像 ----------
AV = {}
for j, c in CAST.items():
    p = os.path.join(WORK, '..', f'{c["img"]}.png')
    if not os.path.exists(p):
        subprocess.run(['sips', '-s', 'format', 'png', os.path.join(PROJ, c['img'] + '.avif'), '--out', p], check=True, capture_output=True)
    AV[j] = Image.open(p).convert('RGBA')

# ---------- 数据 ----------
rows = [r for r in csv.DictReader(open(os.path.join(SUM, '明细_逐题逐裁判.csv'), encoding='utf-8-sig')) if r['题号'] == QID]
prompt_md = open(glob.glob(f'{LLM}/手动评分/00_题目/{QID}.md')[0], encoding='utf-8').read()
title = prompt_md.splitlines()[0].split('｜', 1)[1].strip()
user_blocks = re.findall(r'```user\n(.*?)```', prompt_md, re.S)
prompt_text = user_blocks[0].strip() if user_blocks else ''
rounds = len(user_blocks)
_rub = open(f'/Users/bemly/Documents/opus5.5/手动评分/参考/评分要点/{QID}.md', encoding='utf-8').read()
_m = re.search(r'考察：(.*?)｜\s*难度：(\S+)', _rub)
focus, level = (_m.group(1).strip(), _m.group(2)) if _m else ('', '')
points = [re.sub(r'\*\*', '', l[2:].strip()) for l in _rub.split('**评分要点**', 1)[-1].splitlines() if l.startswith('- ')]

models = sorted({r['模型'] for r in rows})
avg = {}
for m in models:
    v = [float(r['总分']) for r in rows if r['模型'] == m and r['自评'] == '0']
    avg[m] = st.mean(v)
order = sorted(models, key=lambda m: avg[m])            # 从低到高
rank = {m: i + 1 for i, m in enumerate(sorted(models, key=lambda m: -avg[m]))}
anon = {r['模型']: r['匿名ID'] for r in rows}
by = {(r['模型'], r['裁判']): r for r in rows}


def answer_text(m):
    return open(os.path.join(PACK, QID, anon[m] + '.md'), encoding='utf-8').read()


def excerpt(m):
    """点评里引用的原句若能在作答中找到，取所在句并高亮；否则取开头正文。"""
    txt = answer_text(m)
    quotes = []
    for j in ORDER:
        r = by.get((m, j))
        if r:
            quotes += re.findall(r'[“"「]([^”"」]{3,40})[”"」]', r['点评'])
    lines = [l.strip() for l in txt.splitlines() if l.strip() and not l.lstrip().startswith(('#', '>', '|', '---', '```', '**风格', '- **'))]
    picked = []
    for q in quotes:
        core = q.strip('…. ')
        for l in lines:
            if core and core in l and l not in [p[0] for p in picked]:
                picked.append((l, core))
                break
        if len(picked) == 5:
            break
    out = []
    for l, core in picked:
        i = l.find(core)
        s, e = max(0, i - 60), min(len(l), i + len(core) + 60)
        seg = ('…' if s else '') + esc(l[s:i]) + f'<mark>{esc(core)}</mark>' + esc(l[i + len(core):e]) + ('…' if e < len(l) else '')
        out.append(seg)
    if len(''.join(out)) < 260:
        body = ''.join(l for l in lines[:6])[:260 - len(''.join(out)) + 60]
        out = [esc(body) + '…'] + out
    return out


def hanzi(m):
    return len(re.findall(r'[\u4e00-\u9fff]', answer_text(m)))


def speak_clean(t):
    t = re.sub(r'T-([A-J])(\d\d)', r'\1\2', t)
    t = t.replace('M0', 'M').replace('~', '到')
    return t


# ---------- 台词 ----------
lines = []  # (speaker, text, scene)
lines.append(('opus5.5', f'大家好，这里是文笔坐标逐题鉴赏。今天这道是 {QID[2:]}，{title}。', ('q',)))
first_req = re.split(r'[。\n]', prompt_text)[0]
lines.append(('gemini4', f'题目要求：{first_req}。' + (f'本题一共 {rounds} 轮。' if rounds > 1 else ''), ('q',)))
lines.append(('dsv4p', f'一共 {len(models)} 份作答。我们按得分从低到高，一份一份看。', ('q',)))
for m in order:
    lines.append(('opus5.5', f'第 {rank[m]} 名，{SPOKEN[m]}，平均 {avg[m]:.1f} 分。', ('a', m, None)))
    for j in ORDER:
        r = by.get((m, j))
        if not r or not r['点评']:
            continue
        pre = '这是我自己的作答，自评不计分。' if CAST[j]['self'] == m else ''
        lines.append((j, pre + speak_clean(r['点评']), ('a', m, j)))
top, bottom = order[-1], order[0]
lines.append(('gemini4', f'本题第一名是 {SPOKEN[top]}，{avg[top]:.1f} 分；最后一名是 {SPOKEN[bottom]}，{avg[bottom]:.1f} 分。', ('r',)))
lines.append(('dsv4p', '以上就是本题的鉴赏。', ('r',)))
lines.append(('opus5.5', '我们下期见，拜拜～', ('r',)))


# ---------- TTS ----------
import time, urllib.parse, urllib.request
MANBO_KEY = os.environ.get('MANBO_KEY', '')


def manbo(text, speed, out):
    """曼波 TTS：与 xmimu/manbo-tts 相同的 MiloraAPI 接口；免费每 IP 每天 50 次，设置 MANBO_KEY 走 VIP 接口。"""
    q = {'text': text, 'format': 'mp3', 'speed': speed.lstrip('+')}
    url = 'https://api.milorapart.top/apis/mbAIsc'
    hdr = {}
    if MANBO_KEY:
        q['key'] = MANBO_KEY
        url = 'https://api.milorapart.top/apis/mbAIscvip'
        hdr['Authorization'] = f'Bearer {MANBO_KEY}'
    for attempt in range(4):
        try:
            req = urllib.request.Request(url + '?' + urllib.parse.urlencode(q), headers=hdr)
            js = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if js.get('code') != 200:
                raise RuntimeError(f'曼波接口返回 {js.get("code")}：{js.get("msg")}')
            data = urllib.request.urlopen(js['url'], timeout=60).read()
            open(out, 'wb').write(data)
            return
        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(2 + attempt * 2)

def tts(j, text):
    c = CAST[j]
    key = hashlib.md5(f'{c["voice"]}{c["pitch"]}{c["rate"]}{text}'.encode()).hexdigest()
    mp3 = os.path.join(CACHE, key + '.mp3')
    if not os.path.exists(mp3) and c['voice'] == 'manbo':
        manbo(text, c['rate'], mp3)
    if not os.path.exists(mp3):
        subprocess.run([EDGE, '--voice', c['voice'], f'--pitch={c["pitch"]}', f'--rate={c["rate"]}', '--text', text, '--write-media', mp3],
                       check=True, capture_output=True)
    pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', mp3, '-f', 's16le', '-ac', '1', '-ar', str(SR), '-'])
    a = array('h'); a.frombytes(pcm)
    return a


clips = []
for j, text, scene in lines:
    clips.append(tts(j, text))
print('tts done', len(clips))


def envelope(a):
    hop = SR // FPS
    env = []
    for i in range(0, len(a), hop):
        seg = a[i:i + hop]
        env.append(math.sqrt(sum(x * x for x in seg) / max(1, len(seg))))
    ref = sorted(env)[int(len(env) * .95)] or 1
    out, s = [], 0.0
    for e in env:
        v = min(1.0, e / ref)
        s = v if v > s else s * 0.82 + v * 0.18      # 快起慢落
        out.append(s)
    return out


# ---------- 场景 ----------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1920px;background:#eceef2;font-family:"PingFang SC","Hiragino Sans GB",sans-serif;color:#1b2230;overflow:hidden}
.top{position:absolute;left:56px;right:56px;top:46px;display:flex;justify-content:space-between;font-size:24px;color:#8a91a0}
.brand{color:#1b2230;letter-spacing:9px;font-weight:600;font-size:28px}
.qt{position:absolute;left:56px;right:56px;top:96px;font-size:56px;font-weight:600;line-height:1.15}
.qt small{font-size:28px;color:#8a91a0;font-weight:400;margin-right:14px}
.card{position:absolute;left:44px;right:44px;top:210px;height:950px;background:#fff;border-radius:26px;padding:34px 38px;overflow:hidden}
.mh{display:flex;align-items:center;gap:16px;font-size:44px;font-weight:600}
.badge{margin-left:auto;font-size:26px;color:#4a6fb0;font-weight:600}
.big{font-size:76px;font-weight:700;margin-left:6px}
.ex{position:absolute;left:38px;right:38px;top:212px;height:484px}
.tbl{position:absolute;left:38px;right:38px;top:716px}
.ex p{margin-bottom:14px;padding-left:18px;border-left:5px solid #e6e9ef}
mark{background:linear-gradient(transparent 55%,#ffe3a3 55%);color:inherit;padding:0 2px}
table{border-collapse:separate;border-spacing:4px;width:100%;margin-top:18px}
th{font-size:19px;color:#8a91a0;font-weight:400}
td{text-align:center;font-size:22px;border-radius:8px;padding:7px 0;font-variant-numeric:tabular-nums}
td.j{text-align:left;font-size:21px;white-space:nowrap;padding-left:2px}
td.j img{height:34px;width:34px;border-radius:50%;vertical-align:middle;margin-right:6px;object-fit:cover;background:#f1f3f7}
.bub{position:absolute;left:44px;right:44px;top:1186px;height:250px;background:#fff;border-radius:26px;border:5px solid;padding:24px 32px;font-size:33px;line-height:1.5;display:flex;align-items:center}
.bub:after{content:"";position:absolute;bottom:-26px;width:0;height:0;border:22px solid transparent;border-top:26px solid;border-bottom:0}
.who{position:absolute;top:-22px;left:26px;font-size:22px;color:#fff;padding:3px 16px;border-radius:999px}
.tag{position:absolute;top:1880px;width:300px;text-align:center;font-size:22px;color:#8a91a0}
.prompt{margin-top:18px;font-size:27px;line-height:1.6;white-space:pre-wrap;color:#2a3140}
.rk td{font-size:30px;text-align:left;padding:10px 6px;border-bottom:1px solid #eef0f4;border-radius:0}
"""
XS = {'opus5.5': 200, 'gemini4': 540, 'dsv4p': 880}


def heat(v):
    t = max(0, min(1, (v - 2) / 7))
    r, g, b = int(240 + (74 - 240) * t), int(214 + (111 - 214) * t), int(196 + (176 - 196) * t)
    return f'background:rgb({r},{g},{b});color:{"#fff" if t > .55 else "#1b2230"}'


def score_table(m):
    head = '<tr><th></th>' + ''.join(f'<th>{s}</th>' for s in SHORT) + '<th>专项</th><th>总分</th></tr>'
    body = ''
    for j in ORDER:
        r = by.get((m, j))
        if not r:
            continue
        av = os.path.join(WORK, '..', f'{CAST[j]["img"]}.png')
        cells = ''
        for k in DIMS + ['专项分', '总分']:
            v = r[k]
            cells += f'<td style="{heat(float(v))}">{float(v):g}</td>' if v else '<td style="background:#f4f5f8;color:#c0c5cf">—</td>'
        selfmark = '*' if CAST[j]['self'] == m else ''
        body += f'<tr><td class="j"><img src="{uri(av)}">{CAST[j]["name"]}{selfmark}</td>{cells}</tr>'
    return f'<table>{head}{body}</table>'


def bubble(j, text):
    c = CAST[j]
    x = XS[j] - 44 - 22
    fs = 33 if len(text) <= 80 else (29 if len(text) <= 110 else (26 if len(text) <= 140 else 23))
    return (f'<div class="bub" style="border-color:{c["color"]};font-size:{fs}px"><span class="who" style="background:{c["color"]}">{c["name"]}</span>{esc(text)}'
            f'<style>.bub:after{{left:{x}px;border-top-color:{c["color"]}}}</style></div>')


def tags():
    return ''.join(f'<div class="tag" style="left:{XS[j] - 150}px">{CAST[j]["full"]}</div>' for j in ORDER)


def scene_html(j, text, scene):
    head = f'<div class="top"><span>逐题鉴赏 · 三人点评</span><span class="brand">文笔坐标</span></div><div class="qt"><small>{QID}</small>{esc(title)}</div>'
    if scene[0] == 'q':
        p = prompt_text if len(prompt_text) < 520 else prompt_text[:520] + '…'
        pts = ''.join(f'<li>{esc(x)}</li>' for x in points[:6])
        card = (f'<div class="card"><div style="font-size:26px;color:#8a91a0">题目 · {len(models)} 份作答' + (f' · {rounds} 轮' if rounds > 1 else '') + '</div>'
                f'<div class="prompt" style="max-height:470px;overflow:hidden">{esc(p)}</div>'
                f'<div style="margin-top:22px;display:flex;gap:12px;flex-wrap:wrap">' + ''.join(f'<span style="background:#eef2fb;color:#4a6fb0;border-radius:999px;padding:6px 16px;font-size:23px">{esc(x.strip())}</span>' for x in focus.split('·') if x.strip()) +
                f'<span style="background:#fdf1e7;color:#c96a2a;border-radius:999px;padding:6px 16px;font-size:23px">难度 {esc(level)}</span></div>'
                f'<div style="margin-top:20px;font-size:24px;color:#8a91a0">评分要点</div><ul style="margin:8px 0 0 30px;font-size:25px;line-height:1.55;color:#2a3140">{pts}</ul></div>')
    elif scene[0] == 'a':
        m = scene[1]
        card = (f'<div class="card"><div class="mh">{mlogo(m, 50)}{esc(NAMES[m])}<span class="badge">第 {rank[m]} 名 / {len(models)}</span></div>'
                f'<div style="display:flex;align-items:baseline;gap:10px;margin-top:6px;color:#8a91a0;font-size:24px">平均<span class="big" style="color:#1b2230">{avg[m]:.2f}</span>（剔除自评） · {hanzi(m)} 字</div>'
                f'<div class="ex"></div><div class="tbl">{score_table(m)}</div></div>')
    else:
        rk = ''.join(f'<tr><td style="width:60px;color:#8a91a0">{rank[m]}</td><td>{mlogo(m, 34)} {esc(NAMES[m])}</td>'
                     f'<td style="width:42%"><div style="height:16px;border-radius:8px;background:#4a6fb0;width:{avg[m] / 10 * 100:.0f}%"></div></td>'
                     f'<td style="text-align:right;font-weight:600">{avg[m]:.2f}</td></tr>'
                     for m in sorted(models, key=lambda m: -avg[m]))
        card = f'<div class="card"><div style="font-size:26px;color:#8a91a0">本题排名</div><table class="rk">{rk}</table></div>'
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{head}{card}{bubble(j, text)}{tags()}</body></html>'


shots = []
for i, (j, text, scene) in enumerate(lines):
    h = os.path.join(WORK, f's{i:03d}.html')
    open(h, 'w', encoding='utf-8').write(scene_html(j, text, scene))
    shots.append([h, os.path.join(WORK, f's{i:03d}.png')])
json.dump(shots, open(os.path.join(WORK, 'shots.json'), 'w'))
npm_root = subprocess.check_output(['npm', 'root', '-g'], text=True).strip()
subprocess.run(['node', os.path.join(HERE, 'shot.js'), os.path.join(WORK, 'shots.json')], check=True, env={**os.environ, 'NODE_PATH': npm_root})
print('scenes done')

# ---------- 全文长图（滚动用） ----------
EX_X, EX_Y, EX_W, EX_H = 82, 422, 916, 484
FULL_CSS = ('*{margin:0;padding:0;box-sizing:border-box}body{width:916px;background:#fff;font-family:"PingFang SC","Hiragino Sans GB",sans-serif;'
            'color:#2a3140;font-size:30px;line-height:1.66;padding:6px 0 40px}p{margin-bottom:14px;padding-left:18px;border-left:5px solid #e6e9ef}'
            'p.h{border-left-color:#c9d3e8;font-weight:600;color:#1b2230}mark{background:linear-gradient(transparent 55%,#ffe3a3 55%);color:inherit;padding:0 2px}')


def full_html(m):
    cores = []
    for j in ORDER:
        r = by.get((m, j))
        if r:
            cores += [q.strip('…. ') for q in re.findall(r'[“"「]([^”"」]{3,40})[”"」]', r['点评'])]
    cores = sorted({c for c in cores if c}, key=len, reverse=True)
    out = ''
    for l in answer_text(m).splitlines():
        l = l.strip()
        if not l or l.startswith(('```', '---', '|---')):
            continue
        head = l.startswith('#')
        l = re.sub(r'^#+\s*|\*\*', '', l)
        e = esc(l)
        for c in cores:
            ec = esc(c)
            if ec in e:
                e = e.replace(ec, f'<mark>{ec}</mark>', 1)
        out += f'<p class="{"h" if head else ""}">{e}</p>'
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{FULL_CSS}</style></head><body>{out}</body></html>'


fulls, FULL = [], {}
for m in models:
    h = os.path.join(WORK, f'full_{anon[m]}.html')
    open(h, 'w', encoding='utf-8').write(full_html(m))
    FULL[m] = os.path.join(WORK, f'full_{anon[m]}.png')
    fulls.append([h, FULL[m], EX_W])
json.dump(fulls, open(os.path.join(WORK, 'fulls.json'), 'w'))
subprocess.run(['node', os.path.join(HERE, 'shot.js'), os.path.join(WORK, 'fulls.json')], check=True, env={**os.environ, 'NODE_PATH': npm_root})
FULL = {m: Image.open(p).convert('RGB') for m, p in FULL.items()}
print('full texts done')

# ---------- 音轨 + 时间线 ----------
gap = array('h', [0] * int(SR * GAP))
audio = array('h')
segs = []  # (speaker, start_frame, env)
concat = []
for i, ((j, text, scene), a) in enumerate(zip(lines, clips)):
    start = len(audio) / SR
    audio += a; audio += gap
    dur = len(a) / SR + GAP
    segs.append((j, round(start * FPS), envelope(a), scene, round((start + dur) * FPS)))
    concat.append(f"file '{shots[i][1]}'\nduration {dur:.4f}")
concat.append(f"file '{shots[-1][1]}'")
open(os.path.join(WORK, 'scenes.txt'), 'w').write('\n'.join(concat) + '\n')
wav = os.path.join(WORK, 'voice.wav')
with wave.open(wav, 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(audio.tobytes())
total_frames = math.ceil(len(audio) / SR * FPS)

# ---------- 头像动画 ----------
STRIP_Y, STRIP_H, SIZE = 1450, 430, 300
base = {j: AV[j].resize((SIZE, SIZE), Image.LANCZOS) for j in ORDER}
speak = [None] * total_frames
level = [0.0] * total_frames
for j, f0, env, _sc, _f1 in segs:
    for k, e in enumerate(env):
        if f0 + k < total_frames:
            speak[f0 + k] = j
            level[f0 + k] = e

# 每份作答的时间段 → 滚动
scroll_of = [None] * total_frames
blocks = {}
for j, f0, env, sc, f1 in segs:
    if sc[0] == 'a':
        b = blocks.setdefault(sc[1], [f0, f1]); b[0] = min(b[0], f0); b[1] = max(b[1], f1)
for m, (b0, b1) in blocks.items():
    for f in range(b0, min(b1, total_frames)):
        scroll_of[f] = (m, b0, b1)
mask = Image.new('L', (EX_W, EX_H), 255)
for yy in range(EX_H):
    a = min(1.0, yy / 26, (EX_H - 1 - yy) / 70)
    mask.paste(int(255 * max(0, a)), (0, yy, EX_W, yy + 1))
blank_text = bytes(EX_W * EX_H * 4)
fifo = os.path.join(WORK, 'text.fifo')
if os.path.exists(fifo):
    os.remove(fifo)
os.mkfifo(fifo)

proc = subprocess.Popen([
    'ffmpeg', '-y', '-v', 'error',
    '-f', 'concat', '-safe', '0', '-i', os.path.join(WORK, 'scenes.txt'),
    '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'1080x{STRIP_H}', '-r', str(FPS), '-i', '-',
    '-i', wav,
    '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{EX_W}x{EX_H}', '-r', str(FPS), '-i', fifo,
    '-filter_complex', f'[0:v]fps={FPS},format=rgba[bg];[bg][3:v]overlay={EX_X}:{EX_Y}:format=auto[t];[t][1:v]overlay=0:{STRIP_Y}:format=auto,format=yuv420p[v]',
    '-map', '[v]', '-map', '2:a', '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'medium', '-crf', '20',
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-shortest', '-movflags', '+faststart', OUT_MP4,
], stdin=subprocess.PIPE)

import threading


def text_writer():
    with open(fifo, 'wb') as fh:
        for f in range(total_frames):
            sc = scroll_of[f]
            if not sc:
                fh.write(blank_text); continue
            m, b0, b1 = sc
            img = FULL[m]
            span = max(0, img.height - EX_H)
            p = min(1.0, max(0.0, (f - b0 - FPS) / max(1, b1 - b0 - FPS * 2.5)))
            p = p * p * (3 - 2 * p)
            off = int(span * p)
            crop = img.crop((0, off, EX_W, off + EX_H))
            if crop.height < EX_H:
                pad = Image.new('RGB', (EX_W, EX_H), 'white'); pad.paste(crop, (0, 0)); crop = pad
            crop = crop.convert('RGBA'); crop.putalpha(mask)
            fh.write(crop.tobytes())


tw = threading.Thread(target=text_writer); tw.start()
phase = {j: 0.0 for j in ORDER}
for f in range(total_frames):
    t = f / FPS
    strip = Image.new('RGBA', (1080, STRIP_H), (0, 0, 0, 0))
    for idx, j in enumerate(ORDER):
        e = level[f] if speak[f] == j else 0.0
        if speak[f] == j:
            phase[j] += 3.2 / FPS                      # 每秒约 3.2 次弹跳
        p = abs(math.sin(math.pi * phase[j]))           # 0 落地 → 1 最高
        hop = 46 * p * e
        stretch = 1 + 0.16 * e * (p - 0.35)             # 空中拉长，落地压扁
        breath = 1 + 0.018 * math.sin(2 * math.pi * 0.45 * t + idx * 2.1)
        sy = stretch * breath
        sx = 1 / (stretch ** 0.7)
        scale = 1.0 if speak[f] == j else 0.9
        w, h = int(SIZE * sx * scale), int(SIZE * sy * scale)
        im = base[j].resize((w, h), Image.BILINEAR)
        if speak[f] not in (None, j):
            a = im.getchannel('A').point(lambda v: int(v * 0.72))
            im.putalpha(a)
        x = XS[j] - w // 2
        y = STRIP_H - 40 - h - int(hop)
        strip.alpha_composite(im, (x, max(0, y)))
    proc.stdin.write(strip.tobytes())
proc.stdin.close()
tw.join()
proc.wait()
os.remove(fifo)
print('done', OUT_MP4, f'{len(audio) / SR:.1f}s')
