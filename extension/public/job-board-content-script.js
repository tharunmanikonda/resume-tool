(() => {
  const sites = globalThis.ResumeJobSites;
  if (!sites || sites.skip(location.href)) return;
  let version, runtimeId;
  try { version = chrome.runtime.getManifest().version; runtimeId = chrome.runtime.id; } catch (_) { return; }
  const previous = globalThis.__resumeJobBoardReader;
  if (previous?.version === version && previous?.runtimeId === runtimeId && previous.active()) return;
  previous?.shutdown();
  let stopped = false, timer, observer, watchdog;
  let observedKey = '', published = '', pending = '', lastJobKey = '', lastDescription = '';
  const clean = value => String(value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  const active = () => { try { return !stopped && Boolean(chrome.runtime.id); } catch (_) { return false; } };
  function send(message) {
    if (!active()) return shutdown();
    try { chrome.runtime.sendMessage(message)?.catch?.(() => {}); } catch (_) { shutdown(); }
  }
  function visible(node) {
    return node && node.getBoundingClientRect().width > 0 && node.getBoundingClientRect().height > 0 && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden';
  }
  function text(selectors, root = document) {
    for (const selector of selectors || []) {
      const node = [...root.querySelectorAll(selector)].find(visible);
      if (node) return clean(node.innerText || node.textContent);
    }
    return '';
  }
  function html(value) {
    const root = document.createElement('div'); root.innerHTML = String(value || '');
    root.querySelectorAll('script, style, form, nav, button, input, textarea, select').forEach(node => node.remove());
    root.querySelectorAll('br').forEach(node => node.replaceWith('\n'));
    root.querySelectorAll('p, div, li, h1, h2, h3, h4, section').forEach(node => node.append('\n'));
    return clean(root.textContent);
  }
  function collect(value, results) {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) return value.forEach(item => collect(item, results));
    const types = [].concat(value['@type'] || []);
    if (types.some(type => /(?:^|\/)JobPosting$/.test(type))) results.push(value);
    collect(value['@graph'], results); collect(value.mainEntity, results);
    // ItemList entries must not be mistaken for the selected job.
  }
  function structured(site, detail) {
    const jobs = [];
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try { collect(JSON.parse(script.textContent), jobs); } catch (_) {}
    }
    const current = new URL(location.href);
    const selectedId = current.searchParams.get('vjk') || current.searchParams.get('jk') || current.searchParams.get('jobListingId') || current.searchParams.get('jl');
    const exact = jobs.find(job => {
      const id = String(job.identifier?.value || job.identifier || '');
      if (selectedId && id === selectedId) return true;
      try { return job.url && new URL(job.url, location.href).pathname.replace(/\/$/, '') === current.pathname.replace(/\/$/, '') && !selectedId; } catch (_) { return false; }
    });
    if (exact) return exact;
    // Known search pages require a selected-detail URL. Unknown sites require one posting.
    if ((site && !detail) || jobs.length !== 1) return null;
    const job = jobs[0];
    if (selectedId && String(job.identifier?.value || job.identifier || '') !== selectedId) return null;
    if (job.url) {
      try { if (new URL(job.url, location.href).pathname.replace(/\/$/, '') !== current.pathname.replace(/\/$/, '')) return null; } catch (_) { return null; }
    }
    return job;
  }
  function canonical() {
    const url = new URL(location.href);
    const allowed = ['jk', 'vjk', 'jobListingId', 'jl', 'job', 'career_job_req_id', 'jobId', 'j', 'id', 'jid', 'job_id'];
    const params = new URLSearchParams();
    for (const key of allowed) if (url.searchParams.get(key)) params.set(key, url.searchParams.get(key));
    return `${url.origin}${url.pathname}${params.size ? `?${params}` : ''}`;
  }
  function date(value) {
    const raw = clean(value);
    return /^\d{4}-\d{2}-\d{2}(?:$|T)/.test(raw) && Number.isFinite(Date.parse(raw)) ? raw : '';
  }
  function dateMeta(property) {
    const node = document.querySelector(`[itemprop="${property}"]`);
    return date(node?.getAttribute('content') || node?.getAttribute('datetime') || node?.textContent);
  }
  function read() {
    if (!active()) return shutdown();
    const site = sites.platform(location.href), detail = sites.isDetail(location.href);
    const key = canonical();
    if (observedKey && key !== observedKey) { send({ type: 'JOB_CONTEXT_CLEARED' }); published = ''; pending = ''; }
    observedKey = key;
    const job = structured(site, detail);
    if ((!site && !job) || (site && !detail)) {
      if (published) send({ type: 'JOB_CONTEXT_CLEARED' });
      published = ''; pending = ''; return;
    }
    let description = html(job?.description);
    if (!description && detail) {
      const selectors = [...(site.description || []), '[itemprop="description"]'];
      // Read all known sections in DOM order, without swallowing navigation or forms.
      let nodes = [];
      for (const selector of selectors) {
        nodes = [...document.querySelectorAll(selector)].filter(visible);
        if (nodes.length) break;
      }
      description = clean(nodes.map(node => html(node.innerHTML)).join('\n\n'));
    }
    const title = clean(job?.title) || text(site?.title) || (detail ? text(['h1']) : '');
    const company = clean(job?.hiringOrganization?.name) || text(site?.company) || text(['[itemprop="hiringOrganization"] [itemprop="name"]', '[data-testid="company-name"]']);
    const locations = [].concat(job?.jobLocation || []).map(item => {
      const address = item.address || {};
      return [address.addressLocality, address.addressRegion, typeof address.addressCountry === 'object' ? address.addressCountry.name : address.addressCountry].filter(Boolean).join(', ');
    }).filter(Boolean);
    const locationText = locations.join(' / ') || text(site?.location) || (job?.jobLocationType === 'TELECOMMUTE' ? 'Remote' : '');
    const dates = {
      posted_at: date(job?.datePosted) || dateMeta('datePosted'),
      updated_at: date(job?.dateModified) || dateMeta('dateModified'),
      posted_text: text(site?.posted).split('\n').find(line => /(?:posted|reposted|\d+\+?\s+days? ago|today|yesterday)/i.test(line)) || '',
    };
    if (!title || description.length < 120) {
      if (published) send({type:'JOB_CONTEXT_CLEARED'});
      published = ''; pending = ''; return;
    }
    if (lastJobKey && lastJobKey !== key && description === lastDescription) { pending = ''; return; }
    const id = clean(job?.identifier?.value || (typeof job?.identifier === 'string' ? job.identifier : '')) || key;
    const context = {
      source: site?.source || 'career_page', external_job_id: key, url: key,
      role_title: title, company_name: company, location: locationText, job_description: description,
      extraction_confidence: company ? 'high' : 'medium',
      source_metadata: { ...dates, posted_at_source: dates.posted_at ? 'page_metadata' : '',
        extraction_method: job ? 'json_ld' : 'platform_dom', extracted_at: new Date().toISOString(), extractor_version: version,
        job_page_reader: true, external_identifier: id, description_scope: "job_description" },
    };
    const fingerprint = JSON.stringify([key, title, company, description, locationText, dates]);
    if (fingerprint === published) return;
    if (fingerprint !== pending) { pending = fingerprint; timer = setTimeout(read, 400); return; }
    published = fingerprint; lastJobKey = key; lastDescription = description;
    send({ type:'JOB_CONTEXT', context });
  }
  function schedule() { clearTimeout(timer); if (active()) timer = setTimeout(read, 350); else shutdown(); }
  function message(message, _sender, respond) { if (message?.type === 'READ_JOB_CONTEXT') { schedule(); respond({success:true}); } }
  function shutdown() {
    stopped = true; clearTimeout(timer); clearInterval(watchdog); observer?.disconnect();
    window.removeEventListener('popstate', schedule);
    try { chrome.runtime.onMessage.removeListener(message); } catch (_) {}
  }
  globalThis.__resumeJobBoardReader = { version, runtimeId, active, shutdown };
  chrome.runtime.onMessage.addListener(message);
  window.addEventListener('popstate', schedule);
  observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, {subtree:true, childList:true, characterData:true});
  watchdog = setInterval(() => { if (!active()) return shutdown(); if (canonical() !== observedKey) schedule(); }, 1000);
  schedule();
})();
