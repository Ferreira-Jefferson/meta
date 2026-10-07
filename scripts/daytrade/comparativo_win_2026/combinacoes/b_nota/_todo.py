import sys
from pathlib import Path
T=Path(__file__).resolve().parents[1]/"TODO.md"
s=T.read_text(encoding="utf-8")
a=s.index("\n## B ")+1; b=s.index("<!-- Frentes novas")
new=sys.stdin.buffer.read().decode("utf-8").rstrip()+"\n\n"
T.write_text(s[:a]+new+s[b:],encoding="utf-8",newline="")
