#!/bin/bash
# 逐题生成鉴赏视频；已有的跳过；曼波 TTS 接口报错（多为当日额度用完）时停止。
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(echo /Volumes/*/影片/文笔/汇总)/逐题鉴赏"
mkdir -p "$OUT"
for f in /Users/bemly/Documents/opus5.5/手动评分/00_题目/T-*.md; do
  q=$(basename "$f" .md)
  [ -f "$OUT/$q.mp4" ] && continue
  echo "== $q $(date +%H:%M:%S)"
  log=$(python3 -I "$HERE/yk.py" "$q" "$OUT/$q.mp4.part.mp4" 2>&1)
  if [ $? -ne 0 ]; then
    rm -f "$OUT/$q.mp4.part.mp4"
    echo "$log" | tail -3
    if echo "$log" | grep -q '曼波接口'; then echo "STOP: 曼波 TTS 接口报错，停在 $q"; exit 2; fi
    echo "FAIL $q（非接口原因），继续下一题"; continue
  fi
  mv "$OUT/$q.mp4.part.mp4" "$OUT/$q.mp4"
  echo "$log" | tail -1
done
echo "ALL DONE"
