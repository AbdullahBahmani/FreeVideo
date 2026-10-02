"""Decode real benchmark media natively with PyAV; no browser or Docker required."""
import argparse
import hashlib
import json
from pathlib import Path

import av
import numpy as np
from PIL import Image


def inspect(path, *, width=1344, height=768, frames=243, fps=24):
    selected = {}
    indices = tuple(round((frames - 1) * i / 3) for i in range(4))
    thumb_height = round(448 * height / width)
    count = 0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        geometry = (stream.width, stream.height, str(stream.average_rate))
        video_info = {'width': stream.width, 'height': stream.height, 'avg_frame_rate': str(stream.average_rate),
                      'start_time': float((stream.start_time or 0) * stream.time_base),
                      'duration': float(stream.duration * stream.time_base), 'codec': stream.codec_context.name}
        stream.codec_context.thread_count = 2
        for frame in container.decode(stream):
            if count in indices:
                selected[count] = frame.to_image().resize((448, thumb_height))
            count += 1
    if geometry != (width, height, str(fps)) or count != frames:
        raise ValueError(f'Unexpected actual video geometry: {geometry}, {count} frames')
    samples, squares, peak = 0, 0., 0.
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        audio_info = {'sample_rate': stream.rate, 'channels': stream.codec_context.channels,
                      'start_time': float((stream.start_time or 0) * stream.time_base),
                      'duration': float(stream.duration * stream.time_base), 'codec': stream.codec_context.name}
        for frame in container.decode(stream):
            values = frame.to_ndarray()
            if np.issubdtype(values.dtype, np.integer):
                values = values.astype(np.float64) / (np.iinfo(values.dtype).max + 1)
            else:
                values = values.astype(np.float64)
            if not np.isfinite(values).all():
                raise ValueError('Non-finite decoded audio')
            samples += values.size
            squares += np.square(values).sum().item()
            peak = max(peak, np.abs(values).max().item())
    rms = (squares / samples) ** .5 if samples else 0.
    if rms <= 1e-8:
        raise ValueError('Decoded audio is silent or missing')
    offset = audio_info['start_time'] - video_info['start_time']
    duration_delta = audio_info['duration'] - video_info['duration']
    # Allow up to one video frame or two AAC packets for container padding.
    # This checks timestamps, not perceptual alignment of sound and action.
    tolerance = max(1 / fps, 2048 / audio_info['sample_rate'])
    if abs(offset) > tolerance or abs(duration_delta) > tolerance:
        raise ValueError('Audio/video timestamps differ beyond codec tolerance: offset=%s, duration_delta=%s' % (offset, duration_delta))
    sheet = Image.new('RGB', (448 * 4, thumb_height))
    for column, index in enumerate(indices):
        sheet.paste(selected[index], (column * 448, 0))
    contact = path.with_name(path.stem + '-contact.jpg')
    sheet.save(contact, quality=92)
    selected[0].save(path.with_suffix('.poster.jpg'), quality=90)
    return {'id': path.stem, 'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'video': dict(video_info, nb_read_frames=count), 'audio': audio_info,
            'audio_rms': rms, 'audio_peak': peak, 'contact_sheet': str(contact),
            'audio_video_start_offset_seconds': offset,
            'audio_minus_video_duration_seconds': duration_delta,
            'timestamp_tolerance_seconds': tolerance, 'timestamp_alignment_pass': True,
            'geometry_frames_fps_pass': True,
            'quality_scope': 'Every frame decoded, non-silent finite audio, timestamps and sampled frames; not a perceptual or semantic sync score'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--ids', nargs='+', default=['city_surfing', 'dawn', 'anime_romance'])
    parser.add_argument('--report', default='media-validation-native.json')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    report = args.directory / args.report
    previous = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
    records = {r['id']: r for r in previous.get('videos', [])}
    for name in args.ids:
        path = args.directory / (name + '.mp4')
        cached = records.get(name)
        if (not args.refresh and cached and previous.get('decoder') == 'PyAV ' + av.__version__
                and cached['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
                and Path(cached['contact_sheet']).is_file() and path.with_suffix('.poster.jpg').is_file()):
            continue
        records[name] = inspect(path)
    report.write_text(json.dumps({'decoder': 'PyAV ' + av.__version__, 'videos': list(records.values())}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps([{'id': r['id'], 'frames': r['video']['nb_read_frames'], 'audio_rms': r['audio_rms']} for r in records.values()]))


if __name__ == '__main__':
    main()
