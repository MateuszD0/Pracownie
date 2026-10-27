'use strict';
// The portable file needs only a small index. All evidence remains real HTML.
const data=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
let expanded=false,kind='all';
const categories=e=>$('journal-category').value==='all'||$('journal-category').value===e.category||$('journal-category').value==='sales'&&e.bucket==='promotions'||$('journal-category').value==='extras'&&e.bucket==='extras'||$('journal-category').value==='other'&&!['promotions','extras','design'].includes(e.bucket);
function render(){
 const query=$('search').value.trim().toLocaleLowerCase('pl'),page=$('page-filter').value;
 const scope=data.rows.filter(r=>(relationshipScope()==='all'||r.relationship===relationshipScope())&&(r.domain+' '+r.name+' '+(r.studio_name||'')+' '+(r.partner_code||'')).toLocaleLowerCase('pl').includes(query));
 const eligible=e=>scope.some(r=>r.domain===e.domain)&&e.items.some(i=>(page==='all'||i.page===page)&&categories(i));
 const selected=scope.filter(r=>kind==='all'||kind==='changed'&&data.events.some(e=>e.domain===r.domain&&eligible(e))||kind==='review'&&!r.complete||kind==='missing'&&r.missing);
 const domains=new Set(selected.map(r=>r.domain));
 let main=0,review=0;const groupCounts={};
 for(const e of data.events){
  const visible=domains.has(e.domain)&&eligible(e),tr=document.querySelector('[data-brief-id="'+e.id+'"]');
  const groupKey=e.tier+':'+(e.group||'all');if(visible)groupCounts[groupKey]=(groupCounts[groupKey]||0)+1;
  if(e.tier==='main'&&visible)main++;if(e.tier==='review'&&visible)review++;
  tr.hidden=!visible||(e.tier==='main'&&groupCounts[groupKey]>5&&!expanded);
  tr.querySelector('[data-brief-places]').textContent=[...new Set(e.items.filter(i=>(page==='all'||i.page===page)&&categories(i)).map(i=>i.page==='glowna'?'Strona główna':'Karta projektu'))].join(' · ');
  document.querySelector('[data-brief-proof="'+e.id+'"]').hidden=!visible;
 }
 document.querySelector('[data-brief-empty="main"]').hidden=!!$('relationship-filter')||main>0;
 document.querySelector('[data-brief-empty="review"]').hidden=!!$('relationship-filter')||review>0;
 refreshRelationshipGroups(selected,groupCounts);
 $('brief-review-cue').hidden=!review;$('brief-review-cue').querySelector('a').textContent='Ważne do sprawdzenia: '+review;
 const extra=Object.entries(groupCounts).filter(([key])=>key.startsWith('main:')).reduce((sum,[,n])=>sum+Math.max(0,n-5),0);
 $('brief-more').hidden=!extra;$('brief-more').textContent=expanded?'Pokaż tylko 5 najważniejszych w grupie':'Pozostałe ważne zmiany ('+extra+')';
 const paired=scope.filter(r=>r.complete).length;
 const pending=scope.filter(r=>r.pending).length;
 $('brief-coverage').textContent='Porównano obie strony: '+paired+'/'+scope.length+' pracowni · '+(pending?pending+' oczekuje na pierwszy skan · Pozostałe braki: '+(scope.length-paired-pending):(scope.length-paired)+' wymaga uwagi');
 for(const [selector,key] of [['.day-domain','domain'],['[data-communication-domain]','communicationDomain'],['[data-journal-domain]','journalDomain'],['[data-availability-domain]','availabilityDomain'],['[data-firm-domain]','firmDomain']])for(const el of document.querySelectorAll(selector))el.hidden=!domains.has(el.dataset[key]);
 for(const el of document.querySelectorAll('[data-intelligence-domain]'))el.hidden=!scope.some(r=>r.domain===el.dataset.intelligenceDomain);
 for(const el of document.querySelectorAll('[data-gap-domain]'))el.hidden=!scope.some(r=>r.domain===el.dataset.gapDomain);
 for(const el of document.querySelectorAll('.daily-page,[data-communication-page],[data-communication-header]'))el.hidden=page!=='all'&&(el.dataset.page||el.dataset.communicationPage||el.dataset.communicationHeader)!==page;
 for(const el of document.querySelectorAll('[data-filter]'))el.setAttribute('aria-pressed',String(el.dataset.filter===kind));
 $('portable-status').textContent=selected.length?'Wyświetlane pracownie: '+selected.length+'/'+data.rows.length:'Brak pracowni spełniających filtry.';
}
$('filters').innerHTML=[['all','Wszystkie'],['changed','Zmiany'],['review','Niepełne porównanie'],['missing','Brak odczytu']].map(([id,label])=>'<button type="button" data-filter="'+id+'">'+label+'</button>').join('');
for(const id of ['search','page-filter','journal-category'])$(id).addEventListener(id==='search'?'input':'change',render);
$('relationship-filter')?.addEventListener('change',()=>{expanded=false;render();});
$('reset-filters').addEventListener('click',()=>{kind='all';expanded=false;if($('relationship-filter'))$('relationship-filter').value='all';$('search').value='';$('page-filter').value='all';$('journal-category').value='all';render();});
$('brief-more').addEventListener('click',()=>{expanded=!expanded;render();});
document.addEventListener('click',event=>{const button=event.target.closest('[data-filter]');if(button){kind=button.dataset.filter;render();}const link=event.target.closest('a[href^="#"]');if(link)requestAnimationFrame(()=>reveal(link.getAttribute('href')));});
function reveal(hash){let target;try{target=document.getElementById(decodeURIComponent(hash.replace(/^#/,'')));}catch{return;}if(!target)return;let parent=target.closest('details');while(parent){parent.open=true;parent=parent.parentElement?.closest('details');}target.scrollIntoView({block:'start'});}
window.addEventListener('hashchange',()=>reveal(location.hash));
render();if(location.hash)reveal(location.hash);
