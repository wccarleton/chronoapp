"""Optional Windows/Chrome integration check; run from repo root; starts an isolated test server.

Requires the websockets package already available in the development environment.
Native chooser selections are substituted; local API file reads/writes are real.
"""

import asyncio, json, subprocess, tempfile, urllib.request, base64, zipfile
from pathlib import Path
import threading, socket
import uvicorn
from chronologer_app.main import app
from chronologer_app.services import project_files as files
from websockets.asyncio.client import connect

async def main():
    with tempfile.TemporaryDirectory(prefix='chrono-project-') as profile:
        selected = Path(profile) / 'example.chrono'
        choices = []
        def chooser(mode, **kwargs):
            choices.append(mode)
            return selected
        original_chooser = files.choose_file
        files.choose_file = chooser
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        app_port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started: break
            await asyncio.sleep(.1)
        assert server.started
        browser=subprocess.Popen([r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            portfile=Path(profile)/'DevToolsActivePort'
            for _ in range(100):
                if portfile.exists():break
                await asyncio.sleep(.1)
            port=portfile.read_text().splitlines()[0]
            pages=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
            async with connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'),max_size=30000000) as ws:
                seq=0;errors=[]
                async def call(method,**params):
                    nonlocal seq
                    seq+=1
                    await ws.send(json.dumps(dict(id=seq,method=method,params=params)))
                    while True:
                        r=json.loads(await ws.recv())
                        if r.get('method')=='Runtime.exceptionThrown':errors.append(r)
                        if r.get('id')==seq:
                            assert 'error' not in r,r
                            return r.get('result',{})
                async def js(expression):
                    r=await call('Runtime.evaluate',expression=expression,awaitPromise=True,returnByValue=True,replMode=True)
                    assert 'exceptionDetails' not in r,r
                    return r.get('result',{}).get('value')
                async def wait(expression):
                    for _ in range(300):
                        if await js(expression):return
                        await asyncio.sleep(.1)
                    raise AssertionError((expression,errors,await js('document.body.innerText')))
                await call('Runtime.enable')
                download_dir=Path(profile)/'downloads'
                download_dir.mkdir()
                await call('Browser.setDownloadBehavior',behavior='allow',downloadPath=str(download_dir))
                await call('Emulation.setDeviceMetricsOverride',width=1440,height=1100,deviceScaleFactor=1,mobile=False)
                await call('Page.navigate',url=f'http://127.0.0.1:{app_port}')
                await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                assert await js("!document.querySelector('#project-panel').hidden && document.querySelector('#calibrate-panel').hidden && document.querySelector('#project-tab').getAttribute('aria-selected')==='true' && document.title==='Chronologer · Project'")
                await js("window.startupMarker=true")
                await call('Page.reload',ignoreCache=False)
                await wait("typeof window.startupMarker==='undefined' && !!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled")
                assert await js("!document.querySelector('#project-panel').hidden && document.querySelector('#calibrate-panel').hidden && document.title==='Chronologer · Project'")
                # Deliberately disable browser filesystem pickers.
                await js("""window.state=(await import('/js/project-state.js')).projectState;
                  window.confirmCalls=0;window.allowDiscard=true;
                  window.confirm=()=>{confirmCalls++;return allowDiscard};
                  window.showSaveFilePicker=window.showOpenFilePicker=async()=>{throw new DOMException('Browser file handles blocked','NotAllowedError')};
                  window.upload=text=>{let dt=new DataTransfer();dt.items.add(new File([text],'dates.csv',{type:'text/csv'}));let input=document.querySelector('#csv-file');input.files=dt.files;input.dispatchEvent(new Event('change'))};
                  upload('id,c14_mean,c14_err,curve\\nA1,1045,25,intcal20\\nB2,3240,25,intcal20\\nC3,4500,30,intcal20\\n');""")
                await wait("state.data.events.length===3 && !state.busy")
                assert await js("document.querySelectorAll('#determination-rows tr').length===3 && state.dirty")
                await js("document.querySelector('#calibrate-button').click()")
                await wait("document.querySelectorAll('.sample-plot').length===3")
                await js("document.querySelector('#project-tab').click(); let n=document.querySelector('#project-name');n.value='Benchmark dates';n.dispatchEvent(new Event('input'));document.querySelector('[data-project-action=save]').click()")
                await wait("!state.dirty && !state.busy && !!state.fileHandle")
                assert choices.count('save') == 1
                await js("window.saved=JSON.stringify(state.data); document.querySelector('[data-project-action=new]').click()")
                await wait("state.data.events.length===0 && !state.busy")
                assert await js("!document.querySelector('.sample-plot') && state.fileHandle===null && document.querySelectorAll('#determination-rows tr').length===1")
                await js("document.querySelector('[data-project-action=open]').click()")
                await wait("state.data.events.length===3 && !state.busy")
                assert await js("JSON.stringify(state.data)===saved && !state.dirty && state.fileHandle.name==='example.chrono'")
                # Edit through the actual calibration table, save to same file.
                await js("document.querySelector('#calibrate-tab').click();let input=document.querySelector('[data-field=age]');input.value='1046';input.dispatchEvent(new Event('input'));document.querySelector('#project-tab').click();document.querySelector('[data-project-action=save]').click()")
                await wait('!state.busy && !state.dirty')
                assert choices.count("save") == 1
                assert await js("state.data.events[0].parameters.c14_mean===1046")
                # External modifications are not overwritten; dirty edits survive.
                saved_bytes = selected.read_bytes()
                selected.write_bytes(b'external change')
                await js("state.setName('Unsaved edit');document.querySelector('[data-project-action=save]').click()")
                await wait("!state.busy && document.querySelector('#project-status').textContent.includes('changed outside')")
                assert await js('state.dirty')
                assert selected.read_bytes() == b'external change'
                await js("document.querySelector('[data-project-action=download]').click()")
                await wait("!state.busy && document.querySelector('#project-status').textContent.includes('copy sent')")
                assert await js('state.dirty')
                downloaded=download_dir/'Unsaved edit.chrono'
                for _ in range(100):
                    if downloaded.exists():break
                    await asyncio.sleep(.1)
                with zipfile.ZipFile(downloaded) as archive:
                    assert json.loads(archive.read('project.json'))['project_name']=='Unsaved edit'
                selected.write_bytes(saved_bytes)
                await js("allowDiscard=false;document.querySelector('[data-project-action=new]').click()")
                await wait('!state.busy')
                assert await js("state.data.metadata.project_name==='Unsaved edit' && confirmCalls>0")
                await js("allowDiscard=true;document.querySelector('[data-project-action=open]').click()")
                await wait("!state.busy && !state.dirty")
                assert await js("state.data.events[0].parameters.c14_mean===1046 && state.data.metadata.project_name==='Benchmark dates'")
                # Invalid CSV is transactional: no dataset/provenance replacement.
                await js("window.beforeBad=JSON.stringify(state.data);upload('id,age,error\\nA,5,1')")
                await wait("!state.busy && document.querySelector('#project-status').textContent.includes('requires columns')")
                assert await js('JSON.stringify(state.data)===beforeBad && !state.dirty')
                # Save As chooses a new target.
                selected = Path(profile) / 'copy.chrono'
                await js("document.querySelector('[data-project-action=save-as]').click()")
                await wait("!state.busy && state.fileHandle.name==='copy.chrono'")
                assert choices.count('save') == 2
                # A new browser page/session can open the saved file with no
                # previous in-memory state (the chooser provides its handle).
                await call('Page.reload',ignoreCache=True)
                await wait("!!document.querySelector('#calibrate-button') && !document.querySelector('#calibrate-button').disabled && document.querySelector('#project-details')?.textContent.startsWith('0 events')")
                await js("window.state=(await import('/js/project-state.js')).projectState;window.showSaveFilePicker=window.showOpenFilePicker=async()=>{throw new DOMException('Blocked','NotAllowedError')};document.querySelector('#project-tab').click();document.querySelector('[data-project-action=open]').click()")
                await wait("state.data.events.length===3 && !state.busy")
                assert await js("state.data.events[0].parameters.c14_mean===1046 && state.data.source_csv.name==='dates.csv' && !state.dirty")
                # Mixed-curve import is editable and preserves each event choice,
                # even if a recognized curve is not installed on this machine.
                await js("""window.confirm=()=>true;
                  const dt=new DataTransfer();dt.items.add(new File(['id,c14_mean,c14_err,curve\\nA,3240,25,intcal20\\nB,3240,25,shcal20\\n'],'mixed.csv',{type:'text/csv'}));
                  const input=document.querySelector('#csv-file');input.files=dt.files;input.dispatchEvent(new Event('change'));""")
                await wait('!state.busy && state.data.events.length===2')
                assert await js("JSON.stringify([...document.querySelectorAll('#determination-rows [data-field=curve]')].map(s=>s.value))===JSON.stringify(['intcal20','shcal20'])")
                await js("window.originalEvents=JSON.stringify(state.data.events);document.querySelector('#curve-select').dispatchEvent(new Event('change'))")
                assert await js('JSON.stringify(state.data.events)===originalEvents')
                await js("document.querySelector('#calibrate-tab').click();document.querySelector('#calibrate-button').click()")
                # When unavailable, the curve is retained and a row-specific error is shown.
                if await js("document.querySelectorAll('#determination-rows [data-field=curve]')[1].selectedOptions[0].disabled"):
                    await wait("document.querySelector('#form-errors').textContent.includes('shcal20')")
                    assert await js("state.data.events[1].parameters.curve==='shcal20'")
                await js("{const ageInput=document.querySelector('[data-field=age]');ageInput.value='3241';ageInput.dispatchEvent(new Event('input'));document.querySelector('#project-tab').click();document.querySelector('[data-project-action=save]').click()}")
                await wait('!state.busy && !state.dirty')
                await js("document.querySelector('[data-project-action=new]').click()")
                await wait('!state.busy && state.data.events.length===0')
                await js("document.querySelector('[data-project-action=open]').click()")
                await wait('!state.busy && state.data.events.length===2')
                assert await js("state.data.events[0].parameters.c14_mean===3241 && state.data.events[1].parameters.curve==='shcal20' && document.querySelectorAll('#determination-rows [data-field=curve]')[1].value==='shcal20'")
                await js("document.querySelector('#calibrate-tab').click();let select=document.querySelectorAll('#determination-rows [data-field=curve]')[1];select.value='intcal20';select.dispatchEvent(new Event('change'))")
                assert await js("state.dirty && state.data.events.every(e=>e.parameters.curve==='intcal20')")
                await js("document.querySelector('#calibrate-button').click()")
                await wait("document.querySelectorAll('.sample-plot').length===2 && !document.querySelector('#calibrate-button').disabled")
                assert await js("[...document.querySelectorAll('.sample-plot-body > p.help')].every(p=>p.textContent==='Calibration curve: intcal20')")
                # Phase acceptance benchmark: three semantic objects, rename,
                # change profiles, drag third between first/second, save/reopen.
                await js("document.querySelector('#phase-tab').click();for(let i=0;i<3;i++)document.querySelector('#add-phase').click();[...document.querySelectorAll('.phase-name')].forEach((n,i)=>{n.value=['Early','Late','Middle'][i];n.dispatchEvent(new Event('input'))});window.uniformShape=document.querySelector('.phase-density path').getAttribute('d');{const family=document.querySelectorAll('.phase-distribution')[2];family.value='normal';family.dispatchEvent(new Event('change'))}window.phaseIds=state.data.phases.map(p=>p.id)")
                assert await js("state.data.phases.length===3 && state.data.phases[0].distribution==='normal' && document.querySelectorAll('.phase-density path')[2].getAttribute('d')!==uniformShape")
                await js("document.querySelector('#phase-canvas').scrollTop=0;document.querySelector('#phase-canvas').scrollIntoView({block:'center'})")
                points=await js("(()=>{let cards=[...document.querySelectorAll('.phase-card')];let r=cards[2].querySelector('button').getBoundingClientRect();let target=cards[1].getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,to:target.y+target.height/2-20,second:cards[1].offsetTop}})()")
                await call('Input.dispatchMouseEvent',type='mousePressed',x=points['x'],y=points['y'],button='left',clickCount=1)
                await call('Input.dispatchMouseEvent',type='mouseMoved',x=points['x'],y=points['to'],buttons=1)
                assert await js("JSON.stringify([...document.querySelectorAll('.phase-card')].map(c=>c.dataset.phaseId))===JSON.stringify([phaseIds[2],phaseIds[0],phaseIds[1]])")
                await call('Input.dispatchMouseEvent',type='mouseReleased',x=points['x'],y=points['to'],button='left',clickCount=1)
                await wait("state.data.phases[1].id===phaseIds[0]")
                assert await js("JSON.stringify(state.data.phases.map(p=>p.order))==='[0,1,2]' && state.data.phases.map(p=>p.label).join(',')==='Late,Middle,Early'")
                assert await js("document.querySelectorAll('.phase-card')[2].offsetTop")>points['second']
                await js("document.querySelector('#project-tab').click();document.querySelector('[data-project-action=save]').click()")
                await wait('!state.busy && !state.dirty')
                await js("window.savedPhases=JSON.stringify(state.data.phases);document.querySelector('[data-project-action=new]').click()")
                await wait("!state.busy && !state.data.phases")
                assert await js("document.querySelectorAll('.phase-card').length===0")
                await js("document.querySelector('[data-project-action=open]').click()")
                await wait("!state.busy && state.data.phases?.length===3")
                assert await js("JSON.stringify(state.data.phases)===savedPhases && document.querySelectorAll('.phase-card').length===3")
                assert await js("[...document.querySelectorAll('.phase-card')].map(c=>c.dataset.phaseId).join()===state.data.phases.toReversed().map(p=>p.id).join()")
                await js("document.querySelector('#depth-tab').click();document.querySelector('#depth-tab').focus()")
                assert await js("!document.querySelector('#depth-panel').hidden && document.querySelector('#phase-panel').hidden && document.title==='Chronologer · Depth'")
                await call('Input.dispatchKeyEvent',type='keyDown',key='ArrowLeft',code='ArrowLeft',windowsVirtualKeyCode=37)
                assert await js("!document.querySelector('#phase-panel').hidden")
                await js("document.querySelector('.phase-grip').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))")
                assert await js("document.querySelectorAll('.phase-card')[1].dataset.phaseId===phaseIds[2] && state.data.phases[1].id===phaseIds[2]")
                await js("document.querySelectorAll('.phase-grip')[1].dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))")
                assert await js("JSON.stringify(state.data.phases)===savedPhases")
                await js("document.querySelector('#phase-tab').click();document.documentElement.dataset.theme='dark'")
                shot=await call('Page.captureScreenshot',format='png',captureBeyondViewport=True)
                Path('docs/screenshots/phase-dark.png').write_bytes(base64.b64decode(shot['data']))
                await js("document.querySelector('#summarize-tab').click();document.querySelector('#add-summary').click();{let card=document.querySelector('.summary-card');let name=card.querySelector('input');name.value='Occupation';name.dispatchEvent(new Event('input'));let model=card.querySelector('select');model.value='mixture';model.dispatchEvent(new Event('change'));card=document.querySelector('.summary-card');card.querySelector('details').open=true;let search=card.querySelector('[type=search]');search.value=state.data.events[0].id;search.dispatchEvent(new Event('input'));let check=card.querySelector('[type=checkbox]');check.click();[...card.querySelectorAll('button')].find(b=>b.textContent==='Add selected').click()}")
                assert await js("state.data.summaries[0].label==='Occupation' && state.data.summaries[0].model==='mixture' && state.data.summaries[0].events.length===1 && state.dirty")
                await js("window.savedSummaries=JSON.stringify(state.data.summaries);document.querySelector('#project-tab').click();document.querySelector('[data-project-action=save]').click()")
                await wait('!state.busy && !state.dirty')
                await js("document.querySelector('[data-project-action=new]').click()")
                await wait('!state.busy && !state.data.summaries')
                assert await js("document.querySelectorAll('.summary-card').length===0")
                await js("document.querySelector('[data-project-action=open]').click()")
                await wait('!state.busy && state.data.summaries?.length===1')
                assert await js('JSON.stringify(state.data.summaries)===savedSummaries')
                await js("document.querySelector('#summarize-tab').click()")
                shot=await call('Page.captureScreenshot',format='png',captureBeyondViewport=True)
                Path('docs/screenshots/summarize-dark.png').write_bytes(base64.b64decode(shot['data']))
                await call('Emulation.setDeviceMetricsOverride',width=390,height=844,deviceScaleFactor=1,mobile=False)
                await asyncio.sleep(.2)
                assert await js('document.documentElement.scrollWidth<=390')
                await js("document.querySelector('#project-tab').click()")
                await asyncio.sleep(.2)
                assert await js('document.documentElement.scrollWidth<=390'),await js('document.documentElement.scrollWidth')
                await js("document.querySelector('#phase-tab').click()")
                await asyncio.sleep(.2)
                assert await js('document.documentElement.scrollWidth<=390'),await js('document.documentElement.scrollWidth')
                await js("document.querySelector('#calibrate-tab').click()")
                await asyncio.sleep(.2)
                assert await js('document.documentElement.scrollWidth<=390'),await js('document.documentElement.scrollWidth')
                await js("document.querySelector('#project-tab').click()")
                await js("document.documentElement.dataset.theme='dark'")
                shot=await call('Page.captureScreenshot',format='png',captureBeyondViewport=True)
                Path('docs/screenshots/project-dark-mobile.png').write_bytes(base64.b64decode(shot['data']))
                # Master event table: heterogeneous data, duplicate IDs, shared
                # edits, metadata, and calibration-only selection.
                await call('Emulation.setDeviceMetricsOverride',width=1440,height=1100,deviceScaleFactor=1,mobile=False)
                await js("""state.setEvents([
                  {id:'Duplicate',distribution:'calrcarbon',parameters:{c14_mean:3240,c14_err:25,curve:'intcal20'}},
                  {id:'Normal date',distribution:'normal',parameters:{mean:100,sd:10}},
                  {id:'Duplicate',distribution:'calrcarbon',parameters:{c14_mean:3450,c14_err:25,curve:'intcal20'}},
                  {id:'Future date',distribution:'future',parameters:{a:1,b:2,c:3,extra:{keep:true}}}
                ]);
                window.editMaster=(index,field,value)=>{let control=document.querySelectorAll('#project-events tr')[index].querySelector(`[data-field=${field}]`);control.focus();control.value=value;control.dispatchEvent(new Event(control.tagName==='SELECT'?'change':'input'));return document.activeElement===control};
                document.querySelector('#project-tab').click();""")
                assert await js("document.querySelectorAll('#project-events tr').length===4 && document.querySelectorAll('#determination-rows tr').length===2")
                assert await js("editMaster(2,'p1','3460')")
                assert await js("document.querySelectorAll('#determination-rows [data-field=age]')[1].value==='3460' && state.data.events[0].parameters.c14_mean===3240")
                await js("editMaster(0,'label','Context A');editMaster(1,'datum','BCAD');editMaster(3,'p1','11')")
                assert await js("state.data.events[1].parameters.mean===100 && state.data.events[3].parameters.extra.keep && state.data.events[3].parameters.a===11")
                await js("document.querySelector('#calibrate-tab').click();{let input=document.querySelector('#determination-rows [data-field=age]');input.focus();input.value='3250';input.dispatchEvent(new Event('input'));window.calibrationFocus=document.activeElement===input}")
                assert await js("calibrationFocus && document.querySelector('#project-events [data-field=p1]').value==='3250' && state.data.events[0].label==='Context A' && state.data.events.length===4")
                await js("editMaster(0,'curve','shcal20')")
                assert await js("document.querySelector('#determination-rows [data-field=curve]').value==='shcal20'")
                await js("{let curve=document.querySelector('#determination-rows [data-field=curve]');curve.value='intcal20';curve.dispatchEvent(new Event('change'))}")
                assert await js("document.querySelector('#project-events [data-field=curve]').value==='intcal20'")
                await js("editMaster(2,'p2','');document.querySelectorAll('#determination-rows [data-field=include]')[1].click();window.calibrationRequests=0;const tableFetch=window.fetch;window.fetch=(...args)=>{if(args[0]==='/api/calibrate')calibrationRequests++;return tableFetch(...args)};document.querySelector('#calibrate-button').click()")
                await wait("!document.querySelector('#calibrate-button').disabled && document.querySelectorAll('.sample-plot').length===1")
                assert await js("calibrationRequests===1 && state.data.events[2].include_in_calibration===false")
                await js("document.querySelector('#determination-rows [data-field=include]').click();document.querySelector('#calibrate-button').click()")
                assert await js("calibrationRequests===1 && document.querySelector('#form-errors').textContent.includes('Select at least one')")
                await js("editMaster(2,'p2','25');document.querySelector('#project-tab').click();document.querySelector('[data-project-action=save]').click()")
                await wait('!state.busy && !state.dirty')
                await js("window.savedMaster=JSON.stringify(state.data.events);document.querySelector('[data-project-action=new]').click()")
                await wait('!state.busy && state.data.events.length===0')
                await js("document.querySelector('[data-project-action=open]').click()")
                await wait('!state.busy && state.data.events.length===4')
                assert await js("JSON.stringify(state.data.events)===savedMaster && [...document.querySelectorAll('#determination-rows [data-field=include]')].every(c=>!c.checked) && document.querySelectorAll('#project-events [data-field=datum]')[1].value==='BCAD'")
                shot=await call('Page.captureScreenshot',format='png',captureBeyondViewport=True)
                Path('docs/screenshots/project-event-editor.png').write_bytes(base64.b64decode(shot['data']))
                await js("document.querySelector('#calibrate-tab').click();document.querySelector('#determination-rows .remove-row').click()")
                assert await js("state.data.events.length===3 && state.data.events[0].distribution==='normal' && state.data.events[1].parameters.c14_mean===3460 && state.data.events[2].parameters.extra.keep && document.querySelectorAll('#determination-rows tr').length===1")
                await js("document.querySelector('#project-tab').click();document.querySelector('#add-event').click();editMaster(3,'distribution','uniform');editMaster(3,'p1','100');editMaster(3,'p2','200')")
                assert await js("state.data.events[3].distribution==='uniform' && state.data.events[3].datum==='BP1950' && state.data.events[3].parameters.lower===100 && document.querySelectorAll('#determination-rows tr').length===1")
                # Cancellation preserves the current draft; copy import also works.
                selected = None
                await js("window.beforeCancel=JSON.stringify(state.data);document.querySelector('[data-project-action=open]').click()")
                await wait("!state.busy && document.querySelector('#project-status').textContent.includes('Open cancelled')")
                assert await js('JSON.stringify(state.data)===beforeCancel && state.dirty')
                document=await call('DOM.getDocument')
                file_input=await call('DOM.querySelector',nodeId=document['root']['nodeId'],selector='#project-file')
                await call('DOM.setFileInputFiles',nodeId=file_input['nodeId'],files=[str(downloaded)])
                await wait("!state.busy && state.data.metadata.project_name==='Unsaved edit' && !state.dirty")
                assert await js("state.fileHandle===null && state.data.events.length===3 && document.querySelector('#project-location').textContent.includes('Opened copy:')")
                await js("window.beforeBadCopy=JSON.stringify(state.data);{let dt=new DataTransfer();dt.items.add(new File(['not a project'],'invalid.chrono'));let input=document.querySelector('#project-file');input.files=dt.files;input.dispatchEvent(new Event('change'))}")
                await wait("!state.busy && document.querySelector('#project-status').textContent.includes('Invalid .chrono')")
                assert await js('JSON.stringify(state.data)===beforeBadCopy && !state.dirty')
                # Previously fitted mixture restores from archive without sampling.
                fixture = json.loads(Path('docs/mixture-benchmark-result.json').read_text())
                await js('window.mixtureFixture=' + json.dumps(fixture))
                await js('window.mixtureCSV=' + json.dumps(Path('docs/examples/density-benchmark.csv').read_text()))
                await js("""{
                  const events=(await (await fetch('/api/projects/import-csv?filename=example.csv',{method:'POST',body:mixtureCSV})).json()).events;
                  const saved_run={id:'saved-mixture',created_at:new Date().toISOString(),model:'mixture',events,parameters:{K_max:5},result:mixtureFixture};
                  state.setSummaries([{id:'restored-mixture',label:'Restored mixture',model:'mixture',events,parameters:{K_max:5},saved_run}]);
                  const archive=await (await fetch('/api/projects/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.data)})).blob();
                  const reopened=await (await fetch('/api/projects/decode',{method:'POST',body:archive})).json();
                  state.replace(reopened);document.querySelector('#summarize-tab').click();
                }""")
                await wait("document.querySelectorAll('[data-layer=summary-density] [data-event-index]').length===20")
                assert await js("!document.querySelector('.summary-parameter-plot') && !state.dirty && document.querySelector('.mixture-diagnostics')!==null")
                await js("{const input=document.querySelector('[data-setting=K_max]');input.value='4';input.dispatchEvent(new Event('input'))}")
                assert await js("!document.querySelector('[data-layer=summary-density]') && state.data.summaries[0].saved_run.parameters.K_max===5")
                await js("[...document.querySelectorAll('button')].find(b=>b.textContent==='Load saved run').click()")
                await wait("!!document.querySelector('[data-layer=summary-density]')")
                assert await js("state.data.summaries[0].parameters.K_max===5")
                await js("[...document.querySelectorAll('button')].find(b=>b.textContent==='Remove saved result').click()")
                assert await js("!state.data.summaries[0].saved_run && !document.querySelector('[data-layer=summary-density]')")
                assert not errors,errors
                print('PASS: Master table two-way edits/focus, mixed types, duplicate IDs, labels/datums, inclusion filtering, save/reopen; Summary/Phase benchmarks; failed-save protection, per-event curves, calibration, mobile/dark. Native chooser boundary substituted; real local API and disk IO, with browser filesystem APIs blocked.')
        finally:
            browser.terminate();browser.wait(timeout=10)
            server.should_exit = True
            await asyncio.to_thread(thread.join, 10)
            files.choose_file = original_chooser
            sock.close()
            await asyncio.sleep(.5)

if __name__ == '__main__':
    asyncio.run(main())
