function relationshipScope(){return document.getElementById('relationship-filter')?.value||'all';}
function refreshRelationshipGroups(scope,counts){
 const n=group=>scope.filter(r=>r.relationship===group).length;
 for(const node of document.querySelectorAll('[data-relationship-heading]')){
  const group=node.dataset.relationshipHeading;node.hidden=!n(group);
  node.querySelector('[data-relationship-count]').textContent=n(group);
 }
 for(const node of document.querySelectorAll('[data-relationship-empty]')){
  const group=node.dataset.relationshipEmpty;
  node.hidden=!n(group)||(counts[node.dataset.relationshipArea+':'+group]||0)>0;
 }
 const block=document.getElementById('without-websites');
 if(block){
  const query=document.getElementById('search').value.trim().toLocaleLowerCase('pl');let count=0;
  for(const node of block.querySelectorAll('[data-no-website-partner]')){
   node.hidden=relationshipScope()==='other'||!node.dataset.noWebsitePartner.includes(query);if(!node.hidden)count++;
  }
  block.hidden=!count;document.getElementById('without-websites-count').textContent=count;
  const note=document.getElementById('relationship-no-web-note');
  if(note){note.hidden=!(count&&query);note.textContent='Partnerzy bez strony WWW: '+count+'. Wykaz poniżej.';}
 }
}
