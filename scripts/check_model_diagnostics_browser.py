"""Headless rendering check with fixtures only; no server or inference."""
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
from websockets.asyncio.client import connect


async def main():
    source = (Path(__file__).parents[1] / 'frontend/js/model-diagnostics.js').read_text()
    with tempfile.TemporaryDirectory(prefix='chrono-diags-') as directory:
        browser = subprocess.Popen([
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
            '--disable-gpu', '--no-first-run', '--remote-debugging-port=0',
            '--user-data-dir=' + directory, 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            portfile = Path(directory) / 'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists():
                    break
                await asyncio.sleep(.1)
            port = portfile.read_text().splitlines()[0]
            pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
            async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')) as ws:
                expression = source.replace('export function', 'function') + """
                  const scores = [undefined, {unavailable:'Fixture failure'},
                    {waic:20,se:2,elpd_waic:-10,p_waic:1,n_events:3,n_units:3,n_samples:100,warning:true,notes:['Event likelihood']},
                    {waic:20,se:null,elpd_waic:-10,p_waic:1,n_events:3,n_units:1,n_samples:100,warning:false,notes:['Whole observation window']}];
                  const before = JSON.stringify(scores);
                  for (const score of scores) {
                    const section = document.createElement('section'); document.body.append(section);
                    createModelDiagnostics(section, score);
                  }
                  if (JSON.stringify(scores) !== before) throw Error('Mutated scores');
                  const text = document.body.textContent;
                  for (const expected of ['predates model diagnostics','Fixture failure','ELPD WAIC','reliability warning','Unavailable','Whole observation window']) {
                    if (!text.includes(expected)) throw Error('Missing ' + expected);
                  }
                  if (document.querySelectorAll('details').length !== 4) throw Error('Missing panels');
                  'passed';
                """
                await ws.send(json.dumps(dict(id=1, method='Runtime.evaluate',
                    params=dict(expression=expression, returnByValue=True))))
                while True:
                    reply = json.loads(await ws.recv())
                    if reply.get('id') == 1:
                        assert 'error' not in reply and 'exceptionDetails' not in reply['result'], reply
                        assert reply['result']['result']['value'] == 'passed', reply
                        break
            print('Model diagnostics browser fixtures passed; no inference.')
        finally:
            browser.terminate()
            browser.wait(timeout=10)


if __name__ == '__main__':
    asyncio.run(main())
