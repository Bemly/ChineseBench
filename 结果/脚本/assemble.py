"""把逐帧动画按顺序拼成视频：每张卡动画结束后定格，卡与卡之间 0.4s 淡入淡出，配满 bgm。
用法: assemble.py <帧目录> <名单json> <bgm> <输出mp4>"""
import json, os, subprocess, sys

frames, order_json, bgm, out = sys.argv[1:5]
order = json.load(open(order_json, encoding='utf-8'))
durs = json.load(open(os.path.join(frames, 'durs.json'), encoding='utf-8'))
T = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', bgm]))
N, X, FPS = len(order), 0.4, 30
d = (T + X * (N - 1)) / N
args = ['ffmpeg', '-y', '-v', 'error']
for i, _ in enumerate(order):
    args += ['-framerate', str(FPS), '-i', os.path.join(frames, f'{i:02d}', 'f%04d.jpg')]
args += ['-i', bgm]
f = []
for i, name in enumerate(order):
    pad = max(0.0, d - durs[name])
    assert durs[name] < d - X, (name, durs[name], d)
    f.append(f'[{i}:v]tpad=stop_mode=clone:stop_duration={pad:.4f},trim=duration={d:.4f},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]')
prev = 'v0'
for i in range(1, N):
    f.append(f'[{prev}][v{i}]xfade=transition=fade:duration={X}:offset={i * (d - X):.4f}[x{i}]')
    prev = f'x{i}'
f.append(f'[{prev}]scale=in_range=pc:out_range=tv,format=yuv420p[out]')
args += ['-filter_complex', ';'.join(f), '-map', '[out]', '-map', f'{N}:a',
         '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-preset', 'medium', '-crf', '20',
         '-c:a', 'copy', '-t', f'{T}', '-movflags', '+faststart', out]
print(f'{N} cards, {d:.2f}s each')
subprocess.run(args, check=True)
