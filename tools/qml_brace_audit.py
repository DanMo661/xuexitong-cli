# -*- coding: utf-8 -*-
"""QML 括号配平审计（忽略注释与字符串字面量）。"""
import re
import pathlib

qd = pathlib.Path(__file__).resolve().parent.parent / "assistant" / "ui" / "qml"
for f in sorted(qd.glob("*.qml")):
    s = f.read_text(encoding="utf-8")
    s = re.sub(r"//[^\n]*", "", s)
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
    depth = 0
    neg = False
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                neg = True
                break
    print(f"{f.name:20s} braces_final={depth} neg={neg}")
