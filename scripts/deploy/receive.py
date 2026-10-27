#!/usr/bin/python3
"""Receive a GitHub-built static archive through a restricted SSH key."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import time

command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
if not re.fullmatch(r"deploy [0-9a-f]{40}", command):
    sys.exit("Only deploy <40-character commit SHA> is allowed")

revision = command.split()[1]
root = Path("/srv/word-atlas")
releases = root / "releases"
incoming = Path(tempfile.mkdtemp(prefix=".incoming-", dir=releases))
link = root / ".current-new"
try:
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
        for member in archive:
            if not (member.isfile() or member.isdir()):
                raise ValueError("Archive must contain only regular files and directories")
            archive.extract(member, incoming, filter="data")
    if not (incoming / "index.html").is_file():
        raise ValueError("Missing index.html")
    index = json.loads((incoming / "atlas/index.json").read_text())
    if not index.get("count") or index["count"] != len(index["words"]):
        raise ValueError("Invalid vocabulary index")
    (incoming / "revision.txt").write_text(revision + "\n")
    incoming.chmod(0o755)
    release = releases / f"{time.time_ns()}-{revision}"
    incoming.rename(release)
    link.unlink(missing_ok=True)
    link.symlink_to(release)
    link.replace(root / "current")
    print(f"Published {revision}: {index['count']} words", flush=True)
    previous = sorted(
        (p for p in releases.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name,
        reverse=True,
    )
    for old in previous[3:]:
        shutil.rmtree(old)
finally:
    if incoming.exists():
        shutil.rmtree(incoming)
    link.unlink(missing_ok=True)
