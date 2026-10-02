"""Presentation check with deterministic plot arrays; no inference is performed."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import urllib.request
import xml.etree.ElementTree as ET

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
    while not server.started:
        await asyncio.sleep(.1)
    with tempfile.TemporaryDirectory(prefix='chrono-labels-') as directory:
        root = Path(directory)
        browser = subprocess.Popen([
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
            '--disable-gpu', '--no-first-run', '--remote-debugging-port=0',
            '--user-data-dir=' + directory, 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            portfile = root / 'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists():
                    break
                await asyncio.sleep(.1)
            debug_port = portfile.read_text().splitlines()[0]
            pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json'))
            async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')) as ws:
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
                downloads = root / 'downloads'
                downloads.mkdir()
                await call('Browser.setDownloadBehavior', behavior='allow', downloadPath=str(downloads))
                await call('Page.navigate', url=f'http://127.0.0.1:{port}')
                for _ in range(100):
                    if await js("document.readyState === 'complete'"):
                        break
                    await asyncio.sleep(.1)
                await js("""(async () => {
                  const {createSummaryPlot} = await import('/js/plots.js');
                  document.body.replaceChildren();
                  const values = {t_values: [-100,-50,0], pdf_values: [.001,.01,.001], lower_values: [0,.005,0], upper_values: [.002,.015,.002]};
                  window.plotChecks = [];
                  for (const model of ['density','gaussian_mixture','ippp_gp']) {
                    const container = document.createElement('section');
                    container.style.width = '760px'; document.body.append(container);
                    const result = {model, density: values, intensity: {...values, rate_values: values.pdf_values}, divergences: 0,
                      marginals: {events: [{...values,id:'Event 1',index:0}], parameters: [{...values,name:'tau_mu',label:'Model location (mean) · cal BP',calendar:true}, {...values,name:'length_scale',label:'GP length scale · years',calendar:false}]}};
                    const before = JSON.stringify(result);
                    createSummaryPlot(container, result, model);
                    if (before !== JSON.stringify(result)) throw Error('Scientific arrays changed');
                    window.plotChecks.push(container);
                  }
                })()""")
                for width in [760, 320]:
                    result = await js(f"""(() => {{
                      plotChecks.forEach(c => c.style.width = '{width}px');
                      window.dispatchEvent(new Event('resize'));
                      return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => {{
                        resolve(plotChecks.map(c => {{
                          const svg = c.querySelector(':scope > svg');
                          const labels = [...svg.querySelectorAll('text')];
                          return {{text: labels.map(t => t.textContent).join('|'),
                            overflow: labels.some(t => {{const b=t.getBoundingClientRect(), s=svg.getBoundingClientRect();return b.left < s.left - 1 || b.right > s.right + 1;}})}};
                        }}));
                      }})));
                    }})()""")
                    for i, plot in enumerate(result):
                        assert 'Years (BP1950)' in plot['text'], plot
                        assert 'cal BP' not in plot['text'], plot
                        assert 'Posterior event-date densities' in plot['text'], plot
                        assert '95% credible interval (pointwise)' in plot['text'], plot
                        assert ('Event intensity (events/year)' if i == 2 else 'Model density (1/year)') in plot['text'], plot
                        assert not plot['overflow'], (width, plot)
                await js("plotChecks[2].querySelector(':scope > .plot-tools .plot-export-button').click()")
                for _ in range(100):
                    files = list(downloads.glob('*.svg'))
                    if files:
                        break
                    await asyncio.sleep(.1)
                exported = files[0].read_text(encoding='utf-8')
                assert 'visual-legend' in exported and 'Posterior event-date densities' in exported
                assert 'Event intensity (events/year)' in exported and 'Years (BP1950)' in exported
                assert 'cal BP' not in exported
                assert 'calibrated as part of modelling' in ''.join(ET.fromstring(exported).itertext())
                assert await js("plotChecks.every(c => !c.textContent.includes('cal BP') && c.textContent.includes('calibrated as part of modelling'))")
                print('PASS: density, mixture and IPPP labels/legends at 760px and 320px; SVG export; arrays preserved')
        finally:
            browser.terminate()
            browser.wait(timeout=15)
            server.should_exit = True
            thread.join(timeout=15)


if __name__ == '__main__':
    asyncio.run(main())
