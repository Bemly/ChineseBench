#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-G05 文体契约检查器
用法：python3 check_g05.py 文件1 文件2 ...
"""
import sys, re, glob, os

BANNED = ['像', '如同', '仿佛', '好像', '似的', '宛如', '犹如', '好比',
          '似乎', '宛如', '犹如', '般的', '一样', '一般', '好像']

def chapter_blocks(text):
    out = []
    cur = None
    for line in text.split('\n'):
        m = re.match(r'^##\s*第([一二三四五六七八九十]+)章', line)
        if m:
            if cur: out.append(cur)
            cur = {'title': line.strip(), 'lines': []}
            continue
        if cur is not None and line.startswith('## 附'):
            cur['lines'].append(line)  # 标记正文结束
            out.append(cur); cur = None
            continue
        if cur is not None and not line.startswith('#') and not line.startswith('>') and line.strip() != '---':
            cur['lines'].append(line)
    if cur: out.append(cur)
    return out

def main(paths):
    total_bad = 0
    for p in paths:
        s = open(p, encoding='utf-8').read()
        for ch in chapter_blocks(s):
            name = ch['title']
            probs = []
            body = [l for l in ch['lines']]
            # 1. banned words
            joined = '\n'.join(body)
            for w in ['像', '如同', '仿佛', '好像', '似的', '宛如', '犹如', '好比', '似乎']:
                if w in joined:
                    for i, l in enumerate(body):
                        if w in l:
                            probs.append(f'禁用比喻词「{w}」: {l.strip()[:50]}')
            # 2. paragraph sentence count
            para = []
            buf = []
            for l in body:
                if l.strip():
                    buf.append(l)
                else:
                    if buf: para.append(''.join(buf)); buf = []
            if buf: para.append(''.join(buf))
            for pp in para:
                pp = pp.strip()
                if not pp: continue
                if pp.startswith('　　'):  # 全角缩进=正文
                    n = len(re.findall(r'[。！？…][”」』"]?(?![”」』"])', pp))
                    if n > 4:
                        probs.append(f'段落 {n} 句 > 4: {pp[:50]}')
            # 3. last sentence must be a question
            texts = [p.strip() for p in para if p.strip().startswith('　　')]
            if texts:
                last = texts[-1]
                tail = last.rstrip('　')
                if not tail.endswith('？'):
                    probs.append(f'章末非问句: {last[-40:]}')
            print(('OK  ' if not probs else 'FAIL'), p, name)
            for x in probs:
                print('     -', x)
            total_bad += len(probs)
    print('---')
    print('问题总数:', total_bad)

if __name__ == '__main__':
    files = sys.argv[1:]
    if not files:
        files = sorted(glob.glob('G_长上下文续航_答案_part1[7-9].md')) + sorted(glob.glob('G_长上下文续航_答案_part2*.md'))
    main(files)