export function createBlocksEditor(container, questionId, initialBlocks, convention) {
  container.innerHTML = "";
  let blocks = Array.isArray(initialBlocks) ? JSON.parse(JSON.stringify(initialBlocks)) : [];
  let idCounter = blocks.length ? Math.max(...blocks.map(b=>b.id||0)) : 0;
  const header = document.createElement("div");
  header.className = "blocks-header";
  header.innerHTML = `<span class="blocks-title">Solution Blocks</span><select class="blocks-convention"><option value="metric" ${convention==="metric"?"selected":""}>Metric</option><option value="english" ${convention==="english"?"selected":""}>English</option><option value="custom" ${convention==="custom"?"selected":""}>Custom</option></select><button class="btn btn-sm">+ Constant</button><button class="btn btn-sm">+ Formula</button><button class="btn btn-sm">+ Answer</button><button class="btn btn-sm btn-primary run-btn">▶ Run</button><button class="btn btn-sm clear-btn">Clear</button>`;
  container.appendChild(header);
  const list = document.createElement("div");
  list.className = "blocks-list";
  container.appendChild(list);
  const results = document.createElement("div");
  results.className = "blocks-results";
  container.appendChild(results);
  const conventionSel = header.querySelector(".blocks-convention");
  const [btnConst, btnFormula, btnAnswer, btnRun, btnClear] = header.querySelectorAll("button");
  function render() {
    list.innerHTML="";
    blocks.forEach((b, idx)=>{
      const div=document.createElement("div");
      div.className="block-card";
      if(b.type==="constants"){
        div.innerHTML=`<div class="block-head">Constants <button data-remove="${idx}">✕</button></div><div class="const-rows">${(b.constants||[]).map((c,ci)=>`<div class="const-row"><input placeholder="name" value="${c.name||""}" data-ci="${ci}" data-field="name"><span>=</span><input placeholder="value" value="${c.value||""}" data-ci="${ci}" data-field="value"><input placeholder="unit" value="${c.unit||""}" data-ci="${ci}" data-field="unit"><button data-rmc="${ci}">✕</button></div>`).join("")}</div><button data-addc="+">+ Add constant</button>`;
      } else if(b.type==="formula"){
        div.innerHTML=`<div class="block-head">Formula <button data-remove="${idx}">✕</button></div><textarea placeholder="e.g. P*V = n*R*T" data-field="latex">${b.latex||""}</textarea>${b.result?`<div class="block-result">${b.result}</div>`:""}`;
      } else if(b.type==="answer"){
        div.innerHTML=`<div class="block-head">Answer <button data-remove="${idx}">✕</button></div><div class="answer-row"><input placeholder="variable" value="${b.variable||""}" data-field="variable"><input placeholder="unit" value="${b.unit||""}" data-field="unit">${b.result?`<span class="block-result">${b.result}</span>`:""}</div>`;
      } else if(b.answer!==undefined){
        div.innerHTML=`<div class="block-head">Legacy Answer <button data-remove="${idx}">✕</button></div><div>Answer index: ${b.answer}</div>`;
      }
      list.appendChild(div);
    });
  }
  list.addEventListener("click", e=>{
    const rm=e.target.getAttribute("data-remove");
    if(rm!==null){ blocks.splice(Number(rm),1); render(); scheduleSave(); return; }
    const rmc=e.target.getAttribute("data-rmc");
    if(rmc!==null){ const card=e.target.closest(".block-card"); const idx=Array.from(list.children).indexOf(card); blocks[idx].constants.splice(Number(rmc),1); render(); scheduleSave(); }
    if(e.target.getAttribute("data-addc")==="+"){ const card=e.target.closest(".block-card"); const idx=Array.from(list.children).indexOf(card); blocks[idx].constants.push({name:"",value:"",unit:""}); render(); }
  });
  list.addEventListener("input", e=>{
    const card=e.target.closest(".block-card"); if(!card) return; const idx=Array.from(list.children).indexOf(card); const b=blocks[idx];
    if(b.type==="constants" && e.target.hasAttribute("data-field")){ const ci=Number(e.target.getAttribute("data-ci")); const field=e.target.getAttribute("data-field"); b.constants[ci][field]=e.target.value; scheduleSave(); }
    else if(b.type==="formula" && e.target.getAttribute("data-field")==="latex"){ b.latex=e.target.value; scheduleSave(); }
    else if(b.type==="answer"){ if(e.target.getAttribute("data-field")==="variable") b.variable=e.target.value; if(e.target.getAttribute("data-field")==="unit") b.unit=e.target.value; scheduleSave(); }
  });
  btnConst.onclick=()=>{ blocks.push({type:"constants", id:++idCounter, constants:[{name:"",value:"",unit:""}]}); render(); scheduleSave(); };
  btnFormula.onclick=()=>{ blocks.push({type:"formula", id:++idCounter, latex:"", result:null}); render(); scheduleSave(); };
  btnAnswer.onclick=()=>{ blocks.push({type:"answer", id:++idCounter, variable:"", unit:"", result:null}); render(); scheduleSave(); };
  btnClear.onclick=()=>{ blocks=[]; render(); scheduleSave(); };
  btnRun.onclick=()=>{ const out=runSolver(blocks); results.textContent=JSON.stringify(out,null,2); render(); };
  conventionSel.onchange=(e)=>{ scheduleSave(e.target.value); };
  let saveTimeout=null;
  function scheduleSave(newConv){
    clearTimeout(saveTimeout);
    saveTimeout=setTimeout(async()=>{
      const conv=newConv||conventionSel.value;
      await saveBlocks(questionId, blocks, conv);
    }, 600);
  }
  render();
  return { getBlocks: ()=>blocks, setBlocks: (nb)=>{blocks=nb; render();} };
}
export function runSolver(blocks){
  const vars={};
  blocks.forEach(b=>{ if(b.type==="constants") (b.constants||[]).forEach(c=>{ if(c.name&&c.value){ const v=parseFloat(c.value); if(!isNaN(v)) vars[c.name]=v; }});});
  const results=[];
  blocks.forEach(b=>{ if(b.type==="formula"&&b.latex){
    try{
      const expr=b.latex.replace(/\\/g,"").trim();
      const sides=expr.split("=").map(s=>s.trim());
      if(sides.length===2){
        const allVars=[...new Set((expr.match(/[a-zA-Z_]\w*/g)||[]))];
        const unknowns=allVars.filter(v=>!(v in vars));
        if(unknowns.length===1){
          const unknown=unknowns[0];
          const fn=(val)=>{ try{ const scope={...vars,[unknown]:val}; let ev=sides[0]+"-("+sides[1]+")"; for(const [k,v] of Object.entries(scope)) ev=ev.replace(new RegExp(`\\b${k}\\b`,"g"),v); return eval(ev); }catch{return NaN;}};
          let lo=-1e6, hi=1e6; for(let i=0;i<100;i++){ const mid=(lo+hi)/2; const v=fn(mid); if(Math.abs(v)<1e-6){ vars[unknown]=mid; b.result=`${unknown} = ${mid}`; results.push(b.result); break;} if(v>0) hi=mid; else lo=mid;}
        }
      }
    }catch(e){ b.result="error: "+e.message; }
  }});
  return results;
}
export async function saveBlocks(questionId, blocks, convention){
  await fetch(`/api/questions/${questionId}/solution`, {method:"PUT", headers:{"Content-Type":"application/json"}, credentials:"include", body: JSON.stringify({convention, blocks: JSON.stringify(blocks)})});
}
