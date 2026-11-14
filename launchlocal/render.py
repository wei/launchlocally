"""Hyperframes rendering on a persistent Daytona sandbox, or explicit local fallback."""
from pathlib import Path
import argparse
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import uuid
from . import common

STATE = common.ROOT / 'docs' / 'daytona-render.json'
CLI = ['npx', '--yes', 'hyperframes@0.9.43']
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def _log(run_dir, message):
    clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', ANSI.sub('', str(message)))
    for line in clean.replace('\r', '\n').splitlines():
        if line.strip():
            common.emit(run_dir, 'renderer', 'log', line)
            print(line, flush=True)


def _local(run_dir, command, cwd=None):
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in process.stdout:
            _log(run_dir, line)
        if process.wait():
            raise RuntimeError(f'Command failed: {command[0]}')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _remote(run_dir, sandbox, command, timeout=900):
    """Stream each sandbox output line into the shared event log."""
    from daytona import SessionExecuteRequest
    session = 'render-' + uuid.uuid4().hex[:12]
    sandbox.process.create_session(session)
    response = sandbox.process.execute_session_command(session, SessionExecuteRequest(command=f'setsid sh -c {shlex.quote(command)} & child=$!; echo $child > /tmp/{session}.pid; wait $child', run_async=True))
    started = time.monotonic()
    seen = 0
    while True:
        logs = sandbox.process.get_session_command_logs(session, response.cmd_id)
        output = logs.output or ((logs.stdout or '') + (logs.stderr or ''))
        if len(output) > seen:
            _log(run_dir, output[seen:])
            seen = len(output)
        status = sandbox.process.get_session_command(session, response.cmd_id)
        if status.exit_code is not None:
            logs = sandbox.process.get_session_command_logs(session, response.cmd_id)
            output = logs.output or ((logs.stdout or '') + (logs.stderr or ''))
            _log(run_dir, output[seen:])
            if status.exit_code:
                raise RuntimeError(f'Sandbox command failed ({status.exit_code}); see renderer events')
            return
        if time.monotonic() - started > timeout:
            # Kill only the process group created for this command, by its recorded PID.
            sandbox.process.exec(f'test ! -f /tmp/{session}.pid || kill -- -$(cat /tmp/{session}.pid)', timeout=10)
            raise TimeoutError('Daytona render command timed out')
        time.sleep(1)


def _sandbox(run_dir):
    from daytona import Daytona, CreateSandboxFromImageParams, Resources
    daytona = Daytona()
    state = common.read_json(STATE) if STATE.exists() else {}
    if state.get('sandbox_id'):
        sandbox = daytona.get(state['sandbox_id'])
        if str(sandbox.state).lower().split('.')[-1] != 'started':
            sandbox.start(timeout=120)
    else:
        started = time.monotonic()
        errors = []
        for cpu, memory in [(4,8),(2,4),(1,2)]:
            try:
                sandbox = daytona.create(CreateSandboxFromImageParams(image='daytonaio/sandbox:0.6.0-slim', resources=Resources(cpu=cpu,memory=memory,disk=10), auto_stop_interval=0,public=True),timeout=180)
                state.update(sandbox_id=sandbox.id,cpu=cpu,memory=memory,start_seconds=round(time.monotonic()-started,2))
                common.write_json(STATE,state)
                break
            except Exception as exc:
                errors.append(str(exc))
                if not any(term in str(exc).lower() for term in ['quota','resource','limit','cpu','memory']):
                    raise
        else:
            raise RuntimeError('Daytona resource allocation failed: ' + '; '.join(errors))
    sandbox.set_autostop_interval(0)
    _log(run_dir, 'Daytona sandbox ' + sandbox.id)
    ready = sandbox.process.exec('test -f /tmp/launchlocal-render-ready',timeout=15)
    if ready.exit_code:
        _remote(run_dir,sandbox,'sudo -n apt-get update -qq && sudo -n apt-get install -y -qq ffmpeg fonts-noto-cjk libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1 libasound2t64 && npx --yes hyperframes@0.9.43 browser ensure && touch /tmp/launchlocal-render-ready',timeout=900)
    return sandbox, state


def render(run_dir: Path, cut: int = 1) -> dict:
    common.load_env()
    run_dir = Path(run_dir).resolve()
    composition = run_dir / 'composition'
    common.emit(run_dir,'renderer','start',f'Rendering cut {cut}',cut=cut)
    try:
        if not (composition / 'index.html').is_file():
            raise FileNotFoundError('Run build_baseline before rendering')
        if cut == 2 and (run_dir / 'video.mp4').exists() and not (run_dir / 'video.cut1.mp4').exists():
            import shutil
            shutil.copy2(run_dir / 'video.mp4',run_dir / 'video.cut1.mp4')
        sandbox_id = None
        preview_url = None
        if os.environ.get('LAUNCHLOCAL_RENDER','daytona') == 'local':
            _log(run_dir,'Explicit local fallback used (LAUNCHLOCAL_RENDER=local)')
            _local(run_dir,CLI + ['browser','ensure'],cwd=composition)
            _local(run_dir,CLI + ['lint'],cwd=composition)
            started = time.monotonic()
            _local(run_dir,CLI + ['render','--fps','30','--workers','2','--quality','standard','--strict','-o',str(run_dir / 'video.mp4')],cwd=composition)
            render_seconds = time.monotonic()-started
            _local(run_dir,['ffmpeg','-hide_banner','-loglevel','error','-y','-ss','1','-i',str(run_dir / 'video.mp4'),'-frames:v','1','-update','1',str(run_dir / 'poster.png')])
        else:
            sandbox,state = _sandbox(run_dir)
            sandbox_id = sandbox.id
            workers = max(1, min(4, int(state.get('cpu', 4))))
            # A unique directory isolates simultaneous runs and prevents stale assets.
            remote = '/home/daytona/launchlocal/' + re.sub(r'[^\w-]','_',run_dir.name) + '-' + uuid.uuid4().hex[:8]
            q = shlex.quote
            with tempfile.TemporaryDirectory(prefix='launchlocal-upload-') as temp:
                archive = Path(temp) / 'composition.tar.gz'
                with tarfile.open(archive,'w:gz') as tar:
                    tar.add(composition,arcname='composition')
                sandbox.process.exec(f'mkdir -p {q(remote)}',timeout=15)
                sandbox.fs.upload_file(str(archive),remote + '/composition.tar.gz')
            _log(run_dir,'Uploaded composition/ to ' + remote)
            _remote(run_dir,sandbox,f'cd {q(remote)} && tar xzf composition.tar.gz && cd composition && npx --yes hyperframes@0.9.43 lint')
            started = time.monotonic()
            _remote(run_dir,sandbox,f'cd {q(remote)}/composition && npx --yes hyperframes@0.9.43 render --fps 30 --workers {workers} --no-low-memory-mode --quality standard --strict -o ../video.mp4')
            render_seconds = time.monotonic()-started
            _remote(run_dir,sandbox,f'ffmpeg -hide_banner -loglevel error -y -ss 1 -i {q(remote)}/video.mp4 -frames:v 1 -update 1 {q(remote)}/poster.png')
            for name in ['video.mp4','poster.png']:
                sandbox.fs.download_file(remote + '/' + name,str(run_dir / name))
            index = '<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><title>LaunchLocal</title><body style="margin:0;background:#0a0a0a;color:white;font-family:sans-serif"><video controls playsinline poster="poster.png" src="video.mp4" style="width:100%;max-height:95vh"></video></body></html>'
            sandbox.fs.upload_file(index.encode(), remote + '/index.html')
            # One persistent static server, serving each run by directory name.
            sandbox.fs.upload_file(str(common.ROOT / 'template' / 'serve.py'), '/home/daytona/launchlocal/serve.py')
            serve = 'cd /home/daytona/launchlocal && (test -f /tmp/launchlocal-server-v2 || (test ! -f /tmp/launchlocal-server.pid || kill $(cat /tmp/launchlocal-server.pid); rm -f /tmp/launchlocal-server.pid; touch /tmp/launchlocal-server-v2)); cd /home/daytona/launchlocal && (test -f /tmp/launchlocal-server.pid && kill -0 $(cat /tmp/launchlocal-server.pid) 2>/dev/null || (nohup python3 serve.py /home/daytona/launchlocal >/tmp/launchlocal-server.log 2>&1 & echo $! > /tmp/launchlocal-server.pid))'
            sandbox.process.exec(serve,timeout=15)
            preview_url = sandbox.get_preview_link(8000).url.rstrip('/') + '/' + remote.rsplit('/',1)[1] + '/'
            state.update(last_remote_dir=remote,last_preview_url=preview_url,last_render_seconds=round(render_seconds,2),last_cut=cut)
            common.write_json(STATE,state)
            _log(run_dir,'Public preview may show Daytona warning on phones; proxy requests with X-Daytona-Skip-Preview-Warning: true')
        result = dict(video='video.mp4',poster='poster.png',preview_url=preview_url,sandbox_id=sandbox_id,render_seconds=round(render_seconds,2),cut=cut)
        common.write_json(run_dir / 'render.json',result)
        for name in ['video.mp4','poster.png','render.json']:
            common.emit(run_dir,'renderer','artifact',name,path=name)
        common.emit(run_dir,'renderer','done','Render complete',**result)
        return result
    except Exception as exc:
        common.emit(run_dir,'renderer','error',str(exc),cut=cut)
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('run_id',nargs='?',default='fixture')
    parser.add_argument('--cut',type=int,default=1)
    args=parser.parse_args()
    print(render(common.run_dir(args.run_id),args.cut))
