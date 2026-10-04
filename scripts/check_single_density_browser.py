"""Minimal single-density browser check with mocked inference; no MCMC."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import subprocess
import tempfile
import time
import urllib.request

from websockets.asyncio.client import connect


async def main():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); app_port = listener.getsockname()[1]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'chronologer_app.main:app', '--port', str(app_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    with tempfile.TemporaryDirectory(prefix='chrono-single-', ignore_cleanup_errors=True) as directory:
        for _ in range(150):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{app_port}/', timeout=1).close(); break
            except OSError:
                await asyncio.sleep(.2)
        root = Path(directory)
        browser = subprocess.Popen([
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '--headless=new',
            '--disable-gpu', '--no-first-run', '--remote-debugging-port=0',
            '--user-data-dir=' + str(root / 'profile'), 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
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
                await call('Page.navigate', url=f'http://127.0.0.1:{app_port}/')
                await wait("!!document.querySelector('#add-summary')", timeout=20)
                await js("window.state=(await import('/js/project-state.js')).projectState")
                await wait("!!state.data", timeout=20)
                await js("""window.state=(await import('/js/project-state.js')).projectState;
                    const project=structuredClone(state.data);
                    project.summaries=[{id:'legacy',label:'Legacy density',model:'density',events:[],parameters:{}}];state.replace(project);
                    document.querySelector('#summarize-tab').click();""")
                assert await js("document.querySelector('.summary-card select').value==='single_density'")
                await js("""state.setSummaries([]);document.querySelector('#add-summary').click();
                    const item=state.data.summaries[0];
                    const events=[{id:'normal',distribution:'normal',parameters:{mean:2500,sd:30}},
                      {id:'uniform',distribution:'uniform',parameters:{lower:2400,upper:2600}},
                      {id:'north',distribution:'calrcarbon',parameters:{c14_mean:2500,c14_err:30,curve:'intcal20'}},
                      {id:'south',distribution:'calrcarbon',parameters:{c14_mean:2500,c14_err:30,curve:'shcal20'}}];
                    state.setSummaries([{...item,events,parameters:{sampling:{draws:4,tune:4,chains:1,cores:1}}}]);window.sent=null;window.originalFetch=window.fetch;
                    const marginal=(name,calendar)=>({name,label:name,calendar,t_values:calendar?[-2600,-2500,-2400]:[10,20,30],pdf_values:[0,.01,0]});
                    window.mock={model:'single_density',coordinate_system:'negative_bp',sampling:{draws:4,tune:4,chains:1,cores:1,random_seed:912},
                      divergences:0,warnings:[],elapsed_seconds:1,diagnostics:{},
                      density:{t_values:[-3000,-2500,-2000],pdf_values:[0,.002,0],lower_values:[0,.001,0],upper_values:[0,.003,0]},
                      posterior:{type:'xarray.DataTree',variables:['tau_mu','tau_sd','tau'],sizes:{chain:1,draw:4,event:4}},
                      marginals:{parameters:[marginal('tau_mu',true),marginal('tau_sd',false)],events:events.map((e,index)=>({id:e.id,index,t_values:[-2550,-2500,-2450],pdf_values:[0,.02,0]}))}};
                    const job={id:'mock',label:'Single density',status:'completed',stage:'Completed',total:8,completed:8,elapsed_seconds:1};
                    window.fetch=async(url,options)=>{
                      let data;
                      if(url==='/api/single_density/jobs'){sent=JSON.parse(options.body);data=job;}
                      else if(url==='/api/jobs/mock')data=job;
                      else if(url==='/api/jobs/mock/result')data=mock;
                      else if(url==='/api/jobs')data={jobs:sent?[job]:[],max_workers:2,log_directory:''};
                      else return originalFetch(url,options);
                      return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
                    };
                    document.querySelector('.summary-fit').click();""")
                await wait("!!state.data.summaries[0].saved_run && !!document.querySelector('[data-layer=summary-density] path')", timeout=20)
                assert await js("sent.events.length===4 && !!sent.settings && !sent.determinations && state.data.summaries[0].saved_run.model==='single_density' && document.querySelector('.summary-fit').textContent==='Fit single density'")
                assert await js("""const encoded=await originalFetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)});
                    if(!encoded.ok)throw Error(await encoded.text());
                    const decoded=await originalFetch('/api/projects/decode',{method:'POST',body:await encoded.blob()});
                    if(!decoded.ok)throw Error(await decoded.text());
                    (await decoded.json()).summaries[0].saved_run.model==='single_density'""")
                assert not errors, errors
                await js("document.querySelector('[data-mode=simulate]').click()")
                assert await js("!document.querySelector('.simulation-download') && !!document.querySelector('.simulation-options') && state.data.summaries[0].events.length===4")
                await js("""const family=document.querySelector('[data-simulation=distribution]');
                    family.value='normal';family.dispatchEvent(new Event('change'));""")
                assert await js("!document.querySelector('[data-simulation=curve]')")
                await js("""for(const [key,value] of Object.entries({n:3,draws:4,error:20})) {
                    const input=document.querySelector(`[data-simulation=${key}]`);input.value=value;input.dispatchEvent(new Event('input'));}
                    const family=document.querySelector('[data-simulation=distribution]');
                    family.value='calrcarbon';family.dispatchEvent(new Event('change'));""")
                assert await js("!!document.querySelector('[data-simulation=curve]') && state.data.summaries[0].parameters.simulation.n===3 && state.data.summaries[0].parameters.simulation.error===20")
                await js("""const events=[2400,2500,2600].map((age,index)=>({id:`Sim-${index+1}`,distribution:'calrcarbon',datum:'BP1950',parameters:{c14_mean:age,c14_err:20,curve:'intcal20'}}));
                    const {posterior,...result}=mock;
                    window.mock={...result,mode:'simulate',sampling:{draws:4,tune:0,chains:1,cores:1,random_seed:912},
                      prior:{...posterior,sizes:{chain:1,draw:4,event:3}},
                      simulation:{settings:structuredClone(state.data.summaries[0].parameters.simulation),events,exported_draw:0},
                      marginals:{parameters:result.marginals.parameters,events:events.map((e,index)=>({...result.marginals.events[index],id:e.id}))}};
                    const inferenceFetch=window.fetch;
                    window.fetch=async(url,options)=>{
                      if(url==='/api/simulation/jobs'){sent=JSON.parse(options.body);return new Response(JSON.stringify({id:'mock',label:'Simulation',status:'completed',stage:'Completed',total:4,completed:4,elapsed_seconds:1}),{status:200,headers:{'Content-Type':'application/json'}});}
                      return inferenceFetch(url,options);
                    };
                    document.querySelector('.summary-fit').click();""")
                await wait("!!document.querySelector('.simulation-download')", timeout=20)
                assert await js("sent.simulation.n===3 && !sent.events && !sent.sampling && document.querySelector('.summary-result').innerText.includes('Prior') && state.data.summaries[0].saved_run.events.length===0")
                assert await js("""const encoded=await originalFetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)});
                    if(!encoded.ok)throw Error(await encoded.text());
                    const decoded=await originalFetch('/api/projects/decode',{method:'POST',body:await encoded.blob()});
                    if(!decoded.ok)throw Error(await decoded.text());
                    (await decoded.json()).summaries[0].saved_run.result.mode==='simulate'""")
                await js("""window.downloaded=null;const originalURL=URL.createObjectURL;
                    URL.createObjectURL=blob=>{blob.text().then(text=>window.downloaded=text);return originalURL(blob);};
                    HTMLAnchorElement.prototype.click=function(){};
                    document.querySelector('.simulation-download').click();""")
                await wait("!!window.downloaded", timeout=5)
                csv = await js("window.downloaded")
                from chronologer_app.projects import import_csv
                imported = import_csv(csv.encode('utf-8'), 'simulation.csv')
                assert len(imported['events']) == 3, imported
                await js("document.querySelector('[data-mode=inference]').click()")
                assert await js("!document.querySelector('.simulation-options') && !document.querySelector('.simulation-download') && state.data.summaries[0].events.length===4")
                assert not errors, errors
                print('PASS: single-density inference, simulation controls, plots, importer-ready CSV and archive round trips. No MCMC.')
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            server.terminate(); server.wait(timeout=10)
            await asyncio.sleep(.3)


asyncio.run(main())
