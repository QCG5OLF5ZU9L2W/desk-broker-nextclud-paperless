#!/usr/bin/env python3
"""Build an unsigned XPI using only Python's standard library."""
from pathlib import Path
import json
import zipfile

root=Path(__file__).resolve().parent
version=json.loads((root/'extension/manifest.json').read_text())['version']
output=root/'dist'/f'Paperless-Send-{version}-unsigned.xpi'
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
    for file in sorted((root/'extension').rglob('*')):
        if file.is_file():
            name=file.relative_to(root/'extension').as_posix()
            info=zipfile.ZipInfo(name,date_time=(2026,9,8,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644 << 16
            archive.writestr(info,file.read_bytes())
print(output)
