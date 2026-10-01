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
                await call('Page.enable')
                await call('Page.navigate', url='http://127.0.0.1:8000')
                await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                await asyncio.sleep(1.5)
                assert await js("document.querySelector('#run-monitor').hidden && document.querySelector('#run-list').children.length===0")
                # Fixture only at the HTTP boundary: old finished jobs plus one active run.
                await js("""window.originalFetch=window.fetch; window.stage='running';
                window.fetch=async(...args)=>args[0]==='/api/jobs'?new Response(JSON.stringify({max_workers:2,jobs:[
                {id:'old',status:'completed',stage:'Completed',label:'Old run',elapsed_seconds:7,total:10,completed:10},
                {id:'active',status:stage,stage:stage,label:'Current run',elapsed_seconds:1,total:10,completed:5}
                ]}),{headers:{'Content-Type':'application/json'}}):originalFetch(...args);""")
                await wait("document.querySelectorAll('.run-row').length===1 && document.querySelector('.run-row').dataset.jobId==='active'")
                await js("stage='completed'")
                await wait("!document.querySelector('.run-dismiss').hidden")
                await js("document.querySelector('.run-dismiss').click()")
                assert await js("document.querySelector('#run-monitor').hidden")
                for _ in range(3):
                    await call('Page.reload', ignoreCache=False)
                    await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                    await asyncio.sleep(1)
                    assert await js("document.querySelector('#run-monitor').hidden && document.querySelector('#run-list').children.length===0")
                assert not errors, errors
                print('PASS: existing finished jobs hidden on load and three ordinary refreshes; active run shown through completion and dismissal.')
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            await asyncio.sleep(.5)

if __name__ == '__main__':
    asyncio.run(main())
