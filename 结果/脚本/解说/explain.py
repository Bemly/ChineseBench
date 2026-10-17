"""评分规则解说：生成竖版幻灯片 HTML + 旁白文本。用法: explain.py <输出目录> <anim.js> <logos目录>"""
import base64, html, json, os, sys

OUT, ANIM, LOGOS = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)
JS = open(ANIM, encoding='utf-8').read()
esc = html.escape


def lg(f, h):
    raw = open(os.path.join(LOGOS, f), 'rb').read()
    mime = 'image/svg+xml' if f.endswith('.svg') else 'image/png'
    return f'<img src="data:{mime};base64,{base64.b64encode(raw).decode()}" style="height:{h}px;vertical-align:middle">'


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eceef2;font-family:"PingFang SC","Hiragino Sans GB",system-ui,sans-serif;color:#1b2230}
.card{width:1080px;height:1920px;padding:80px 64px;display:flex;flex-direction:column;gap:34px;overflow:hidden}
.top{display:flex;justify-content:space-between;font-size:26px;color:#8a91a0}
.brand{font-size:30px;color:#1b2230;letter-spacing:10px;font-weight:600}
h1{font-size:96px;font-weight:600;line-height:1.1}
.lead{font-size:42px;color:#4b5263;line-height:1.5}
.panel{background:#fff;border-radius:22px;padding:30px 34px}
.pt{font-size:24px;color:#8a91a0;margin-bottom:14px}
.tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.tile{background:#f6f7fa;border-radius:18px;padding:34px 28px}
.tile b{display:block;font-size:64px;color:#4a6fb0}
.tile span{font-size:32px;color:#4b5263}
table{width:100%;border-collapse:collapse}
td{padding:30px 8px;border-bottom:1px solid #e6e9ef;font-size:38px;vertical-align:middle}
td.n{text-align:right;color:#8a91a0;font-size:28px}
.big{font-size:300px;font-weight:700;color:#4a6fb0;line-height:1}
.formula{font-size:58px;line-height:1.8;padding:60px 34px;text-align:center}
.formula em{font-style:normal;color:#4a6fb0;font-weight:700}
.grow{flex:1;display:flex;flex-direction:column;justify-content:center}
.grow table{flex:1;height:100%}
.grow td{font-size:36px;white-space:nowrap}
.grow td.n{font-size:27px}
.sub{margin-top:auto;background:#1b2230;color:#fff;border-radius:22px;padding:32px 34px;font-size:36px;line-height:1.55}
"""

MODELS = [('claude-color.svg', 'Claude Opus 5.5', 'Claude Code · High'),
          ('gemini-color.svg', 'Gemini 4 Argon', 'OpenCode · High'),
          ('muse.png', 'Muse Spark 1.2', 'OpenCode · xHigh'),
          ('deepseek-color.svg', 'DeepSeek V4 Pro 0813', 'DeepSeek Harness · High'),
          ('muse.png', 'Muse Spark 1.3', 'OpenCode · xHigh'),
          ('longcat-color.svg', 'LongCat 2.0', 'OpenCode · Max'),
          (None, 'space-bunny', 'OpenCode · Max'),
          ('gemini-color.svg', 'Gemini 3.7 Flash', 'JetBrains Air · High'),
          ('longcat-color.svg', 'LongCat 2.5 Preview', 'OpenCode · Max'),
          ('qwen-color.svg', 'Qwen3.6 27B', 'Junie')]
JUDGES = [('claude-color.svg', 'Claude Opus 5.5'), ('gemini-color.svg', 'Gemini 4 Argon'), ('gemini-color.svg', 'Gemini 3.7 Flash'),
          ('muse.png', 'Muse Spark 1.2'), ('muse.png', 'Muse Spark 1.3'), ('deepseek-color.svg', 'DeepSeek V4 Pro')]
DIMS = ['指令遵循', '文笔与文气', '活人感 / 去AI味', '结构与节奏', '人物与对白', '逻辑与一致性', '吸引力', '文体契合', '信息密度', '准确与诚实']


def rows(items):
    return '<table>' + ''.join(f'<tr><td>{a}</td><td class="n">{b}</td></tr>' for a, b in items) + '</table>'


def tiles(items):
    return '<div class="tiles">' + ''.join(f'<div class="tile"><b>{a}</b><span>{b}</span></div>' for a, b in items) + '</div>'


S = []  # (标题小字, 标题, 主体 html, 旁白)
S.append(('评分规则解说', '文笔坐标<br>是怎么打分的',
          '<div class="panel"><div class="big">107</div><div class="lead" style="margin-top:12px">道中文创意写作题</div><div class="tiles" style="margin-top:40px"><div class="tile"><b>10</b><span>个模型作答</span></div><div class="tile"><b>6</b><span>位裁判盲评</span></div><div class="tile"><b>10</b><span>个模块</span></div><div class="tile"><b>6391</b><span>条打分记录</span></div></div></div>',
          '这一期把文笔坐标的评分规则完整讲一遍。从模型怎么作答、答卷怎么匿名，到裁判怎么打分、什么算硬伤、多语言题怎么分段，最后是分数怎么汇总。'))
S.append(('第一步 · 题库', '107 道题<br>10 个模块',
          '<div class="panel">' + tiles([('A', '语言基本功'), ('B', '叙事结构'), ('C', '人物与对白'), ('D', '类型文学 · 23 题'), ('E', 'RP 与互动'),
                                         ('F', '法学社科论文'), ('G', '长上下文续航'), ('H', '综合实验'), ('I', '去 AI 味'), ('J', '多语言与汉化')]) + '</div>'
          '<div class="panel">' + rows([('评分要点', '考什么、参考答案、典型失败'), ('check 配置', '目标字数、禁词、禁用句式')]) + '</div>',
          '题库一百零七道题，分十个模块。每道题都附有评分要点，写明考察什么、参考答案和典型的失败方式；大部分题还带有自动检查配置，比如目标字数、禁用词和禁用句式。'))
S.append(('第二步 · 作答', '10 个模型<br>在各自环境里答题',
          '<div class="panel">' + rows([(f'{lg(f, 44) if f else ""} {n}', e) for f, n, e in MODELS]).replace('<td', '<td style="padding:22px 8px"') + '</div>',
          '十个模型在各自常用的环境里作答，比如 Claude Code、OpenCode、JetBrains Air 和 DeepSeek Harness，推理强度从 High 到 Max 不等。'))
S.append(('作答规范', '这些行为<br>直接归零',
          '<div class="panel">' + rows([('修改题目', '作弊'), ('偷看其他模型的答案', '作弊'), ('使用 git、翻历史会话', '作弊'),
                                         ('联网搜索', '作弊'), ('读取项目以外的文件', '作弊')]) + '</div>'
          '<div class="panel">' + rows([('每题以 ## T-XXX 题头开头', '便于机械切割'), ('只写答案正文', '不写无关的脚手架')]) + '</div>',
          '作答时只能读项目以内的文件。修改题目、偷看其他模型的答案、使用 git 或翻历史会话、联网搜索、读取项目以外的文件，都按作弊处理，成绩归零。每个小题必须以题号题头开头，只写答案正文。'))
S.append(('作答规范', '答题卡<br>禁止带名字',
          '<div class="panel">' + rows([('署名行', '编剧：某某、以上由某某生成'), ('自报家门', '我是某某、作为某某模型'),
                                         ('推理与工具残留', 'think 标签、文件已写入'), ('本地路径', '一律不许泄露')]) + '</div>'
          '<div class="panel"><div class="lead">文件头只允许写「覆盖题目：T-XXX」，违反按作弊计。</div></div>',
          '为了保证盲评，答题卡里禁止出现任何模型名称和身份标记：署名行、自报家门、推理和工具残留，以及本地文件路径都不允许。文件头只能写覆盖了哪些题目。'))
S.append(('第三步 · 盲评准备', '切开、打乱<br>去掉名字',
          '<div class="panel">' + rows([('按题头切割', '原字节写入，不改一字'), ('删除署名残留 52 处', '只删签名，正文不动'),
                                         ('匿名编号 M01…', '每题重新洗牌'), ('洗牌种子每轮更换', '只有主会话知道'),
                                         ('记录 sha256', '核对盲评包没被改')]) + '</div>',
          '评分之前，脚本按题头把答卷原样切开，一个字都不改；遗留的五十二处署名残留只删签名行，正文不动。每份答卷换成匿名编号，编号每道题重新洗牌，洗牌种子只有主会话知道。每个文件记录哈希值，事后核对有没有被改动。'))
S.append(('第四步 · 互评', '6 位裁判<br>逐题盲评',
          '<div class="panel">' + rows([(f'{lg(f, 48)} {n}', '裁判') for f, n in JUDGES]).replace('<td', '<td style="padding:30px 8px"') + '</div>'
          '<div class="panel"><div class="lead">裁判也是参赛模型，所以汇总时要剔除自评。</div></div>',
          '六个参赛模型同时担任裁判。因为裁判也在参赛，汇总时会把它们给自己打的分剔除掉。'))
S.append(('裁判纪律', '只许读<br>只许写',
          '<div class="panel"><div class="pt">只许读</div>' + rows([('当前这道题', '一次只读一题'), ('该题评分要点', '专项分的依据'),
                                                                   ('该题全部匿名答卷', '盲评包'), ('评分量表、AI 味词典', '通用标准'),
                                                                   ('多语言规则', '仅 J 模块'), ('《阿Q正传》全文', '仅 G04 核对')]) + '</div>'
          '<div class="panel"><div class="pt">只许写</div><div class="lead">该题的记分表。读其他副本、联网、猜模型名、串供，成绩归零。</div></div>',
          '裁判同样有纪律。只许读当前这道题、它的评分要点、全部匿名答卷，以及评分量表和 AI 味词典；多语言题加读分段规则，长文阅读题加读阿Q正传原文。只许写这道题的记分表。读别的副本、联网、猜模型名或互相串供，都算作弊。'))
S.append(('评分步骤', '先拆清单<br>再逐份打分',
          '<div class="panel">' + rows([('① 读题，找出硬约束', '字数、禁词、视角、轮次'), ('② 要点拆成检查清单', '逐条勾选，记原文证据'),
                                         ('③ 每份独立打分', '再横向校准'), ('④ 字数禁词自己数', '不信作答自称已满足'),
                                         ('⑤ 多轮题逐轮查', '后面有没有忘记前文'), ('⑥ 自报家门一律忽略', '不加分也不扣分')]) + '</div>',
          '打分分六步。先读题，找出字数、禁词、视角这些硬约束；再把评分要点拆成检查清单，逐条勾选并记下原文证据；每份答卷先独立打分再横向校准；字数和禁词要自己数，不能相信作答自称已经满足；多轮题要逐轮检查有没有遗忘前文；答卷里的自报家门一律忽略。'))
S.append(('评分细则', '十个通用维度',
          '<div class="panel">' + tiles([('指令遵循', '字数、格式、禁词、视角'), ('文笔与文气', '准确、质感、节奏'), ('活人感', '像不像人写的'),
                                         ('结构与节奏', '切入、详略、转场'), ('人物与对白', '有辨识度、有潜台词'), ('逻辑一致', '设定、时间线、常识'),
                                         ('吸引力', '想不想读下去'), ('文体契合', '像不像要求的类型'), ('信息密度', '每句话都在干活'),
                                         ('准确与诚实', '不编造、不自引不实')]).replace('<b>', '<b style="font-size:40px">') + '</div>',
          '每份答卷先按十个通用维度打分，每项零到十分，和这道题无关的维度留空、不计入平均。从指令遵循、文笔文气、活人感，到结构节奏、人物对白、逻辑一致，再到吸引力、文体契合、信息密度和准确诚实。'))
S.append(('评分细则', '分档标准',
          '<div class="panel">' + rows([('<b style="color:#4a6fb0">9–10</b>', '出版水准，有让人记住的亮点'), ('<b style="color:#4a6fb0">7–8</b>', '扎实，偶有小瑕疵'),
                                         ('<b>5–6</b>', '及格，平庸或有套路感'), ('<b>3–4</b>', '多处违规、逻辑错误或严重 AI 味'),
                                         ('<b style="color:#c4573f">1–2</b>', '答非所问、大面积违规、严重编造'), ('<b style="color:#c4573f">0</b>', '拒答、截断无内容、乱码')]) + '</div>',
          '分档是统一的。九到十分是出版水准，七到八分扎实，五到六分及格但平庸，三到四分有明显缺陷，一到两分基本失败，零分是拒答或没有有效内容。不能因为篇幅长或辞藻华丽给高分。'))
S.append(('重点维度', '活人感<br>怎么扣分',
          '<div class="panel"><div class="pt">扣分</div>' + rows([('对比翻转', '不是……而是……密集'), ('金句体、规矩体', '怕吗？怕。宁可少挣也不能坏规矩'),
                                                                 ('无病呻吟', '命运、宇宙、或许这就是……吧'), ('伪精密意象', '第三根睫毛、0.3 毫米'),
                                                                 ('可互换的身体反应', '瞳孔微缩、指节发白'), ('老牌套话', '仿佛、一抹、命运的齿轮')]) + '</div>'
          '<div class="panel"><div class="pt">加分</div><div class="lead">人物有私心和失误 · 对话有岔题打断 · 细节只有见过才写得出 · 意外但合理 · 结尾克制</div></div>',
          '活人感是重点维度。对比翻转句密集、人物像在念格言的金句体、无病呻吟、伪精密意象、可以互换的身体反应、老牌套话，都会扣分。反过来，人物有私心和失误、对话有岔题和打断、细节具体到只有见过的人才写得出来、情节意外但合理、结尾克制，会加分。'))
S.append(('评分细则', '单题总分',
          '<div class="panel formula">总分 = <em>十维均分</em> × 0.5<br>+ <em>专项分</em> × 0.5</div>'
          '<div class="panel">' + rows([('专项分', '对照本题评分要点逐条打'), ('硬约束违规', '在专项分里重扣'), ('均分、总分', '保留一位小数')]) + '</div>',
          '单题总分等于十维均分和专项分各占一半。专项分对照这道题的评分要点逐条检查后给出，硬约束违规主要在专项分里扣。'))
S.append(('硬伤', '一票降档<br>专项分 ≤ 4',
          '<div class="panel">' + rows([('使用了明令禁止的写法', '如不许升华却升华'), ('编造法条、案号、文献、原著', '且未标注'),
                                         ('引用自己正文中不存在的句子', '自引不实'), ('多轮题忘记关键设定', '如写错主角惯用手'),
                                         ('输出截断、烂尾', '作品不完整')]) + '</div>'
          '<div class="panel"><div class="lead">编造与自引不实，「准确与诚实」一项同时不超过 3 分。</div></div>',
          '出现硬伤一票降档，专项分最高只给四分。硬伤包括：用了题目明令禁止的写法；编造法条、案号、文献或原著情节且没有标注；引用自己正文里根本不存在的句子；多轮题忘记关键设定；以及输出被截断、作品不完整。编造和自引不实，准确与诚实这一项同时不超过三分。'))
S.append(('多语言题', '分段评分',
          '<div class="panel">' + rows([('S 原 · 外语原文', '按该语言母语编辑标准'), ('S 汉 · 汉化译文', '当独立中文作品，看不到原文'),
                                         ('S 对 · 对照翻译', '忠实、风格、文化、语域、完整'), ('S 本 · 本土化', '是否真正长在中国语境里')]) + '</div>'
          '<div class="panel"><div class="lead">四段各自独立打分，避免一个总分把差别抹平。</div></div>',
          '先用外语写再汉化的题，分段评分。外语原文按该语言母语编辑的标准评；汉化译文当作一篇独立的中文作品评，裁判看不到原文；对照翻译从忠实、风格、文化负载词、语域和完整五个方面评；本土化重写看是否真正长在中国语境里。'))
S.append(('多语言题', '合成与诊断',
          '<div class="panel formula" style="font-size:44px">双语核心 = <em>0.35</em> 原 + <em>0.35</em> 汉 + <em>0.30</em> 对<br>J01–J06 = <em>0.8</em> 核心 + <em>0.2</em> 本<br>J09 = 0.3 英 + 0.3 日 + 0.4 对</div>'
          '<div class="panel">' + rows([('信达兼备', '对 ≥ 7 且 汉 ≥ 7'), ('漂亮但不忠实', '汉 ≥ 7 且 对 < 6'), ('忠实但翻译腔', '对 ≥ 7 且 汉 < 6'),
                                         ('汉化损耗大', '原 − 汉 ≥ 2'), ('外语原创是短板', '汉 − 原 ≥ 2')]) + '</div>',
          '四段分数按公式合成：原文、汉化、对照按零点三五、零点三五、零点三的权重合成双语核心分，含本土化的题再按八比二加入本土化分；中译外题按英译、日译和对照三比三比四合成。同时给出诊断标签，比如信达兼备、漂亮但不忠实、忠实但翻译腔。'))
S.append(('点评要求', '每条分数<br>都要有证据',
          '<div class="panel">' + rows([('一句话说明给分理由', '必须'), ('点名扣分最多的维度', '必须'), ('引用原文短句', '必须'),
                                         ('只喊口号', '禁止，如「文笔优美」')]) + '</div>',
          '每份打分都要附一句点评：说明给分理由，点名扣分最多的维度，并且引用原文短句作为证据。只喊文笔优美、感染力强这类口号是不允许的。'))
S.append(('第五步 · 汇总', '剔除自评<br>去掉极值',
          '<div class="panel"><div class="pt">示例 · Claude Opus 5.5</div>'
          '<svg width="880" height="120" viewBox="0 0 880 120"><line x1="120" y1="50" x2="760" y2="50" stroke="#c9ced8" stroke-width="16" stroke-linecap="round"/>'
          '<circle cx="640" cy="50" r="22" fill="#4a6fb0"/><text x="120" y="110" text-anchor="middle" font-size="30" fill="#8a91a0">7.28 最严</text>'
          '<text x="760" y="110" text-anchor="middle" font-size="30" fill="#8a91a0">8.85 最宽</text><text x="640" y="110" text-anchor="middle" font-size="34" font-weight="700" fill="#4a6fb0">8.45</text></svg></div>'
          '<div class="panel">' + rows([('① 剔除自评', '裁判给自己的分不算'), ('② 按裁判求均分', '每位裁判各算一个分'),
                                         ('③ 去掉最高、最低', '剩下的取平均'), ('④ 灰线', '最低到最高裁判分的范围')]) + '</div>',
          '汇总时，先剔除每位裁判给自己的分。然后对每个模型，按裁判分别算出均分，去掉最高和最低的那一位，剩下的取平均，就是榜单上的分数。旁边的灰线表示最严和最宽的裁判分别给了多少。'))
S.append(('怎么看卡片', '雷达图<br>两种颜色',
          '<div class="panel">' + rows([('<span style="color:#4a6fb0">●</span> 蓝色', '相对自身：哪几项是长板'),
                                         ('<span style="color:#e3a27a">●</span> 黄色', '对标全模型：单项排第几'),
                                         ('#名次', '这一项在 10 个模型里的排名')]) + '</div>',
          '模型卡片上的雷达图有两层。蓝色表示这个模型自己哪几项更强，黄色表示每一项放到所有模型里排在什么位置，标注里的名次就是这一项的排名。'))
S.append(('文笔坐标', '分数之外<br>看原文',
          '<div class="panel">' + tiles([('6391', '条逐题打分明细'), ('107', '道题的答卷原文'), ('35', '张榜单卡片'), ('100%', '点评附原文证据')]) + '</div>'
          '<div class="panel"><div class="lead">完整明细、答卷原文和评分脚本都在汇总目录里，可以逐题复核。</div></div>',
          '分数只是参考。每一份打分都附有带原文证据的点评，完整的明细和答卷原文都可以逐题复核。感谢观看。'))

meta = []
for i, (k, t, body, say) in enumerate(S):
    j = body.rfind('<div class="panel')
    body = body[:j] + '<div class="panel grow' + body[j + len('<div class="panel'):]
    h = (f'<!doctype html><html lang="zh"><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
         f'<div class="card"><div class="top"><span>{k}</span><span class="brand">文笔坐标</span></div>'
         f'<h1>{t}</h1>{body}<div class="sub">{esc(say)}</div></div><script>{JS}</script></body></html>')
    name = f'{i:02d}'
    open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8').write(h)
    meta.append({'name': name, 'say': say})
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(meta), 'slides')
