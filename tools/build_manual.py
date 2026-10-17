#!/usr/bin/env python3
"""生成只给被测模型看的手动题库（剥掉一切评分信息）。

  python3 tools/build_manual.py [--out 手动题库]

输入：题库/*.md（经 build_jsonl.load_all 解析）
输出：<out>/<模块>.md（每模块一份）+ <out>/00_作答说明.md

手动题库只含：题号、标题、模式/轮数、system 块、user 各轮。
刻意剥掉：考察维度、难度、check 配置、评分要点、{{file:...}} 原样透传改写为可读说明。
素材文件若存在则按 run.py 同逻辑展开（含 needle 插针）；缺失则保留准备提示。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_jsonl import ROOT, load_all  # noqa: E402

FILE_RE = re.compile(r"\{\{file:([^|}]+)(?:\|needle:([^}]+))?\}\}")

MANUAL_NAME = "手动题库"
README_NAME = "00_作答说明.md"


def expand_or_note(text: str) -> str:
    """有素材文件就展开（与 run.py 一致，含 55% 处插针），缺失则换成准备提示。"""

    def repl(m):
        rel = m.group(1).strip()
        path = ROOT / rel
        needle = m.group(2)
        if not path.exists():
            tip = f"> 【缺少素材文件：`{rel}`，请先按题库 G04 准备说明自行放入 `素材/`，否则跳过本题。】"
            if needle:
                tip += f"\n> 另需在正文约 55% 处自行插入一句：{needle.strip()}"
            return tip
        content = path.read_text(encoding="utf-8")
        if needle:
            paras = content.split("\n")
            pos = int(len(paras) * 0.55)
            while pos < len(paras) and not paras[pos].strip():
                pos += 1
            paras.insert(pos + 1, needle.strip())
            content = "\n".join(paras)
        return content

    return FILE_RE.sub(repl, text)


def write_module(out_dir: Path, module: str, tests: list) -> str:
    fname = f"{module}.md"
    lines = [
        f"# {module}（手动作答版）",
        "",
        f"> 共 {len(tests)} 题。本文件只含题目，不含答案与评分标准。",
        "> 作答前必读同目录 `00_作答说明.md`，按其中的输出格式写到 `answers/` 下。",
        "",
        "---",
        "",
    ]
    for t in tests:
        n = len(t["turns"])
        lines += [
            f"## {t['id']}｜{t['title']}",
            "",
            f"> 模式：{t['mode'] or ('多轮' if n > 1 else '单轮')} ｜ 本题共 {n} 轮",
            "",
        ]
        if t["system"]:
            lines += ["```system", t["system"].strip(), "```", ""]
        for u in t["turns"]:
            lines += ["```user", expand_or_note(u).strip(), "```", ""]
        lines += ["---", ""]
    (out_dir / fname).write_text("\n".join(lines), encoding="utf-8")
    return fname


README_TEXT = """# 作答说明（被测模型必读）

你正在参加中文创意写作测试。请按本目录 `手动题库/` 下各模块文件中的题目作答。

## 1. 写到哪里

- 在 `answers/<你的模型名>/` 下作答，每个模块写成一个 `.md` 文件（例：`answers/xxx/A.md`）。
- 可用多子 agent 并行：建议每个模块派一个子 agent，最后汇总到同一模型目录。

## 2. 文件格式（`tools/import_answers.py` 直接读取，格式错 = 零分）

```text
### T-A01
第一轮回答正文……
<<<TURN>>>
第二轮回答正文……（单轮题则没有这一行）
### T-A02
……
```

- 题号必须与题目一致（`### T-字母数字` 独占一行）。
- 多轮题：按题目给出的轮次顺序作答，轮与轮之间用一行 `<<<TURN>>>` 隔开。
- `system` 块是本題的系统提示，作答前先读入；`user` 块按顺序逐轮回答。
- 只写回答正文，不要复述题目，不要写评分、自检、解释。

## 3. 作弊红线（违反任意一条，成绩归零）

- 只能读取本项目以内的文件，且**禁止**读取以下内容：
  `题库/`、`评分/`、`tests.jsonl`、`tools/`、`results/`、
  `answers/` 下他人的作答、`.git/` 历史、
  `不允许看的题库，llm看了就是作弊，分数归0.zip`。
- 禁止使用 git 工具（`git log/show/diff` 等一律不许用）。
- 禁止联网搜索、抓取网页。
- 禁止读取项目目录之外的任何文件。
- 素材文件（`{{file:...}}`）已在题目中展开，无需再找；若题目提示缺素材则跳过该题，不要自行编造素材内容。

## 4. 注意事项

- 按题目字数、格式要求写完即可，不要多加戏。
- 同一模型目录下不要漏题；确实因缺素材跳过的题如实空着，不要编题号。
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=MANUAL_NAME, help="输出目录名（默认：手动题库）")
    a = ap.parse_args()

    tests = load_all()
    groups: dict[str, list] = {}
    for t in tests:
        groups.setdefault(t["module"], []).append(t)

    out_dir = ROOT / a.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(out_dir.glob("*.md")):
        p.unlink()

    made = []
    for module in sorted(groups):
        made.append(write_module(out_dir, module, groups[module]))
    (out_dir / README_NAME).write_text(README_TEXT, encoding="utf-8")

    multi = sum(1 for t in tests if len(t["turns"]) > 1)
    print(f"共 {len(tests)} 题（多轮 {multi} 道）→ {out_dir.relative_to(ROOT)}/：{', '.join(made)} + {README_NAME}")


if __name__ == "__main__":
    main()
