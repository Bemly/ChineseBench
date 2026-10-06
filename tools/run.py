#!/usr/bin/env python3
"""对 OpenAI 兼容接口（Ollama / LM Studio / llama.cpp server / vLLM 等）批量跑题。

示例：
  python3 tools/run.py --model qwen3:32b                          # Ollama 默认地址
  python3 tools/run.py --base-url http://localhost:1234/v1 --model local-model --ids T-A,T-D01
  python3 tools/run.py --model xxx --ids T-G --max-tokens 32000 --timeout 7200

结果写入 results/<模型名>/<题号>[_rN].json 与同名 .md（可读版对话记录）。
已存在的结果默认跳过，加 --force 重跑。
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_jsonl import ROOT, load_all  # noqa: E402

FILE_RE = re.compile(r"\{\{file:([^|}]+)(?:\|needle:([^}]+))?\}\}")
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def expand_files(text: str) -> str:
    """把 {{file:路径|needle:句子}} 替换为文件内容，可选在约 55% 处插入"针"。"""
    def repl(m):
        path = ROOT / m.group(1).strip()
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_text(encoding="utf-8")
        needle = m.group(2)
        if needle:
            paras = content.split("\n")
            pos = int(len(paras) * 0.55)
            while pos < len(paras) and not paras[pos].strip():
                pos += 1
            paras.insert(pos + 1, needle.strip())
            content = "\n".join(paras)
        return content
    return FILE_RE.sub(repl, text)


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def chat(args, messages):
    body = {"model": args.model, "messages": messages,
            "temperature": args.temperature, "max_tokens": args.max_tokens}
    if args.top_p is not None:
        body["top_p"] = args.top_p
    req = urllib.request.Request(
        args.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {args.api_key}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=args.timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    return {"content": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or msg.get("reasoning") or "",
            "finish_reason": data["choices"][0].get("finish_reason"),
            "usage": data.get("usage", {}),
            "seconds": round(time.time() - t0, 1)}


def select(tests, ids):
    if not ids:
        return tests
    keys = [k.strip() for k in ids.split(",") if k.strip()]
    return [t for t in tests if any(t["id"].startswith(k) for k in keys)]


def to_markdown(rec):
    out = [f"# {rec['id']}｜{rec['title']}", "",
           f"- 模型：`{rec['model']}`　温度：{rec['temperature']}　时间：{rec['time']}", ""]
    if rec["system"]:
        out += ["## System", "", rec["system"], ""]
    for i, turn in enumerate(rec["turns"], 1):
        out += [f"## 第 {i} 轮 · 用户", "", turn["user"] if len(turn["user"]) < 4000
                else turn["user"][:2000] + "\n\n……（长输入已截断显示）……", "",
                f"## 第 {i} 轮 · 模型（{turn['seconds']}s，finish={turn['finish_reason']}）", "",
                turn["content"], ""]
    return "\n".join(out)


def run_test(args, t, out_dir, suffix):
    stem = t["id"] + suffix
    jpath = out_dir / f"{stem}.json"
    if jpath.exists() and not args.force:
        print(f"  跳过 {stem}（已存在）")
        return
    try:
        user_turns = [expand_files(u) for u in t["turns"]]
    except FileNotFoundError as e:
        print(f"  跳过 {stem}：缺少素材文件 {e}")
        return
    messages = [{"role": "system", "content": t["system"]}] if t["system"] else []
    rec = {"id": t["id"], "title": t["title"], "model": args.model,
           "temperature": args.temperature, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
           "system": t["system"], "turns": []}
    for i, u in enumerate(user_turns, 1):
        messages.append({"role": "user", "content": u})
        print(f"  {stem} 第 {i}/{len(user_turns)} 轮 …", end="", flush=True)
        try:
            r = chat(args, messages)
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            print(f" 失败：{e}")
            rec["error"] = str(e)
            break
        print(f" {r['seconds']}s")
        rec["turns"].append({"user": u, **r})
        # 多轮时只把正文（去掉 <think>）放回上下文
        messages.append({"role": "assistant", "content": strip_think(r["content"])})
    jpath.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{stem}.md").write_text(to_markdown(rec), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:11434/v1",
                    help="OpenAI 兼容地址。Ollama: :11434/v1，LM Studio: :1234/v1，llama.cpp: :8080/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="local")
    ap.add_argument("--ids", default="", help="题号前缀，逗号分隔，如 T-A,T-D01,T-G")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--top-p", type=float, default=None)
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--timeout", type=int, default=3600, help="单次请求超时秒数")
    ap.add_argument("--repeat", type=int, default=1, help="每题重复次数（用于看稳定性）")
    ap.add_argument("--tag", default="", help="结果目录后缀，用于区分同一模型的不同参数")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    tests = select(load_all(), args.ids)
    if not tests:
        sys.exit("没有匹配的题目")
    name = re.sub(r"[^\w.\-]+", "_", args.model) + (f"_{args.tag}" if args.tag else "")
    out_dir = ROOT / "results" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"模型 {args.model} → {out_dir.relative_to(ROOT)}，共 {len(tests)} 题 × {args.repeat}")
    for t in tests:
        for n in range(args.repeat):
            run_test(args, t, out_dir, f"_r{n + 1}" if args.repeat > 1 else "")


if __name__ == "__main__":
    main()
