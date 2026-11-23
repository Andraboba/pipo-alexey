"""PNG (256×256) -> .ico с одной PNG-записью (формат Vista+, понимает Windows и PyInstaller).

    python tools/make_icon.py icon.png assets/icon.ico
"""
import struct
import sys
from pathlib import Path


def png_to_ico(png: bytes) -> bytes:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("это не PNG")
    w, h = struct.unpack(">II", png[16:24])
    if w > 256 or h > 256:
        raise ValueError("иконка не больше 256×256")
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(png_to_ico(src.read_bytes()))
    print(f"{dst} ({dst.stat().st_size} bytes)")
