"""The single-file, self-contained local UI (no CDN, no build step)."""
from __future__ import annotations

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reprise</title>
<style>
  :root {
    --bg:#0f1216; --panel:#161b22; --panel2:#1c232d; --line:#2a323d;
    --fg:#e6edf3; --dim:#8b98a5; --accent:#4c8dff;
    --llm:#4c8dff; --tool:#3fb950; --mcp:#bc8cff; --event:#8b98a5; --err:#f85149;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
  #app { display:grid; grid-template-columns:250px 1fr; height:100vh; }
  aside { border-right:1px solid var(--line); overflow:auto; background:var(--panel); }
  aside h1 { font-size:15px; margin:0; padding:14px 16px; letter-spacing:.5px;
             border-bottom:1px solid var(--line); }
  aside h1 span { color:var(--accent); }
  .run { padding:10px 16px; cursor:pointer; border-bottom:1px solid var(--line); }
  .run:hover { background:var(--panel2); }
  .run.active { background:var(--panel2); border-left:3px solid var(--accent); padding-left:13px; }
  .run .name { font-weight:600; }
  .run .meta { color:var(--dim); font-size:11px; }
  main { display:flex; flex-direction:column; overflow:hidden; }
  header { padding:12px 18px; border-bottom:1px solid var(--line); }
  header .title { font-size:15px; font-weight:600; }
  header .sub { color:var(--dim); font-size:11px; margin-top:2px; }
  .badge { display:inline-block; padding:1px 7px; border-radius:10px; font-size:10px;
           border:1px solid var(--line); color:var(--dim); margin-left:6px; }
  .scrub { padding:14px 18px; border-bottom:1px solid var(--line); }
  .scrub input[type=range] { width:100%; accent-color:var(--accent); }
  .timeline { display:flex; gap:4px; flex-wrap:wrap; margin-top:10px; }
  .chip { min-width:30px; height:26px; padding:0 8px; border-radius:5px; cursor:pointer;
          display:flex; align-items:center; justify-content:center; font-size:11px;
          background:var(--panel2); border:1px solid var(--line); color:var(--fg); }
  .chip.sel { outline:2px solid var(--accent); }
  .chip.err { border-color:var(--err); }
  .dot { width:7px; height:7px; border-radius:50%; margin-right:5px; }
  .k-llm_call{color:var(--llm)} .k-tool_call{color:var(--tool)}
  .k-mcp_tool_call{color:var(--mcp)} .k-event{color:var(--event)}
  .b-llm_call{background:var(--llm)} .b-tool_call{background:var(--tool)}
  .b-mcp_tool_call{background:var(--mcp)} .b-event{background:var(--event)}
  .inspector { flex:1; overflow:auto; padding:16px 18px; }
  .stephead { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
  .stephead .nm { font-size:14px; font-weight:600; }
  .facts { color:var(--dim); font-size:11px; margin-bottom:14px; }
  .facts b { color:var(--fg); font-weight:600; }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .col h3 { margin:0 0 6px; font-size:11px; text-transform:uppercase; letter-spacing:.6px;
            color:var(--dim); }
  pre { margin:0; background:var(--panel); border:1px solid var(--line); border-radius:6px;
        padding:12px; overflow:auto; max-height:60vh; white-space:pre-wrap; word-break:break-word; }
  .empty { color:var(--dim); padding:40px 18px; }
  @media(max-width:820px){ #app{grid-template-columns:1fr} aside{display:none} .cols{grid-template-columns:1fr} }
</style>
</head>
<body>
<div id="app">
  <aside><h1>Re<span>prise</span></h1><div id="runs"></div></aside>
  <main>
    <header><div class="title" id="rtitle">—</div><div class="sub" id="rsub"></div></header>
    <div class="scrub" id="scrub" style="display:none">
      <input type="range" id="slider" min="0" value="0" step="1">
      <div class="timeline" id="timeline"></div>
    </div>
    <div class="inspector" id="inspector"><div class="empty">Loading…</div></div>
  </main>
</div>
<script>
const $ = s => document.querySelector(s);
let RUN=null, STEPS=[], SEL=0;

async function j(u){ const r=await fetch(u); if(!r.ok) throw new Error(r.status); return r.json(); }

async function loadRuns(){
  const runs = await j('/api/runs');
  const box = $('#runs'); box.innerHTML='';
  if(!runs.length){ box.innerHTML='<div class="empty">No runs</div>'; $('#inspector').innerHTML='<div class="empty">Empty recording</div>'; return; }
  runs.forEach(r=>{
    const d=document.createElement('div'); d.className='run'; d.dataset.id=r.run_id;
    d.innerHTML=`<div class="name">${esc(r.name)}</div><div class="meta">${r.steps} steps · ${r.status}${r.parent_run_id?' · fork':''}</div>`;
    d.onclick=()=>selectRun(r.run_id);
    box.appendChild(d);
  });
  selectRun(runs[runs.length-1].run_id);
}

async function selectRun(id){
  document.querySelectorAll('.run').forEach(e=>e.classList.toggle('active', e.dataset.id===id));
  const data = await j('/api/runs/'+id);
  RUN=data.run; STEPS=RUN.steps; SEL=0;
  const c=data.cost;
  $('#rtitle').innerHTML = esc(RUN.name) + `<span class="badge">${RUN.status}</span>`;
  let sub = `${STEPS.length} steps · ${c.total_tokens} tokens · $${c.usd.toFixed(6)}`;
  if(RUN.parent_run_id) sub += ` · forked at step ${RUN.forked_from_index}`;
  $('#rsub').textContent = sub;
  const sl=$('#slider'); sl.max=Math.max(0,STEPS.length-1); sl.value=0;
  sl.oninput=()=>{ SEL=+sl.value; renderTimeline(); showStep(SEL); };
  $('#scrub').style.display = STEPS.length? 'block':'none';
  renderTimeline();
  STEPS.length ? showStep(0) : ($('#inspector').innerHTML='<div class="empty">No steps</div>');
}

function renderTimeline(){
  const t=$('#timeline'); t.innerHTML='';
  STEPS.forEach((s,i)=>{
    const c=document.createElement('div');
    c.className='chip b-'+s.kind+(i===SEL?' sel':'')+(s.error?' err':'');
    c.style.opacity = i===SEL?1:0.55; c.textContent=i;
    c.title=`${s.kind} · ${s.name}`;
    c.onclick=()=>{ SEL=i; $('#slider').value=i; renderTimeline(); showStep(i); };
    t.appendChild(c);
  });
}

async function showStep(i){
  const d = await j(`/api/runs/${RUN.run_id}/steps/${i}`);
  const s=d.step;
  const facts=[];
  if(s.duration_ms!=null) facts.push(`<b>${s.duration_ms.toFixed(0)}</b> ms`);
  if(s.tokens) facts.push(`<b>${(s.tokens.prompt||0)}→${(s.tokens.completion||0)}</b> tok`);
  if(s.cost) facts.push(`<b>$${s.cost.toFixed(6)}</b>`);
  if(s.meta && s.meta.replayed) facts.push(`<b style="color:var(--mcp)">replayed prefix</b>`);
  $('#inspector').innerHTML =
    `<div class="stephead"><span class="dot b-${s.kind}"></span>`+
    `<span class="nm k-${s.kind}">#${s.index} ${esc(s.name)}</span>`+
    `<span class="badge">${s.kind}</span></div>`+
    `<div class="facts">${facts.join(' &nbsp;·&nbsp; ')||'—'}</div>`+
    (s.error?`<pre style="border-color:var(--err)">${esc(s.error.type+': '+s.error.message)}</pre>`:'')+
    `<div class="cols"><div class="col"><h3>request</h3><pre>${esc(pretty(d.request))}</pre></div>`+
    `<div class="col"><h3>response</h3><pre>${esc(pretty(d.response))}</pre></div></div>`;
}

function pretty(o){ return o==null?'(none)':JSON.stringify(o,null,2); }
function esc(s){ return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
document.addEventListener('keydown',e=>{
  if(!STEPS.length) return;
  if(e.key==='ArrowRight'&&SEL<STEPS.length-1){SEL++;}
  else if(e.key==='ArrowLeft'&&SEL>0){SEL--;} else return;
  $('#slider').value=SEL; renderTimeline(); showStep(SEL);
});
loadRuns().catch(e=>$('#inspector').innerHTML='<div class="empty">Error: '+e+'</div>');
</script>
</body>
</html>
"""
