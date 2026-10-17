"""解说视频合成：每页时长 = 旁白 + 留白；页间 0.4s 淡入淡出；旁白居前，bgm 压低垫底。
用法: assemble_ex.py <帧目录> <幻灯片目录> <bgm> <输出>"""
import json, os, subprocess, sys

frames, sd, bgm, out = sys.argv[1:5]
order = json.load(open(os.path.join(sd, 'order.json')))
durs = json.load(open(os.path.join(frames, 'durs.json')))
X, FPS, LEAD, TAIL = 0.4, 30, 0.5, 0.9
dur = lambda f: float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]))
seg = [LEAD + dur(os.path.join(sd, n + '.mp3')) + TAIL for n in order]
args = ['ffmpeg', '-y', '-v', 'error']
for i, n in enumerate(order):
    args += ['-framerate', str(FPS), '-i', os.path.join(frames, f'{i:02d}', 'f%04d.jpg')]
for n in order:
    args += ['-i', os.path.join(sd, n + '.mp3')]
args += ['-stream_loop', '-1', '-i', bgm]
N = len(order)
f = []
for i, n in enumerate(order):
    d = seg[i] + (X if i < N - 1 else 0)
    f.append(f'[{i}:v]tpad=stop_mode=clone:stop_duration={max(0, d - durs[n]):.3f},trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v{i}]')
prev, off = 'v0', 0.0
for i in range(1, N):
    off += seg[i - 1]
    f.append(f'[{prev}][v{i}]xfade=transition=fade:duration={X}:offset={off:.3f}[x{i}]')
    prev = f'x{i}'
f.append(f'[{prev}]scale=in_range=pc:out_range=tv,format=yuv420p[vout]')
total = sum(seg)
t = 0.0
for i in range(N):
    ms = int((t + LEAD) * 1000)
    f.append(f'[{N + i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]')
    t += seg[i]
f.append(f'[{2 * N}:a]aresample=48000,volume=0.12,afade=t=out:st={total - 2:.2f}:d=2[bg]')
f.append(''.join(f'[a{i}]' for i in range(N)) + f'[bg]amix=inputs={N + 1}:normalize=0:duration=longest,atrim=0:{total:.3f}[aout]')
args += ['-filter_complex', ';'.join(f), '-map', '[vout]', '-map', '[aout]',
         '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-crf', '20',
         '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-t', f'{total:.3f}', '-movflags', '+faststart', out]
subprocess.run(args, check=True)
print(f'{N} slides, {total:.1f}s')
