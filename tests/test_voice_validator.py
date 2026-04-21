import pytest
import os
import tempfile
import wave
import struct
from vvr_scraper.voice_bank.validator import validate_audio, convert_to_canonical, SUPPORTED_EXTENSIONS


def _create_wav(path, duration_s=5, sample_rate=22050, channels=1, bit_depth=16):
    """Helper to create a valid WAV file for testing."""
    n_samples = int(duration_s * sample_rate)
    data = struct.pack(f"<{n_samples * channels}h", *([0] * n_samples * channels))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_validate_valid_wav(temp_dir):
    wav_path = os.path.join(temp_dir, "test.wav")
    _create_wav(wav_path, duration_s=5, sample_rate=22050)
    result = validate_audio(wav_path)
    assert result.valid is True
    assert result.format == "wav"
    assert result.sample_rate == 22050
    assert result.channels == 1
    assert 2900 <= result.duration_ms <= 5100  # ~5s


def test_validate_wav_too_short(temp_dir):
    wav_path = os.path.join(temp_dir, "short.wav")
    _create_wav(wav_path, duration_s=1, sample_rate=22050)
    result = validate_audio(wav_path)
    assert result.valid is False
    assert "3-10 seconds" in result.error


def test_validate_wav_too_long(temp_dir):
    wav_path = os.path.join(temp_dir, "long.wav")
    _create_wav(wav_path, duration_s=15, sample_rate=22050)
    result = validate_audio(wav_path)
    assert result.valid is False
    assert "3-10 seconds" in result.error


def test_validate_unsupported_format(temp_dir):
    txt_path = os.path.join(temp_dir, "test.txt")
    with open(txt_path, "w") as f:
        f.write("not audio")
    result = validate_audio(txt_path)
    assert result.valid is False
    assert "Unsupported" in result.error


def test_convert_to_canonical(temp_dir):
    wav_path = os.path.join(temp_dir, "input.wav")
    _create_wav(wav_path, duration_s=5, sample_rate=44100, channels=2, bit_depth=16)
    out_path = os.path.join(temp_dir, "canonical.wav")
    convert_to_canonical(wav_path, out_path)
    result = validate_audio(out_path)
    assert result.valid is True
    assert result.sample_rate == 22050
    assert result.channels == 1


def test_validate_duration_after_conversion(temp_dir):
    """Duration must be re-validated on the canonical file."""
    wav_path = os.path.join(temp_dir, "edge.wav")
    _create_wav(wav_path, duration_s=5, sample_rate=22050)
    out_path = os.path.join(temp_dir, "canonical.wav")
    convert_to_canonical(wav_path, out_path)
    result = validate_audio(out_path)
    assert result.valid is True
    assert 4500 <= result.duration_ms <= 5500
