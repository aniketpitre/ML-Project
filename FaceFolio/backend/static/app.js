const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');
const status = document.getElementById('status');
const result = document.getElementById('result');
const identifiedDiv = document.getElementById('identified');
const unidentifiedDiv = document.getElementById('unidentified');
const finalizeBtn = document.getElementById('finalizeBtn');
const autoSortBtn = document.getElementById('autoSortBtn');

let lastResponse = null;

function setStatus(msg, isError=false){
  status.textContent = msg;
  status.style.color = isError ? 'crimson' : '#444';
}

// shared upload function used by both uploadBtn and processAnotherBtn
async function doUpload(){
  const f = fileInput.files[0];
  if(!f){ setStatus('Please choose an image file to upload', true); return }
  setStatus('Uploading...');

  const fd = new FormData();
  fd.append('file', f, f.name);

  try{
    const res = await fetch('/api/process-photo', { method: 'POST', body: fd });
    if(!res.ok){
      const text = await res.text();
      setStatus('Upload failed: '+res.status+' '+text, true);
      return;
    }
    const data = await res.json();
    lastResponse = data;
    renderResult(data);
    setStatus('Scan complete.');
  }catch(err){
    setStatus('Upload error: '+err, true);
  }
}

uploadBtn.addEventListener('click', doUpload);

// If user selects a file, show the Process Selected Image button
// Optional: show selected filename in the chooser (accessible feedback)
fileInput.addEventListener('change', ()=>{
  const label = document.querySelector('.file-chooser');
  if(label){
    const f = fileInput.files[0];
    label.textContent = f ? f.name : 'Choose a photo';
  }
});

function renderResult(data){
  result.style.display = '';
  identifiedDiv.innerHTML = '';
  unidentifiedDiv.innerHTML = '';
  finalizeBtn.style.display = 'none';

  const idents = data.identified_people || [];
  const unids = data.unidentified_faces || [];

  const hIdent = document.createElement('div');
  hIdent.innerHTML = '<strong>Identified people:</strong>';
  if(idents.length===0){
    hIdent.innerHTML += ' <em>none</em>';
  }else{
    const ul = document.createElement('ul');
    idents.forEach(n=>{ const li=document.createElement('li'); li.textContent = n; ul.appendChild(li); });
    hIdent.appendChild(ul);
  }
  identifiedDiv.appendChild(hIdent);

  // Add a finalize/sort button directly under the identified people list
  // (visible when there are identified people)
  // Remove existing one if present
  const existingBelow = document.getElementById('finalizeBelowBtn');
  if(existingBelow) existingBelow.remove();
  if(idents.length > 0){
    const btn = document.createElement('button');
    btn.id = 'finalizeBelowBtn';
    btn.style.marginTop = '8px';
    btn.textContent = 'Finalize & Sort (identified only)';
    btn.addEventListener('click', async ()=>{
      if(!lastResponse) return;
      setStatus('Finalizing & sorting identified people...');
      const temp = lastResponse.temp_photo_path;
      const identified_people = lastResponse.identified_people || [];
      const payload = { temp_photo_path: temp, identified_people, new_labels: [] };
      try{
        const res = await fetch('/api/finalize-and-sort', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        const txt = await res.text();
        if(!res.ok){ setStatus('Finalize failed: '+res.status+' '+txt, true); return; }
        setStatus('Finalize OK: '+txt);
        // hide other action buttons
        if(finalizeBtn) finalizeBtn.style.display='none';
        if(autoSortBtn) autoSortBtn.style.display='none';
        btn.style.display = 'none';
      }catch(err){ setStatus('Finalize error: '+err, true); }
    });
    identifiedDiv.appendChild(btn);
  }

  const hUnid = document.createElement('div');
  hUnid.innerHTML = '<strong>Unidentified faces (label them):</strong>';
  if(unids.length===0){
    hUnid.innerHTML += ' <em>none</em>';
  }else{
    const grid = document.createElement('div'); grid.className='grid';
    unids.forEach(u=>{
      const card = document.createElement('div'); card.className='card';
      const img = document.createElement('img'); img.src = u.image_url; img.alt = u.temp_id;
      const inp = document.createElement('input'); inp.placeholder = 'Name for this face'; inp.type='text'; inp.dataset.tempId = u.temp_id;
      card.appendChild(img); card.appendChild(inp);
      grid.appendChild(card);
    });
    hUnid.appendChild(grid);
    finalizeBtn.style.display='inline-block';
    // show auto-sort if there are identified people
    if(idents.length > 0 && autoSortBtn){
      autoSortBtn.style.display = 'inline-block';
    } else if(autoSortBtn){
      autoSortBtn.style.display = 'none';
    }
  }
  unidentifiedDiv.appendChild(hUnid);
}

finalizeBtn.addEventListener('click', async ()=>{
  if(!lastResponse) return;
  setStatus('Finalizing...');
  const temp = lastResponse.temp_photo_path;
  const identified_people = lastResponse.identified_people || [];
  // collect new labels
  const inputs = Array.from(document.querySelectorAll('#unidentified input'));
  const new_labels = inputs.map(i=>({ temp_id: i.dataset.tempId, name: i.value.trim() })).filter(x=>x.name);

  const payload = { temp_photo_path: temp, identified_people, new_labels };

  try{
    const res = await fetch('/api/finalize-and-sort', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const txt = await res.text();
    if(!res.ok){ setStatus('Finalize failed: '+res.status+' '+txt, true); return; }
    setStatus('Finalize OK: '+txt);
    // hide finalize button to avoid double submissions
    finalizeBtn.style.display='none';
    if(autoSortBtn) autoSortBtn.style.display='none';
  }catch(err){ setStatus('Finalize error: '+err, true); }
});

// Auto-sort: use identified people only, no new labels
if(autoSortBtn){
  autoSortBtn.addEventListener('click', async ()=>{
    if(!lastResponse) return;
    setStatus('Auto-sorting...');
    const temp = lastResponse.temp_photo_path;
    const identified_people = lastResponse.identified_people || [];
    if(identified_people.length === 0){ setStatus('No identified people to sort for.', true); return; }

    const payload = { temp_photo_path: temp, identified_people, new_labels: [] };
    try{
      const res = await fetch('/api/finalize-and-sort', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
      const txt = await res.text();
      if(!res.ok){ setStatus('Auto-sort failed: '+res.status+' '+txt, true); return; }
      setStatus('Auto-sort OK: '+txt);
      finalizeBtn.style.display='none';
      autoSortBtn.style.display='none';
    }catch(err){ setStatus('Auto-sort error: '+err, true); }
  });
}

// On load, small check
(async ()=>{
  try{
    const r = await fetch('/api/process-photo', { method: 'OPTIONS' });
    // no-op, just checking server
  }catch(e){ /* ignore */ }
})();
