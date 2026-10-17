"""fill.py <csv> < input ；输入每行：Mxx|十个维度用逗号分隔(空=不适用)|专项|点评"""
import csv, sys

path = sys.argv[1]
rows = list(csv.reader(open(path, encoding='utf-8-sig')))
header, body = rows[0], rows[1:]
scores = {}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    mid, dims, spec, comment = line.split('|', 3)
    d = [x.strip() for x in dims.split(',')]
    assert len(d) == 10, mid
    vals = [float(x) for x in d if x]
    avg = round(sum(vals) / len(vals) + 1e-9, 1)
    tot = round(avg * 0.5 + float(spec) * 0.5 + 1e-9, 1)
    scores[mid] = [mid, *d, f'{avg:.1f}', spec, f'{tot:.1f}', comment]
out = []
for r in body:
    assert r[0] in scores, f'缺 {r[0]}'
    out.append(scores.pop(r[0]))
assert not scores, f'多余 {list(scores)}'
with open(path, 'w', encoding='utf-8', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(header)
    w.writerows(out)
for r in out:
    print(r[0], r[11], r[12], r[13])
