from pathlib import Path
from unittest.mock import Mock

from ghost_data.vision import FallbackImageReader, TesseractImageReader


def test_tesseract_reader_uses_configured_executable(monkeypatch, tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"png")
    completed = Mock(stdout="recognized text")
    run = Mock(return_value=completed)
    monkeypatch.setattr("ghost_data.vision.subprocess.run", run)
    monkeypatch.setenv("GHOST_DATA_OCR_DPI", "240")
    assert TesseractImageReader("ocr-tool").extract_text(image) == "recognized text"
    assert run.call_args.args[0] == ["ocr-tool", str(image), "stdout", "--dpi", "240"]


def test_ocr_backend_environment_selects_and_orders_fallbacks(monkeypatch):
    monkeypatch.setenv("GHOST_DATA_OCR_BACKEND", "rapidocr")
    monkeypatch.delenv("GHOST_DATA_API_KEY", raising=False)
    reader = FallbackImageReader()
    assert [factory.__name__ for factory in reader.factories] == ["RapidOCRImageReader", "TesseractImageReader"]
