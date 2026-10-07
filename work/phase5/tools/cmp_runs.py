"""Compare two runs' package/ trees file by file: bytes, or bytes after normalising run paths for text files."""
import re, sys
from pathlib import Path
a, b = Path(sys.argv[1]) / "package", Path(sys.argv[2]) / "package"
pat = re.compile(r"/[^\s\"']*?/(replay[AB]|runs[^/\s\"']*|replay_bf)/[^/\s\"']+")
ok = tot = 0
for f in sorted(p for p in a.rglob("*") if p.is_file()):
    rel = f.relative_to(a); g = b / rel; tot += 1
    if not g.exists():
        print("MISSING", rel); continue
    x, y = f.read_bytes(), g.read_bytes()
    if x == y:
        ok += 1; print("identical           ", rel); continue
    try:
        if pat.sub("<RUN>", x.decode()) == pat.sub("<RUN>", y.decode()):
            ok += 1; print("identical (run path)", rel); continue
    except UnicodeDecodeError:
        pass
    print("DIFFERENT           ", rel, len(x), len(y))
print(f"{ok}/{tot} identical")
