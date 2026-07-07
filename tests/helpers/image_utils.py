# tests/helpers/image_utils.py

from pathlib import Path

def get_minimal_jpeg_bytes() -> bytes:
    """
    Reads and returns the bytes of the minimal test JPEG.
    Resolves the path relative to this file to ensure robust test execution.
    """
    # Navigates up from helpers/ to tests/, then into fixtures/
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "minimal.jpg"

    if not fixture_path.exists():
        raise FileNotFoundError(f"Missing required test asset: {fixture_path}")

    return fixture_path.read_bytes()
