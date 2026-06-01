#!/usr/bin/env python3
"""One-off: convert file to LF line endings. Usage: python3 fix_crlf.py <file>"""
import sys
path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()
with open(path, "wb") as f:
    f.write(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
