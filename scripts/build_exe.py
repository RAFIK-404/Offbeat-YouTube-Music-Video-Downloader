"""Build a single Windows EXE; download tools are fetched on first launch."""
import argparse
from importlib import metadata
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--work', type=Path, default=ROOT / 'build-exe')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    marker = work / 'single-file.json'
    marker.write_text('{"layout":"adjacent-app-folder"}\n',encoding='utf-8')
    texts = ['OFFBEAT 1.3.1 — LICENSES AND THIRD-PARTY NOTICES\n']
    for filename in ('LICENSE','THIRD-PARTY-NOTICES.md'):
        texts.append(filename + '\n\n' + (ROOT / filename).read_text(encoding='utf-8'))
    for filename in ('Microsoft-WebView2-1.0.3856.49-LICENSE.txt','Microsoft-WebView2-1.0.3856.49-NOTICE.txt'):
        texts.append(filename + '\n\n' + (ROOT / 'third-party' / filename).read_text(encoding='utf-8'))
    texts.append('Python\n\n' + (Path(sys.base_prefix) / 'LICENSE.txt').read_text(encoding='utf-8'))
    for distribution in sorted(metadata.distributions(), key=lambda d:d.metadata['Name'].lower()):
        for file in sorted(distribution.files or [],key=str):
            if file.name.lower().startswith(('license','copying','notice')) and '.dist-info/' in str(file).replace('\\','/'):
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    texts.append(distribution.metadata['Name'] + ' ' + distribution.version + ' / ' + file.name + '\n\n' + path.read_text(encoding='utf-8',errors='replace'))
    notices = work / 'THIRD-PARTY-LICENSES.txt'
    notices.write_text(('\n\n' + '=' * 72 + '\n\n').join(texts),encoding='utf-8')
    command = [sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','Offbeat-1.3.1-Windows-x64','--icon',str(ROOT / 'web/app.ico'),'--distpath',str(args.dist.resolve()),'--workpath',str(work),'--specpath',str(work),'--add-data',str(ROOT / 'web') + ';web','--add-data',str(marker) + ';.','--add-data',str(notices) + ';.','--collect-all','webview','--exclude-module','PyQt5','--exclude-module','PyQt6','--exclude-module','PySide2','--exclude-module','PySide6',str(ROOT / 'app.py')]
    subprocess.run(command,check=True)
    print('Standalone EXE:',args.dist.resolve() / 'Offbeat-1.3.1-Windows-x64.exe')


if __name__ == '__main__':
    main()
