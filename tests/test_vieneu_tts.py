import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
import soundfile as sf

from haizflow.core.model_choices import gpu_choice_blocked, models_for_device
from haizflow.core.vieneu_assets import MANIFEST
from haizflow.core.vieneu_voices import VIENEU_VOICES, native_voice, sample_voice_id, speaker_voice
from haizflow.desktop.presenters import voice_options_for_language
from haizflow.pipeline import tts, vieneu_tts
from haizflow.schemas.video import VideoConfig
from haizflow.services.resource_packs import ENGINE_REQUIRED_COMMANDS, ResourcePackError, ResourcePackManager
from haizflow.services.video_store import _migrate_video_metadata


@pytest.mark.parametrize('provider', ['vieneu', 'vieneu-gpu'])
def test_native_provider_and_voice_survive_reopen(provider):
    voice = 'vieneu:Trúc Ly'
    config = VideoConfig(tts_provider=provider, tts_voice=voice, target_language='vi')
    assert config.tts_provider == provider
    migrated, _ = _migrate_video_metadata({'schema_version': 19, 'tts_provider': provider,
                                           'tts_voice': voice, 'speaker_mode': 'multiple',
                                           'files': {'manual_voice_overrides': {
                                               's1': {'provider': provider, 'voice': voice}}}})
    assert migrated['tts_provider'] == provider
    assert migrated['tts_voice'] == voice
    assert migrated['speaker_mode'] == 'multiple'
    assert migrated['files']['manual_voice_overrides']['s1']['voice'] == voice
    assert tts.resolve_tts_provider(provider, 'vi') == 'vieneu'
    with pytest.raises(ValueError):
        tts.resolve_tts_provider(provider, 'zh')


def test_one_shared_pack_and_explicit_device_routing():
    manager = ResourcePackManager()
    assert len([key for key in manager.definitions if 'vieneu' in key]) == 1
    for provider, engine in [('vieneu', 'engine-cpu-py313'), ('vieneu-gpu', 'engine-cuda128-py313')]:
        assert manager.required_packs('voice', {'provider': provider, 'device': 'gpu'}) == [engine, 'model-vieneu']
    assert manager.definitions['model-vieneu'].download_size == sum(entry['size'] for entry in MANIFEST['assets'])
    assert all(len(entry['sha256']) == 64 for entry in MANIFEST['assets'])
    assert all('/resolve/main/' not in entry['url'] for entry in MANIFEST['assets'])
    assert gpu_choice_blocked('cpu', voice='vieneu-gpu')
    assert not gpu_choice_blocked('gpu', voice='vieneu-gpu')
    choices = models_for_device('cpu', recognition='small-cpu', translation='q4', voice='vieneu-gpu')
    assert choices['tts_provider'] == 'vieneu'


@pytest.mark.parametrize('contract,valid,vieneu_ready', [(3, False, False), (6, True, False),
                                                       (7, True, True), (8, False, False)])
def test_additive_engine_contract_keeps_existing_models_and_requires_vieneu_command(tmp_path, contract,
                                                                                   valid, vieneu_ready):
    manager = ResourcePackManager()
    definition = manager.definitions['engine-cpu-py313']
    marker = tmp_path / 'complete.json'
    marker.write_text(json.dumps(dict(pack_id=definition.pack_id, version=definition.version,
                                     protocol_version=definition.protocol_version,
                                     archive_sha256=definition.archive_sha256)), encoding='utf-8')
    (tmp_path / 'engine.exe').write_bytes(b'fixture')
    payload = dict(pack_id=definition.pack_id, version=definition.version, profile='cpu',
                   protocol_version=definition.protocol_version, runtime_contract=contract)
    payload.update({name: ['engine.exe'] for name in ENGINE_REQUIRED_COMMANDS[definition.pack_id]})
    # Even a fabricated command on an older contract must not serve VieNeu.
    payload['vieneu_worker'] = ['engine.exe', '--vieneu-worker']
    manifest = tmp_path / 'engine.json'
    manifest.write_text(json.dumps(payload), encoding='utf-8')
    with (patch.object(manager, '_engine_marker', return_value=marker),
          patch.object(manager, '_bundled_engine_available', return_value=False)):
        assert manager._engine_is_valid(definition) is valid
        assert bool(manager.engine_command(definition.pack_id, 'vieneu_worker')) is vieneu_ready
        if contract == 7:
            payload.pop('vieneu_worker')
            manifest.write_text(json.dumps(payload), encoding='utf-8')
            assert not manager._engine_is_valid(definition)
            with pytest.raises(ResourcePackError, match='vieneu_worker'):
                manager._verify_engine_staging(definition, tmp_path)


def test_native_voice_bank_and_gender_mapping_never_use_narrator_preset():
    assert len(VIENEU_VOICES) == 25
    assert len(voice_options_for_language('vi', 'vi', 'vieneu')) == 26
    assert voice_options_for_language('vi', 'vi', 'vieneu')[-1]['voice'] == 'vieneu:clone'
    assert not voice_options_for_language('zh', 'vi', 'vieneu')
    assert native_voice('vieneu:Hải Đăng') == 'Hải Đăng'
    for code in ('female', 'bright', 'female_low', 'female_gentle'):
        assert speaker_voice('omnivoice:' + code) == 'vieneu:Trúc Ly'
    for code in ('male', 'deep', 'male_high', 'male_soft'):
        assert speaker_voice('omnivoice:' + code) == 'vieneu:Hải Đăng'
    with pytest.raises(ValueError):
        native_voice('omnivoice:female')


def test_preview_asset_ids_are_ascii_unique_and_use_exact_native_presets():
    names = [sample_voice_id('vieneu:' + name) for name, *_ in VIENEU_VOICES]
    assert len(set(names)) == len(VIENEU_VOICES) and all(name.isascii() for name in names)
    assert sample_voice_id('vieneu:Hải Đăng') == 'vieneu_Hai_Dang'
    assert sample_voice_id('vieneu:Thiền Tâm Đức') == 'vieneu_Thien_Tam_Duc'
    with pytest.raises(ValueError):
        sample_voice_id('vieneu:../Hải Đăng')


@pytest.mark.parametrize('provider,device', [('vieneu', 'cpu'), ('vieneu-gpu', 'gpu')])
def test_manual_and_auto_dispatch_to_vieneu_not_omnivoice(tmp_path, provider, device):
    source = tmp_path / 'segments.json'
    source.write_text(json.dumps([{'text': 'Xin chào.', 'start': 0, 'end': 1}]), encoding='utf-8')
    output = tmp_path / 'voice_0001.mp3'

    def generate(items, *args, **options):
        for item in items:
            Path(item['output_path']).write_bytes(b'ID3' + b'0' * 600)
        assert options['device'] == device
        options['progress_callback'](1, 1, 'completed')

    with (patch.object(tts, 'get_video', return_value=SimpleNamespace(files={}, speaker_mode='single')),
          patch.object(tts, 'log_to_video'), patch.object(tts, '_level_voice_peers', return_value=set()),
          patch.object(vieneu_tts, 'synthesize_batch_to_mp3', side_effect=generate) as run,
          patch('haizflow.pipeline.omnivoice_tts.synthesize_batch_to_mp3') as wrong):
        tts.generate_voice_parts(str(source), str(tmp_path), 'vieneu:Hải Đăng', 'test', provider=provider)
    assert run.call_count == 1 and not wrong.called
    assert output.exists()


def test_single_voice_dispatch_never_rewrites_native_preset():
    with patch.object(vieneu_tts, 'synthesize_to_mp3') as run:
        tts.generate_single_voice('Xin chào.', 'output.mp3', 'vieneu:Mai Anh', 'test', provider='vieneu-gpu')
    assert run.call_args.args[1] == 'vieneu:Mai Anh'
    assert run.call_args.kwargs['device'] == 'gpu'


@pytest.mark.parametrize('provider', ['vieneu', 'vieneu-gpu'])
@pytest.mark.parametrize('selection', ['vieneu:Mai Anh', 'per-speaker'])
def test_multiple_speakers_uses_native_mapping_without_mutating_source_cache(tmp_path, provider, selection):
    source = [{'text': 'A male voice.', 'start': 0, 'end': 1,
               'speaker_id': 's1', 'speaker_voice': 'omnivoice:male'},
              {'text': 'A female voice.', 'start': 1, 'end': 2,
               'speaker_id': 's2', 'speaker_voice': 'omnivoice:bright'}]
    before = json.dumps(source)
    source_path = tmp_path / 'source.json'
    source_path.write_text(before, encoding='utf-8')
    subtitles = tmp_path / 'subtitles.json'
    subtitles.write_text(json.dumps([{'text': 'Xin chào.', 'start': 0, 'end': 1},
                                     {'text': 'Cảm ơn.', 'start': 1, 'end': 2}]), encoding='utf-8')
    wav = tmp_path / 'source.wav'
    wav.write_bytes(b'wav fixture')
    video = SimpleNamespace(speaker_mode='multiple',
                            files={'source_segments': str(source_path), 'speech_audio': str(wav)})
    queued = []

    def run(items, *args, **kwargs):
        queued.extend(items)
        for item in items:
            Path(item['output_path']).write_bytes(b'ID3' + b'0' * 600)
        kwargs['progress_callback'](len(items), len(items), 'completed')

    with (patch.object(tts, 'get_video', return_value=video), patch.object(tts, 'log_to_video'),
          patch.object(tts, '_level_voice_peers', return_value=set()),
          patch('haizflow.pipeline.speaker_identity.prepare_speakers', return_value=source),
          patch('haizflow.pipeline.speaker_identity._valid_map', return_value=True),
          patch.object(vieneu_tts, 'synthesize_batch_to_mp3', side_effect=run)):
        tts.generate_voice_parts(str(subtitles), str(tmp_path), selection, 'test', provider=provider)
    assert [item['voice'] for item in queued] == ['vieneu:Hải Đăng', 'vieneu:Trúc Ly']
    assert json.dumps(source) == before


@pytest.mark.parametrize('provider', ['vieneu', 'vieneu-gpu'])
def test_multispeaker_long_path_reaches_synthesis_and_reuses_source_map(tmp_path, provider):
    from haizflow.pipeline import speaker_identity
    from haizflow.utils import atomic_file

    directory = tmp_path / ('d' * (175 - len(str(tmp_path)) - 1))
    directory.mkdir()
    wav = directory / 'vocals.wav'
    wav.write_bytes(b'source speech fixture')
    segments = [{'start': 0, 'end': 1, 'text': 'A male voice.'},
                {'start': 1, 'end': 2, 'text': 'A female voice.'}]
    source = tmp_path / 'source.json'
    source.write_text(json.dumps(segments), encoding='utf-8')
    subtitles = tmp_path / 'subtitles.json'
    subtitles.write_text(json.dumps([{**segment, 'text': text} for segment, text in
                                      zip(segments, ['Xin chào.', 'Cảm ơn.'])]), encoding='utf-8')
    video = SimpleNamespace(speaker_mode='multiple', files={'source_segments': str(source), 'speech_audio': str(wav)})
    queued = []
    create = atomic_file.tempfile.mkstemp

    def legacy_mkstemp(*args, **kwargs):
        prospective = Path(kwargs['dir']) / (kwargs.get('prefix', '') + 'abcdefgh' + kwargs.get('suffix', ''))
        if len(str(prospective)) >= 260:
            raise FileNotFoundError(2, 'No such file or directory', str(prospective))
        return create(*args, **kwargs)

    def identify(_capability, _operation, payload, *_args, **_kwargs):
        return {'segments': [{**segment, 'speaker_id': f's{index}', 'speaker_voice': voice}
                             for index, (segment, voice) in enumerate(zip(payload['segments'],
                                 ['omnivoice:male', 'omnivoice:bright']))]}

    def synthesize(items, *args, **kwargs):
        queued.extend(items)
        for item in items:
            Path(item['output_path']).write_bytes(b'ID3' + b'0' * 600)
        kwargs['progress_callback'](len(items), len(items), 'completed')

    with (patch.object(atomic_file.tempfile, 'mkstemp', side_effect=legacy_mkstemp),
          patch.object(speaker_identity, 'verify_model'),
          patch('haizflow.services.external_tasks.run_external_task', side_effect=identify) as engine,
          patch('haizflow.services.external_engine.shared_external_engine_pool'),
          patch.object(tts, 'get_video', return_value=video), patch.object(tts, 'log_to_video'),
          patch.object(tts, '_level_voice_peers', return_value=set()),
          patch.object(vieneu_tts, 'synthesize_batch_to_mp3', side_effect=synthesize)):
        tts.generate_voice_parts(str(subtitles), str(tmp_path), 'per-speaker', 'test', provider=provider)
        assert [item['voice'] for item in queued] == ['vieneu:Hải Đăng', 'vieneu:Trúc Ly']
        assert engine.call_count == 1
        caches = list(directory.glob('speaker-map-*.json'))
        assert len(caches) == 1 and len(str(caches[0])) == 257
        cached = json.loads(caches[0].read_text(encoding='utf-8'))
        assert [entry['speaker_voice'] for entry in cached] == ['omnivoice:male', 'omnivoice:bright']
        assert speaker_identity.prepare_speakers(str(wav), segments, 'test') == cached
        assert engine.call_count == 1
    assert wav.read_bytes() == b'source speech fixture'
    assert not list(directory.glob('*.tmp'))


def test_cpu_loader_forces_onnx_fp32_local_codec_even_on_gpu_machine(tmp_path):
    original = Mock()
    module = SimpleNamespace(OnnxV3LiteEngine=original)
    sdk = Mock()
    sdk.Vieneu.side_effect = lambda **options: module.OnnxV3LiteEngine(**options)
    with patch.dict(sys.modules, {'vieneu': sdk, 'vieneu._v3_turbo_engine': SimpleNamespace(onnx_runtime_lite=module)}):
        vieneu_tts._load_model(tmp_path, 'cpu')
    options = sdk.Vieneu.call_args.kwargs
    assert options['device'] == 'cpu' and options['backend'] == 'onnx' and options['precision'] == 'fp32'
    assert options['max_batch_size'] == 1
    assert module.OnnxV3LiteEngine is original


def test_gpu_without_cuda_is_blocked_not_silently_cpu(tmp_path):
    sdk = Mock()
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with patch.dict(sys.modules, {'vieneu': sdk, 'torch': torch}), pytest.raises(RuntimeError, match='NVIDIA'):
        vieneu_tts._load_model(tmp_path, 'gpu')
    assert not sdk.Vieneu.called


def test_core_import_stays_lightweight():
    result = subprocess.run([sys.executable, '-c',
        "import sys; import haizflow.pipeline.vieneu_tts; "
        "assert not any(x in sys.modules for x in ('torch','vieneu','sea_g2p','soundfile'))"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_worker_has_encoding_headroom_and_no_expression_or_watermark_injection(tmp_path):
    model = Mock()
    model.infer.return_value = np.full(48000, 1.5, dtype=np.float32)
    output = tmp_path / 'voice.wav'
    status = tmp_path / 'status.json'
    with (patch.object(vieneu_tts, 'verify_assets', return_value=tmp_path),
          patch.object(vieneu_tts, 'prepare_runtime', return_value=tmp_path),
          patch.object(vieneu_tts, '_load_model', return_value=model),
          patch('haizflow.pipeline.tts_quality.validate_speech_waveform'),
          patch('haizflow.pipeline.tts_quality.validate_short_phrase_audio')):
        vieneu_tts._worker(dict(root=str(tmp_path), device='cpu', status=str(status),
                                items=[dict(text='Xin chào.', voice='vieneu:Hải Đăng', wav=str(output))]))
    waveform, rate = sf.read(output)
    assert rate == 48000 and np.max(np.abs(waveform)) <= .891
    assert model.infer.call_args.args[0] == 'Xin chào.'
    assert model.infer.call_args.kwargs['apply_watermark'] is False
    assert model.infer.call_args.kwargs['batch_size'] == 1
    assert json.loads(status.read_text())['completed'] == 1


def test_silent_wave_is_never_marked_complete_or_written(tmp_path):
    model = Mock()
    model.infer.return_value = np.zeros(48000, dtype=np.float32)
    output, status = tmp_path / 'voice.wav', tmp_path / 'status.json'
    with (patch.object(vieneu_tts, 'verify_assets', return_value=tmp_path),
          patch.object(vieneu_tts, 'prepare_runtime', return_value=tmp_path),
          patch.object(vieneu_tts, '_load_model', return_value=model),
          pytest.raises(RuntimeError, match='VieNeu')):
        vieneu_tts._worker(dict(root=str(tmp_path), device='cpu', status=str(status),
                                items=[dict(text='Xin chào.', voice='vieneu:Hải Đăng', wav=str(output))]))
    assert not output.exists()
    assert json.loads(status.read_text())['completed'] == 0


@pytest.mark.parametrize('provider', ['vieneu', 'vieneu-gpu'])
def test_clone_dispatch_keeps_reference_and_skips_native_preset(tmp_path, provider):
    reference = tmp_path / 'my-voice.wav'
    reference.write_bytes(b'reference')
    video = SimpleNamespace(files={'voice_reference': str(reference)})
    with patch.object(tts, 'get_video', return_value=video), patch.object(vieneu_tts, 'synthesize_to_mp3') as run:
        tts.generate_single_voice('Xin chào.', 'output.mp3', 'vieneu:clone', 'test', provider=provider)
    assert run.call_args.args[1] == 'vieneu:clone'
    assert run.call_args.kwargs['reference_path'] == str(reference)


def test_clone_without_reference_is_blocked_before_model_verification(tmp_path):
    with patch.object(vieneu_tts, 'verify_assets') as verify, pytest.raises(ValueError, match='mẫu giọng'):
        vieneu_tts.synthesize_batch_to_mp3([{'text': 'Xin chào.', 'voice': 'vieneu:clone',
            'reference_path': str(tmp_path / 'missing.wav'), 'output_path': str(tmp_path / 'out.mp3')}], 'test')
    verify.assert_not_called()


def test_clone_worker_uses_sdk_ref_audio_without_transcript_or_preset(tmp_path):
    model = Mock()
    model.infer.return_value = np.ones(48000, dtype=np.float32) * .1
    reference = tmp_path / 'reference.wav'
    reference.write_bytes(b'reference fixture')
    with patch.object(vieneu_tts, 'verify_assets', return_value=tmp_path), \
            patch.object(vieneu_tts, 'prepare_runtime', return_value=tmp_path), \
            patch.object(vieneu_tts, '_load_model', return_value=model), \
            patch('haizflow.pipeline.tts_quality.validate_speech_waveform'), \
            patch('haizflow.pipeline.tts_quality.validate_short_phrase_audio'):
        vieneu_tts._worker(dict(root=str(tmp_path), device='cpu', status=str(tmp_path / 'status.json'),
            items=[dict(text='Xin chào.', voice='vieneu:clone', reference_path=str(reference),
                        wav=str(tmp_path / 'out.wav'))]))
    options = model.infer.call_args.kwargs
    assert options['ref_audio'] == str(reference) and options['denoise']
    assert 'voice' not in options and 'ref_text' not in options
    assert options['apply_watermark'] is False


@pytest.mark.parametrize('provider,engine', [('vieneu', 'engine-cpu-py313'), ('vieneu-gpu', 'engine-cuda128-py313')])
def test_clone_requires_no_extra_asr_model(provider, engine):
    manager = ResourcePackManager()
    with patch.object(manager, 'status', return_value='missing'):
        assert manager.required_packs('voice', {'provider': provider, 'voice_clone': True}) == [engine, 'model-vieneu']
