"""Capture the current calibration workspace for the public site using real output.

Run from the repository root in the chronoapp environment (Windows/Chrome).
Uses an isolated local server and browser profile; no inference is performed.
"""
import asyncio
import base64
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import urllib.request

import uvicorn
from websockets.asyncio.client import connect
from chronologer_app.main import app


async def main():
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    browser = None
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.1)
        assert server.started
        with tempfile.TemporaryDirectory(prefix='chrono-site-') as profile:
            browser = subprocess.Popen([
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                '--headless=new', '--disable-gpu', '--no-first-run',
                '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                portfile = Path(profile) / 'DevToolsActivePort'
                for _ in range(100):
                    if portfile.exists():
                        break
                    await asyncio.sleep(.1)
                debug_port = portfile.read_text().splitlines()[0]
                pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json'))
                async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page'), max_size=30000000) as ws:
                    seq = 0
                    async def call(method, **params):
                        nonlocal seq
                        seq += 1
                        await ws.send(json.dumps(dict(id=seq, method=method, params=params)))
                        while True:
                            reply = json.loads(await ws.recv())
                            if reply.get('id') == seq:
                                assert 'error' not in reply, reply
                                return reply.get('result', {})
                    async def js(expression):
                        reply = await call('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
                        assert 'exceptionDetails' not in reply, reply
                        return reply.get('result', {}).get('value')
                    async def wait(expression):
                        for _ in range(300):
                            if await js(expression):
                                return
                            await asyncio.sleep(.1)
                        raise AssertionError(expression)
                    await call('Emulation.setDeviceMetricsOverride', width=1440, height=1100, deviceScaleFactor=1, mobile=False)
                    await call('Page.navigate', url=f'http://127.0.0.1:{port}')
                    await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                    await js("""(() => {
                      const dt = new DataTransfer();
                      dt.items.add(new File(['id,c14_mean,c14_err,curve\\nSample 1,3240,25,intcal20\\nSample 2,4500,30,intcal20\\n'], 'example.csv', {type:'text/csv'}));
                      const input = document.querySelector('#csv-file');
                      input.files = dt.files; input.dispatchEvent(new Event('change'));
                    })()""")
                    await wait("document.querySelectorAll('#determination-rows tr').length===2 && !document.querySelector('#calibrate-button').disabled")
                    await js("document.querySelector('#calibrate-tab').click(); document.querySelector('#calibrate-button').click()")
                    await wait("document.querySelectorAll('.sample-plot').length===2 && !!document.querySelector('#curve-plot path.data-line')")
                    await js("""(() => {
                      if (document.documentElement.dataset.theme !== 'dark') document.querySelector('#theme-toggle').click();
                      const plot = document.querySelector('.sample-plot');
                      plot.querySelector('input[value=curve]').click();
                      plot.querySelector('.domain-older').value = '3550';
                      plot.querySelector('.domain-younger').value = '3350';
                      plot.querySelector('.domain-controls').requestSubmit();
                      document.querySelectorAll('.sample-plot')[1].open = false;
                      window.scrollTo(0,0);
                    })()""")
                    await js("document.fonts.ready")
                    await asyncio.sleep(.5)
                    assert await js("document.documentElement.dataset.theme==='dark' && !!document.querySelector('[data-layer=calibration-curve] path')")
                    metrics = await call('Page.getLayoutMetrics')
                    size = metrics['cssContentSize']
                    shot = await call('Page.captureScreenshot', format='png', captureBeyondViewport=True,
                                      clip=dict(x=0, y=0, width=size['width'], height=size['height'], scale=1))
                    data = base64.b64decode(shot['data'])
                    for target in ['docs/screenshots/curve-overlay.png', 'site/assets/calibration.png']:
                        Path(target).write_bytes(data)
                    print(f"Captured current calibration workspace: {size['width']} x {size['height']}")
            finally:
                browser.terminate()
                browser.wait(timeout=15)
    finally:
        server.should_exit = True
        thread.join(timeout=15)


if __name__ == '__main__':
    asyncio.run(main())
