"""Collect notices from the exact interpreter and packages used by the launcher.

This is a launcher inventory, not a license inventory for downloaded models or
the separately installed inference environment. No network access is needed.
"""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import sysconfig


def collect(root, destination):
    root, destination = Path(root), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    components = []

    def copy(source, relative):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return relative

    # The official Windows interpreter keeps LICENSE.txt beside python.exe;
    # standalone Unix Python distributions usually keep it in the stdlib.
    python_license = next((path for path in (
        Path(sys.base_prefix) / 'LICENSE.txt',
        Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt',
    ) if path.is_file()), None)
    if python_license is None:
        raise ValueError('The build interpreter is missing its CPython LICENSE.txt')
    components.append(dict(name='CPython', version=platform.python_version(),
                           notices=[copy(python_license, 'python/LICENSE.txt')]))

    for package in ('psutil', 'PyInstaller'):
        distribution = metadata.distribution(package)
        licenses = sorted((file for file in distribution.files or []
                           if file.name.lower().startswith(('license', 'copying', 'notice'))), key=str)
        if not licenses:
            raise ValueError('Build package is missing its license files: ' + package)
        notices = [copy(distribution.locate_file(file), '%s/%02d-%s.txt' %
                        (package, index, file.name)) for index, file in enumerate(licenses)]
        components.append(dict(name=package, version=distribution.version, notices=notices))

    qt_notices = root / 'freevideo_engine/launcher/licenses'
    notice = (qt_notices / 'NOTICE.txt').read_text(encoding='utf-8')
    qt_version = metadata.version('PySide6-Essentials')
    if qt_version not in notice or metadata.version('shiboken6') != qt_version:
        raise ValueError('Update the Qt source/attribution notice for the installed build version')
    files = ['NOTICE.txt', 'LGPL-3.0-only.txt', 'GPL-3.0-only.txt']
    components.append(dict(name='PySide6-Essentials / Qt / Shiboken6', version=qt_version,
                           notices=[copy(qt_notices / name, 'qt/' + name) for name in files]))
    files = []
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            files.append(dict(path=path.relative_to(destination).as_posix(), bytes=len(data),
                              sha256=hashlib.sha256(data).hexdigest()))
    value = dict(schema=1, scope='Launcher interpreter, psutil, PyInstaller bootloader and Qt notices',
                 components=components, files=files)
    (destination / 'inventory.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return value
