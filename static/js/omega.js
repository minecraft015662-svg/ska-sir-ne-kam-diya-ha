(function(){
  async function poll(id){
    try{
      const r=await fetch('/api/jobs/'+id,{headers:{'Accept':'application/json'}}); if(!r.ok)return;
      const j=await r.json(); const row=document.querySelector('[data-job="'+id+'"]');
      if(row){const p=row.querySelector('.progress i'),m=row.querySelector('.job-message'),pct=row.querySelector('.job-pct'); p.style.width=(j.progress||0)+'%';m.textContent=j.message||'';pct.textContent=(j.progress||0)+'%';}
      if(!['done','error'].includes(j.status)) setTimeout(()=>poll(id),1800); else setTimeout(()=>location.reload(),900);
    }catch(e){setTimeout(()=>poll(id),3000)}
  }
  (window.OMEGA_JOBS||[]).forEach(poll);
})();
