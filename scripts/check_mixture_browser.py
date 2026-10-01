"""Windows acceptance: 20-date CSV -> K=5 mixture -> plot -> three real exports.

Run with chronoapp and the local server on port 8000. No inference responses or
downloads are mocked. Uses the development environment's websockets package.
"""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

from websockets.asyncio.client import connect


async def main():
    with tempfile.TemporaryDirectory(prefix='chrono-density-') as directory:
        root = Path(directory)
        downloads = root / 'downloads'
        downloads.mkdir()
        browser = subprocess.Popen([
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
            '--disable-gpu', '--no-first-run', '--remote-debugging-port=0',
            '--user-data-dir=' + str(root / 'profile'), 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            portfile = root / 'profile' / 'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists():
                    break
                await asyncio.sleep(.1)
            port = portfile.read_text().splitlines()[0]
            pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
            async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page'), max_size=30000000) as ws:
                seq, errors = 0, []

                async def call(method, **params):
                    nonlocal seq
                    seq += 1
                    await ws.send(json.dumps(dict(id=seq, method=method, params=params)))
                    while True:
                        reply = json.loads(await ws.recv())
                        if reply.get('method') == 'Runtime.exceptionThrown':
                            errors.append(reply)
                        if reply.get('id') == seq:
                            assert 'error' not in reply, reply
                            return reply.get('result', {})

                async def js(expression):
                    result = await call('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True, replMode=True)
                    assert 'exceptionDetails' not in result, result
                    return result.get('result', {}).get('value')

                async def wait(expression, timeout=900):
                    start = time.monotonic()
                    while time.monotonic() - start < timeout:
                        if await js(expression):
                            return
                        await asyncio.sleep(.25)
                    raise AssertionError((expression, errors, await js('document.body.innerText')))

                await call('Runtime.enable')
                await call('Browser.setDownloadBehavior', behavior='allow', downloadPath=str(downloads))
                await call('Emulation.setDeviceMetricsOverride', width=1280, height=1400, deviceScaleFactor=1, mobile=False)
                await call('Page.navigate', url='http://127.0.0.1:8000')
                await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                csv = Path('docs/examples/density-benchmark.csv').read_text()
                await js("window.fixtureCSV=" + json.dumps(csv))
                await js("""window.state=(await import('/js/project-state.js')).projectState;
                    window.responses=[];const originalFetch=window.fetch;
                    window.fetch=async(...args)=>{const r=await originalFetch(...args);if(String(args[0]).startsWith('/api/jobs/') && String(args[0]).endsWith('/result') && r.ok)responses.push(await r.clone().json());return r};
                    document.querySelector('#project-tab').click();
                    {let dt=new DataTransfer();dt.items.add(new File([fixtureCSV],'density-benchmark.csv',{type:'text/csv'}));
                    let input=document.querySelector('#csv-file');input.files=dt.files;input.dispatchEvent(new Event('change'))}""")
                await wait('state.data.events.length===20 && !state.busy')
                await js("""document.querySelector('#summarize-tab').click();document.querySelector('#add-summary').click();
                    {let card=document.querySelector('.summary-card');let name=card.querySelector('input');name.value='Mixture benchmark';name.dispatchEvent(new Event('input'));
                    let model=card.querySelector('select');model.value='mixture';model.dispatchEvent(new Event('change'));
                    card=document.querySelector('.summary-card');card.querySelector('details').open=true;
                    [...card.querySelectorAll('button')].find(b=>b.textContent==='Add all').click()}
                    document.querySelector('.summary-fit').click();""")
                assert await js("document.querySelector('.summary-card').getAttribute('aria-busy')==='true'")
                await wait("!document.querySelector('#run-monitor').hidden")
                await js("document.querySelector('#phase-tab').click()")
                assert await js("!document.querySelector('#run-monitor').hidden && !document.querySelector('#phase-panel').hidden")
                await wait("!![...document.querySelectorAll('.run-description')].find(n=>n.textContent.includes('Mixture benchmark') && n.textContent.includes('tuning + draws'))")
                await js("document.querySelector('#summarize-tab').click()")
                await wait("!!document.querySelector('[data-layer=summary-density] path') && !document.querySelector('.summary-fit').disabled")
                assert await js("responses.length===1 && responses[0].model==='gaussian_mixture' && responses[0].posterior.sizes.component===5")
                assert await js("document.querySelectorAll('[data-layer=summary-density] [data-event-index]').length===20 && !document.querySelector('.summary-parameter-plot')")
                assert await js("![...document.querySelectorAll('[data-layer=summary-density] path')].some(p=>/NaN|Infinity/.test(p.getAttribute('d')))")
                timings = await js('responses.map(r=>r.elapsed_seconds)')
                await js("document.querySelector('#run-list button').click()")
                await wait("document.querySelector('#run-log-text').textContent.includes('Sampling')")
                assert await js("document.querySelector('#run-log-location').textContent.includes('density-')")
                for extension in ('svg', 'png', 'pdf'):
                    await js(f"document.querySelector('.summary-result > .plot-tools .plot-export-format').value='{extension}';document.querySelector('.summary-result > .plot-tools .plot-export-button').click()")
                    await wait(f"document.querySelector('.summary-result > .plot-tools .plot-export-status').textContent==='{extension.upper()} downloaded'", timeout=60)
                    target = downloads / f'Mixture benchmark.{extension}'
                    for _ in range(100):
                        if target.exists():
                            break
                        await asyncio.sleep(.1)
                    data = target.read_bytes()
                    assert len(data) > 1000
                    if extension == 'svg':
                        assert b'<path' in data and b'<image' not in data
                    elif extension == 'png':
                        assert data.startswith(b'\x89PNG\r\n\x1a\n')
                    else:
                        assert data.startswith(b'%PDF-') and b'/Subtype /Image' not in data
                await js("document.documentElement.dataset.theme='dark';document.querySelector('.summary-result').scrollIntoView({block:'center'})")
                screenshot = await call('Page.captureScreenshot', format='png', captureBeyondViewport=True)
                Path('docs/screenshots/mixture-benchmark.png').write_bytes(base64.b64decode(screenshot['data']))
                # Settings survive codec; raw result/model objects never enter the project.
                assert await js("""{const r=await fetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)});
                    const reopened=await (await fetch('/api/projects/decode',{method:'POST',body:await r.blob()})).json();
                    JSON.stringify(reopened.summaries)===JSON.stringify(state.data.summaries) && !('posterior' in reopened.summaries[0])}""")
                await js("{let input=document.querySelector('[data-setting=K_max]');input.value='4';input.dispatchEvent(new Event('input'))}")
                assert await js("!document.querySelector('[data-layer=summary-density]')")
                assert not errors, errors
                Path('docs/mixture-benchmark-result.json').write_text(json.dumps(await js('responses[0]'), indent=2))
                print(json.dumps({'result': 'PASS: CSV -> Summary -> real PyMC -> density/band -> SVG/PNG/vector PDF; saved settings and stale-result invalidation',
                                  'worker_seconds': timings, 'weights': await js('responses[0].diagnostics.weight_mean'), 'weight_below_005': await js('responses[0].diagnostics.weight_below_005'),
                                  'divergences': await js('responses.map(r=>r.divergences)')}))
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            await asyncio.sleep(.5)


if __name__ == '__main__':
    asyncio.run(main())
