"""Windows acceptance: real CSV -> UI -> PyMC -> plot -> three real exports.

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

                async def wait(expression, timeout=300):
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
                await js("""window.state=(await import('/js/project-state.js')).projectState;
                    window.responses=[];const originalFetch=window.fetch;
                    window.fetch=async(...args)=>{const r=await originalFetch(...args);if(String(args[0]).startsWith('/api/jobs/') && String(args[0]).endsWith('/result') && r.ok)responses.push(await r.clone().json());return r};
                    document.querySelector('#project-tab').click();
                    {let dt=new DataTransfer();dt.items.add(new File(['id,c14_mean,c14_err,curve\\nA,2500,30,intcal20\\nB,2550,30,intcal20\\nC,2600,30,intcal20\\n'],'density.csv',{type:'text/csv'}));
                    let input=document.querySelector('#csv-file');input.files=dt.files;input.dispatchEvent(new Event('change'))} """)
                await wait('state.data.events.length===3 && !state.busy')
                await js("""document.querySelector('#summarize-tab').click();document.querySelector('#add-summary').click();
                    {let card=document.querySelector('.summary-card');let name=card.querySelector('input');name.value='Density benchmark';name.dispatchEvent(new Event('input'));
                    card.querySelector('details').open=true;card.querySelectorAll('[type=checkbox]').forEach(c=>c.click());
                    [...card.querySelectorAll('button')].find(b=>b.textContent==='Add selected').click()}
                    for(const [key,value] of Object.entries({older:3500,younger:1500,mean:2500,mean_sd:500,sd_scale:400})){
                    let input=document.querySelector(`[data-setting=${key}]`);input.value=value;input.dispatchEvent(new Event('input'))}
                    for(const [key,value] of Object.entries({draws:250,tune:250,chains:2})){
                    let input=document.querySelector(`[data-sampling=${key}]`);input.value=value;input.dispatchEvent(new Event('input'))}
                    document.querySelector('.summary-fit').click();""")
                assert await js("document.querySelector('.summary-card').getAttribute('aria-busy')==='true'")
                await wait("!document.querySelector('#run-monitor').hidden")
                await js("document.querySelector('#phase-tab').click()")
                assert await js("!document.querySelector('#run-monitor').hidden && !document.querySelector('#phase-panel').hidden")
                await wait("!![...document.querySelectorAll('.run-description')].find(n=>n.textContent.includes('Density benchmark') && n.textContent.includes('tuning + draws'))")
                await js("document.querySelector('#summarize-tab').click()")
                await wait("!!document.querySelector('[data-layer=summary-density] path') && !document.querySelector('.summary-fit').disabled")
                assert await js("responses.length===1 && Object.values(responses[0].density).every(a=>a.length===512 && a.every(Number.isFinite)) && responses[0].posterior.variables.includes('tau_mu')")
                assert await js("![...document.querySelectorAll('[data-layer=summary-density] path')].some(p=>/NaN|Infinity/.test(p.getAttribute('d')))")
                assert await js("document.querySelectorAll('.summary-parameter-plot').length===2 && document.querySelectorAll('[data-layer=summary-density] [data-event-index]').length===3")
                assert await js("document.querySelectorAll('.summary-parameter-plots .domain-controls').length===0 && document.querySelectorAll('.summary-parameter-plots .interactive-chart').length===0")
                assert await js("document.querySelector('.summary-parameter-plots').getBoundingClientRect().bottom <= document.querySelector('[data-layer=summary-density]').closest('svg').getBoundingClientRect().top")
                assert await js("document.querySelector('[data-parameter=tau_mu]').getBoundingClientRect().top===document.querySelector('[data-parameter=tau_sd]').getBoundingClientRect().top && !document.querySelector('.summary-card').textContent.toLowerCase().includes('population')")
                # Repeat with fixed seed to measure another run, not convergence.
                await js("document.querySelector('.summary-fit').click()")
                await wait("responses.length===2 && !!document.querySelector('[data-layer=summary-density] path') && !document.querySelector('.summary-fit').disabled")
                timings = await js('responses.map(r=>r.elapsed_seconds)')
                await js("document.querySelector('#run-list button').click()")
                await wait("document.querySelector('#run-log-text').textContent.includes('Sampling')")
                assert await js("document.querySelector('#run-log-location').textContent.includes('density-')")
                for extension in ('svg', 'png', 'pdf'):
                    await js(f"document.querySelector('.summary-result > .plot-tools .plot-export-format').value='{extension}';document.querySelector('.summary-result > .plot-tools .plot-export-button').click()")
                    await wait(f"document.querySelector('.summary-result > .plot-tools .plot-export-status').textContent==='{extension.upper()} downloaded'", timeout=60)
                    target = downloads / f'Density benchmark.{extension}'
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
                Path('docs/screenshots/density-benchmark.png').write_bytes(base64.b64decode(screenshot['data']))
                # Saved plot arrays survive codec and restore without inference.
                assert await js("""{const r=await fetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)});
                    const reopened=await (await fetch('/api/projects/decode',{method:'POST',body:await r.blob()})).json();
                    window.savedDocument=reopened;
                    JSON.stringify(reopened.summaries)===JSON.stringify(state.data.summaries) && !!reopened.summaries[0].saved_run && !('samples' in reopened.summaries[0].saved_run.result.posterior)}""")
                await js("window.savedPaths=[...document.querySelectorAll('[data-layer=summary-density] path')].map(p=>p.getAttribute('d'));state.replace(savedDocument)")
                await wait("!!document.querySelector('[data-layer=summary-density] path')")
                assert await js("JSON.stringify(state.data.summaries[0].saved_run.result)===JSON.stringify(responses[1]) && document.querySelectorAll('.summary-parameter-plot').length===2 && !state.dirty && responses.length===2")
                await js("{let input=document.querySelector('[data-setting=mean]');input.value='2600';input.dispatchEvent(new Event('input'))}")
                assert await js("!document.querySelector('[data-layer=summary-density]')")
                await js("window.confirm=()=>true;[...document.querySelectorAll('button')].find(b=>b.textContent==='Load saved run').click()")
                await wait("!!document.querySelector('[data-layer=summary-density]')")
                assert await js("state.data.summaries[0].parameters.mean===2500 && responses.length===2")
                await js("[...document.querySelectorAll('button')].find(b=>b.textContent==='Remove saved result').click()")
                assert await js("!state.data.summaries[0].saved_run && !document.querySelector('[data-layer=summary-density]') && state.dirty")
                assert not errors, errors
                print(json.dumps({'result': 'PASS: CSV -> Summary -> real PyMC -> density/band -> SVG/PNG/vector PDF; saved settings and stale-result invalidation',
                                  'worker_seconds_first_and_repeat': timings,
                                  'divergences': await js('responses.map(r=>r.divergences)')}))
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            await asyncio.sleep(.5)


asyncio.run(main())
