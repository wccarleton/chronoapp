"""Small Windows/Chrome phase workflow check with mocked inference, no MCMC."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from websockets.asyncio.client import connect


async def main():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='chrono-phase-', ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'chronologer_app.main:app', '--port', str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        browser = None
        try:
            for _ in range(200):
                try:
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1).close()
                    break
                except OSError:
                    await asyncio.sleep(.2)
            browser = subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                '--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0',
                '--user-data-dir=' + str(root / 'profile'), 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            portfile = root / 'profile' / 'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists():
                    break
                await asyncio.sleep(.1)
            debug_port = portfile.read_text().splitlines()[0]
            pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json'))
            async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')) as ws:
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
                    result = await call('Runtime.evaluate', expression=expression, awaitPromise=True,
                                        returnByValue=True, replMode=True)
                    assert 'exceptionDetails' not in result, result
                    return result.get('result', {}).get('value')
                async def wait(expression):
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if await js(expression):
                            return
                        await asyncio.sleep(.1)
                    raise AssertionError((expression, errors, await js('document.body.innerText')))
                await call('Runtime.enable')
                await call('Page.navigate', url=f'http://127.0.0.1:{port}/')
                await wait("!!document.querySelector('#fit-phase')")
                await js("""window.state=(await import('/js/project-state.js')).projectState;
                    const project=structuredClone(state.data);
                    project.events=[{id:'a',label:'Early',distribution:'normal',parameters:{mean:2500,sd:20}},
                      {id:'b',label:'Late',distribution:'normal',parameters:{mean:2200,sd:20}},
                      {id:'outside',label:'Other',distribution:'normal',parameters:{mean:2000,sd:20}}];
                    project.phases=['Early','Late'].map((label,order)=>({id:'p'+order,label,order,distribution:order?'normal':'uniform',parameters:{}}));
                    project.phase_model={parameters:{anchors:'end_start',delta_scale:100,sampling:{draws:4,tune:4,chains:1,cores:1}}};
                    state.replace(project); document.querySelector('#phase-tab').click();
                    if(document.querySelector('#phase-anchors'))throw Error('Model-wide anchors still in run controls');
                    const olderCard=document.querySelector('[data-phase-id="p0"]');
                    const youngerCard=document.querySelector('[data-phase-id="p1"]');
                    if(olderCard.querySelector('.phase-anchor').value!=='0' || youngerCard.querySelector('.phase-anchor-younger').value!=='0.95')throw Error('Legacy anchors were not interpreted');
                    window.finished=false; window.submitted=null; window.originalFetch=window.fetch;
                    const density={t_values:[-2600,-2400,-2100],pdf_values:[.001,.003,.001],lower_values:[0,.001,0],upper_values:[.002,.005,.002]};
                    const estimate=mean=>({mean,lower:mean-10,upper:mean+10});
                    const parameter=(name,calendar)=>({name,label:name,calendar,t_values:calendar?[-2600,-2500,-2400]:[10,20,30],pdf_values:[0,.05,0]});
                    window.fixture={model:'phase',coordinate_system:'negative_bp',sampling:{draws:4,tune:4,chains:1,cores:1,random_seed:912},divergences:0,warnings:[],elapsed_seconds:1,
                      model_diagnostics:{waic:24,se:2,elpd_waic:-12,p_waic:1,n_events:2,n_samples:4,warning:false,notes:[],likelihood:'event_marginal'},
                      posterior:{type:'xarray.DataTree',variables:['mu','scale','tau','delta'],sizes:{chain:1,draw:4,phase:2,event:2,order:1}},
                      phases:project.phases.map((p,i)=>({label:p.label,distribution:p.distribution,density:{...density,t_values:i?[-2300,-2100,-1900]:density.t_values},
                        interval:{p:p.distribution==='uniform'?0:.05,q:p.distribution==='uniform'?1:.95,lower:estimate(-2550),upper:estimate(-2400)},parameters:[parameter('mu',true),parameter('scale',false)]})),
                      marginals:{parameters:[],events:[{id:'a',index:0,t_values:[-2530,-2500,-2470],pdf_values:[0,.03,0]},{id:'b',index:1,t_values:[-2230,-2200,-2170],pdf_values:[0,.03,0]}]},
                      diagnostics:{deltas:[{before:'Early',after:'Late',anchors:[.25,.2],...estimate(100)}]}};
                    const job=()=>({id:'phase-mock',label:'Phase model',status:finished?'completed':'running',stage:finished?'Completed':'Sampling',elapsed_seconds:1,total:8,completed:finished?8:4});
                    window.fetch=async(url,options)=>{
                      let data;
                      if(url==='/api/phases/jobs'){submitted=JSON.parse(options.body);data=job();}
                      else if(url==='/api/jobs/phase-mock')data=job();
                      else if(url==='/api/jobs/phase-mock/result')data=fixture;
                      else if(url==='/api/jobs')data={max_workers:2,jobs:submitted?[job()]:[]};
                      else return originalFetch(url,options);
                      return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
                    };
                    const setAnchor=(card,selector,value)=>{const input=card.querySelector(selector);input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));};
                    setAnchor(youngerCard,'.phase-anchor-younger','.05');
                    document.querySelector('#fit-phase').click();
                    if(submitted || !document.querySelector('#phase-fit-status').textContent.includes('exceed'))throw Error('Equal anchors not rejected');
                    setAnchor(youngerCard,'.phase-anchor','.2');setAnchor(youngerCard,'.phase-anchor-younger','.9');
                    setAnchor(olderCard,'.phase-anchor','.25');setAnchor(olderCard,'.phase-anchor-younger','');
                    document.querySelector('#fit-phase').click();""")
                await wait("!!submitted && !!document.querySelector('.run-cancel')")
                assert await js("submitted.events.length===2 && submitted.phases[0].label==='Early' && submitted.settings.ordered && submitted.phases[0].anchors.length===1 && submitted.phases[0].anchors[0]===.25 && submitted.phases[1].anchors[0]===.2 && submitted.phases[1].anchors[1]===.9")
                await js('finished=true')
                await wait("!!state.data.phase_model.saved_run && document.querySelectorAll('#phase-output .phase-result').length===2")
                assert await js("document.querySelector('#phase-output').innerText.includes('Anchor separations') && document.querySelectorAll('#phase-output svg').length>=2")
                await wait("document.querySelectorAll('.phase-timeline path[data-phase-label]').length===2")
                assert await js("document.querySelector('.phase-model-diagnostics').nextElementSibling.classList.contains('phase-timeline') && document.querySelector('.phase-model-diagnostics').textContent.includes('24')")
                assert await js("""(()=>{
                  const section=document.querySelector('.phase-timeline');
                  const lines=[...section.querySelectorAll('path[data-phase-label]')];
                  return section===document.querySelector('#phase-output').lastElementChild
                    && new Set(lines.map(p=>p.getAttribute('stroke'))).size===2
                    && lines.every(p=>p.getAttribute('d').startsWith('M'))
                    && section.querySelector('svg').textContent.includes('Early')
                    && section.querySelector('svg').textContent.includes('Late')
                    && section.querySelector('.domain-older').value==='2600'
                    && section.querySelector('.domain-younger').value==='1900';
                })()""")
                await js("const anchor=document.querySelector('[data-phase-id=\"p1\"] .phase-anchor');anchor.value='.3';anchor.dispatchEvent(new Event('input',{bubbles:true}))")
                assert await js("document.querySelectorAll('#phase-output .phase-result').length===0 && state.data.phase_model.saved_run.parameters.phases[1].anchors[0]===.2")
                await js("state.updateEvent(0,{parameters:{mean:2510,sd:20}})")
                assert await js("document.querySelectorAll('#phase-output .phase-result').length===0 && !!state.data.phase_model.saved_run")
                await js("[...document.querySelectorAll('#phase-run button')].find(b=>b.textContent==='View saved run').click()")
                assert await js("document.querySelectorAll('#phase-output .phase-result').length===2 && document.querySelector('#phase-output').innerText.includes('historical inputs')")
                # Exercise real archive APIs, including the retained input snapshot.
                assert await js("""const encoded=await originalFetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)});
                    if(!encoded.ok)throw Error(await encoded.text());
                    const decoded=await originalFetch('/api/projects/decode',{method:'POST',body:await encoded.blob()});
                    if(!decoded.ok)throw Error(await decoded.text());
                    const restored=await decoded.json();state.replace(restored);
                    restored.phase_model.saved_run.events[0].parameters.mean===2500 && restored.events[0].parameters.mean===2510""")
                # Collapsing is display state only; reordering still uses the grip.
                await js("""window.beforeCollapse=JSON.stringify(state.data);window.beforeDirty=state.dirty;
                    document.querySelectorAll('.phase-toggle').forEach(button=>button.click());""")
                assert await js("document.querySelectorAll('.phase-card.collapsed').length===2 && document.querySelectorAll('.phase-card .phase-fields[hidden]').length===2 && JSON.stringify(state.data)===beforeCollapse && state.dirty===beforeDirty")
                await js("document.querySelector('[data-phase-id=\"p0\"] .phase-grip').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))")
                assert await js("state.data.phases[1].id==='p0' && document.querySelectorAll('.phase-card.collapsed').length===2")
                # Move the top collapsed card below the other using real pointer events.
                bounds = await js("""[...document.querySelectorAll('.phase-card')].map(card=>{
                    const grip=card.querySelector('.phase-grip').getBoundingClientRect(), box=card.getBoundingClientRect();
                    return {x:grip.x+grip.width/2,y:grip.y+grip.height/2,bottom:box.bottom};})""")
                await call('Input.dispatchMouseEvent', type='mousePressed', x=bounds[0]['x'], y=bounds[0]['y'], button='left', clickCount=1)
                await call('Input.dispatchMouseEvent', type='mouseMoved', x=bounds[0]['x'], y=bounds[1]['bottom'] - 5, button='left', buttons=1)
                await call('Input.dispatchMouseEvent', type='mouseReleased', x=bounds[0]['x'], y=bounds[1]['bottom'] - 5, button='left', clickCount=1)
                assert await js("state.data.phases[0].id==='p0' && document.querySelectorAll('.phase-card.collapsed').length===2")
                await js("document.querySelector('[data-phase-id=\"p0\"] .phase-toggle').click()")
                assert await js("document.querySelector('[data-phase-id=\"p0\"] .phase-toggle').getAttribute('aria-expanded')==='true' && !document.querySelector('[data-phase-id=\"p0\"] .phase-fields').hidden && state.data.phases[0].anchors[0]===.25")
                assert not errors, errors
                print('PASS: phase workflow, collapsible cards, keyboard and pointer grip reordering. No MCMC.')
        finally:
            for process in (browser, server):
                if process:
                    process.terminate()
                    process.wait(timeout=10)
            await asyncio.sleep(.3)


if __name__ == '__main__':
    asyncio.run(main())
