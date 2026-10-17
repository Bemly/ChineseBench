"""打印某题每份作答的汉字数、禁词/句式命中，辅助人工评分。用法: stat.py <盲评包题目目录> 词1 词2 ..."""
import os, re, sys

d, words = sys.argv[1], sys.argv[2:]
for f in sorted(os.listdir(d)):
    t = open(os.path.join(d, f), encoding='utf-8').read()
    han = len(re.findall(r'[一-鿿]', t))
    hits = {w: t.count(w) for w in words if t.count(w)}
    contrast = len(re.findall(r'不是[^。！？\n]{0,15}[，,]?\s*(而是|是)', t))
    slop = sum(t.count(w) for w in ['仿佛', '一抹', '一丝', '不禁', '缓缓', '深吸一口气', '某种', '这一刻'])
    print(f'{f}: 汉字{han} 不是而是~{contrast} 老套词{slop} 破折号{t.count("——")} 禁词{hits}')
