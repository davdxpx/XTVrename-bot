"""UIChrome — divider/frame/progress-block formatting contract."""

from tools.mirror_leech.UIChrome import (
    DIVIDER,
    BAR_LENGTH,
    BLOCK_FILLED,
    BLOCK_EMPTY,
    frame,
    frame_plain,
    progress_block,
    format_bytes,
    format_eta,
    format_elapsed,
)


def test_divider_is_20_box_chars():
    assert len(DIVIDER) == 20
    assert set(DIVIDER) == {"\u2501"}


def test_progress_block_at_zero():
    block = progress_block(0.0)
    assert "0.0%" in block
    assert block.endswith(f"[{BLOCK_EMPTY * BAR_LENGTH}]")


def test_progress_block_midway():
    block = progress_block(0.479)
    # `47.9%` rendered with one decimal
    assert "47.9%" in block
    # int(47.9 // 10) = 4 filled blocks
    assert block.endswith(f"[{BLOCK_FILLED * 4}{BLOCK_EMPTY * 6}]")


def test_progress_block_full():
    block = progress_block(1.0)
    assert "100.0%" in block
    assert block.endswith(f"[{BLOCK_FILLED * BAR_LENGTH}]")


def test_progress_block_clamps_overflow():
    block_hi = progress_block(2.5)
    block_lo = progress_block(-0.5)
    assert block_hi.endswith(f"[{BLOCK_FILLED * BAR_LENGTH}]")
    assert block_lo.endswith(f"[{BLOCK_EMPTY * BAR_LENGTH}]")


def test_frame_has_two_dividers_and_signature():
    text = frame("⬇️ **Test**", "> hello world")
    lines = text.splitlines()
    assert lines[0] == "⬇️ **Test**"
    assert lines[1] == DIVIDER
    # body sits between the two dividers
    body_idx = lines.index("> hello world")
    assert body_idx > 1
    # second divider precedes the signature
    second_divider_idx = len(lines) - 2
    assert lines[second_divider_idx] == DIVIDER
    assert "Engine" in lines[-1]


def test_frame_plain_has_no_signature():
    text = frame_plain("🗂 **MyFiles**", "> body")
    # Still two dividers bracketing the body
    assert text.count(DIVIDER) == 2
    # But no XTVEngine line
    assert "Engine" not in text
    # And the last line must be the closing divider, not a signature
    assert text.rstrip().splitlines()[-1] == DIVIDER


def test_format_bytes_steps():
    assert format_bytes(0).endswith("B")
    assert "KB" in format_bytes(2048)
    assert "MB" in format_bytes(2 * 1024 ** 2)


def test_format_eta_and_elapsed():
    assert format_eta(30) == "30s"
    assert format_eta(90).endswith("s")
    assert format_elapsed(65) == "01:05"
    assert format_elapsed(3725) == "01:02:05"
