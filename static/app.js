(() => {
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  let serverEpoch = null, anchor = 0, shift = null, failures = 0;
  const format = seconds => { seconds=Math.max(0,Math.floor(seconds));return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(x=>String(x).padStart(2,'0')).join(':'); };
  const notify = (text,error=false) => { let el=document.getElementById('action-feedback');if(!el){el=document.createElement('div');el.id='action-feedback';el.setAttribute('role','status');document.querySelector('main')?.prepend(el);}el.textContent=text;el.className='message '+(error?'error':'success');el.hidden=false; };
  const updateTimers = () => {
    if (!serverEpoch || !shift) return;
    const now=serverEpoch+(performance.now()-anchor);
    document.querySelectorAll('[data-timer]').forEach(el=>{
      let seconds=0;
      if(el.dataset.timer==='shift') seconds=((shift.end_utc?Date.parse(shift.end_utc):now)-Date.parse(shift.start_utc))/1000;
      if(el.dataset.timer==='break'){const b=shift.breaks.find(b=>!b.end);seconds=b?(now-Date.parse(b.start))/1000:0;}
      el.textContent=format(seconds);
    });
  };
  const sync = async () => {
    const el=document.getElementById('sync-status');if(!el)return;
    try{
      const res=await fetch('/api/sync/',{headers:{Accept:'application/json'},cache:'no-store'});
      if(!res.ok)throw Error('Server unavailable');
      const data=await res.json();serverEpoch=Date.parse(data.server_time);anchor=performance.now();failures=0;
      const old=shift;shift=data.shift;
      el.classList.remove('failure');el.textContent='● Synced '+new Intl.DateTimeFormat('en-US',{timeZone:'America/Denver',hour:'numeric',minute:'2-digit',second:'2-digit'}).format(new Date(serverEpoch));
      document.querySelectorAll('[data-count]').forEach(node=>{const v=data[node.dataset.count];if(v!==undefined)node.textContent=v;});
      const label=document.getElementById('shift-status');if(label)label.textContent=shift?shift.status:'Off Shift';
      document.querySelectorAll('[data-action]').forEach(btn=>{const a=btn.dataset.action;btn.hidden=a==='start'?!!shift:a==='break_start'?(!shift||shift.status!=='Working'):a==='break_end'?(!shift||shift.status!=='On Break'):!shift;});
      if(data.coverage){const target=document.getElementById('live-coverage');if(target){target.replaceChildren();data.coverage.forEach(s=>{const row=document.createElement('div');row.className='item item-line';const name=document.createElement('strong');name.textContent=s.employee;const status=document.createElement('span');status.className='badge '+(s.status==='Working'?'good':'warn');status.textContent=s.status;row.append(name,status);target.append(row);});if(!data.coverage.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No active shifts';target.append(empty);}}}
      updateTimers();
    }catch(e){failures++;el.classList.add('failure');el.textContent='Connection failed · data may be stale';document.querySelectorAll('[data-timer]').forEach(n=>n.title='Live estimate; connection lost. Last saved timestamps retained.');}
  };
  document.querySelectorAll('[data-action]').forEach(btn=>btn.addEventListener('click',async()=>{
    const key=btn.dataset.requestId||crypto.randomUUID();btn.dataset.requestId=key;
    const buttons=[...document.querySelectorAll('[data-action]')];buttons.forEach(b=>b.disabled=true);notify('Processing… waiting for backend confirmation.');
    try{
      const res=await fetch('/api/shift-action/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({action:btn.dataset.action,request_id:key})});
      const data=await res.json();if(!res.ok||!data.saved)throw Error(data.error||'Save failed');
      delete btn.dataset.requestId;notify('Saved successfully.');await sync();window.location.reload();
    }catch(e){notify(e.message+' Your request ID is preserved for a safe retry.',true);}finally{buttons.forEach(b=>b.disabled=false);}
  }));
  const bindForms = (root=document) => root.querySelectorAll('form[data-processing]').forEach(form=>form.addEventListener('submit',async event=>{
    event.preventDefault();const button=form.querySelector('button[type=submit]');const label=button?.textContent;
    if(button){button.disabled=true;button.textContent='Saving…';}
    try{
      const res=await fetch(form.action||window.location.href,{method:'POST',body:new FormData(form),headers:{'X-CSRFToken':csrf(),'X-Requested-With':'RockyForm'}});
      if(!res.ok)throw Error(res.status===409?'The request conflicts with a saved submission. Reload before making a different change.':'The backend could not save this request. Your entered information is preserved.');
      if(res.headers.get('Content-Type')?.includes('application/json')){const result=await res.json();if(result.navigate){window.location.assign(result.navigate);return;}throw Error('Unexpected backend response.');}
      if(res.redirected){window.location.assign(res.url);return;}
      const html=await res.text();const doc=new DOMParser().parseFromString(html,'text/html');const main=doc.querySelector('main');
      if(main){document.querySelector('main').replaceWith(main);bindForms(main);bindCopy(main);}
      else throw Error('Unexpected server response. Your information is preserved.');
    }catch(e){notify(e instanceof TypeError?'Connection failed. The save is unconfirmed. Your entered information is preserved; retry safely.':e.message,true);}finally{if(button){button.disabled=false;button.textContent=label;}}
  }));
  bindForms();
  const bindCopy = (root=document) => root.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',async()=>{const el=document.getElementById(btn.dataset.copy);try{await navigator.clipboard.writeText(el.value||el.textContent);btn.textContent='Copied';}catch(e){el.focus();el.select?.();btn.textContent='Select and copy the report';}}));
  bindCopy();
  sync();setInterval(sync,15000);setInterval(updateTimers,1000);
})();
