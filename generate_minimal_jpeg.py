"""
Run this script once from the project root to generate the MINIMAL_JPEG
constant used in tests/test_pdf_formatter.py (and later test_form_routes.py).

    python generate_minimal_jpeg.py

Copy the printed output and replace the MINIMAL_JPEG block in the test file.
Delete this script afterwards — it is not part of the test suite.
"""
import io
from PIL import Image

# 1x1 white RGB pixel
img = Image.new("RGB", (1, 1), color=(255, 255, 255))
buf = io.BytesIO()
img.save(buf, format="JPEG")
jpeg_bytes = buf.getvalue()

print(f"# Length: {len(jpeg_bytes)} bytes")
print(f"# Header bytes: {jpeg_bytes[:4].hex()}")
print()
print("MINIMAL_JPEG: bytes = bytes([")
hex_vals = [f"0x{b:02X}" for b in jpeg_bytes]
lines = [hex_vals[i:i+16] for i in range(0, len(hex_vals), 16)]
for line in lines:
    print("    " + ", ".join(line) + ",")
print("])")
