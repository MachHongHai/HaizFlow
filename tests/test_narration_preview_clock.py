import re
import subprocess
from pathlib import Path
from haizflow.desktop.subtitle_overlay_renderer import export_events
from haizflow.pipeline.render import _subtitle_patch_prefix
from haizflow.utils.ffmpeg import _binary


def test_karaoke_tracks_speech_duration_but_keeps_caption_window(tmp_path):
    segment = dict(segment_id='long', start=10, end=18, _speech_end=12,
                   text='Xin chào bạn tôi đang nói một câu khá dài')
    layout = dict(outputWidth=1280, outputHeight=720, layoutWidth=900, layoutHeight=120,
                  fontSize=40, outline=2, positionXPercent=50, positionYPercent=80)
    _, events = export_events([segment], layout, True, tmp_path)
    assert events[0]['start'] == 10 and events[-1]['end'] == 18
    assert sum(int(n) for event in events for n in re.findall(r'\\kf(\d+)', event['body'])) == 200
    assert segment['end'] == 18


def test_static_patch_mask_repeats_to_end_of_preview_and_export_stays_original(tmp_path):
    region = (20, 60, 80, 16)
    original = _subtitle_patch_prefix(region, 128, 96)
    optimized = _subtitle_patch_prefix(region, 128, 96, static_mask=True)
    assert 'geq=r=' in original and 'alphamerge' in optimized
    graph = optimized + '[source_without_original]format=rgb24[out]'
    result = subprocess.run([_binary('ffmpeg'), '-v', 'error', '-f','lavfi','-i',
        'testsrc2=s=128x96:r=10:d=2', '-filter_complex',graph,'-map','[out]',
        '-f','rawvideo','-pix_fmt','rgb24','-'], capture_output=True, timeout=20,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert len(result.stdout) == 128*96*3*20
    assert result.stdout[:128*96*3] != result.stdout[-128*96*3:]
