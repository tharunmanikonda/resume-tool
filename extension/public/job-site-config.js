(() => {
  // Shared by the background worker, page reader, and toolbar launcher.
  const definitions = [
    { source: 'breezy', hosts: ['breezy.hr'], path: /\/p\/[^/]+/i,
      title: ['.position-header h1'], description: ['.position .description', '.description'], company: ['.company-name'], location: ['.position-header .type .fa-map-marker + span'] },
    { source: 'workday', hosts: ['myworkdayjobs.com', 'myworkdaysite.com', 'workday.com'], path: /\/job\//i,
      title: ['[data-automation-id="jobPostingHeader"]'], description: ['[data-automation-id="jobPostingDescription"]'], location: ['[data-automation-id="locations"]'], posted: ['[data-automation-id="postedOn"]'] },
    { source: 'icims', hosts: ['icims.com'], path: /\/jobs\/\d+/i,
      title: ['.iCIMS_Header h1', '.iCIMS_Header'], description: ['.iCIMS_JobContent', '.iCIMS_JobDescription'], location: ['.iCIMS_JobHeaderGroup .iCIMS_JobHeaderData'], posted: ['[itemprop="datePosted"]'] },
    { source: 'smartrecruiters', hosts: ['smartrecruiters.com'], path: /\/[^/]+\/\d+/,
      title: ['.job-title', '[itemprop="title"]'], description: ['.job-sections', '[itemprop="description"]'], company: ['[itemprop="hiringOrganization"]'], location: ['[itemprop="jobLocation"]'] },
    { source: 'workable', hosts: ['apply.workable.com'], path: /\/[^/]+\/j\/[^/]+/i,
      title: ['[data-ui="job-title"]'], description: ['[data-ui="job-description"], [data-ui="job-requirements"], [data-ui="job-benefits"]', '[data-ui="job-description-container"]'], location: ['[data-ui="job-location"]'] },
    { source: 'oracle', hosts: ['oraclecloud.com'], path: /\/job\/\d+/i,
      title: ['.job-details__title', '[data-bind*="jobTitle"]'], description: ['.job-details__description-content', '.job-details__description'], location: ['.job-details__location'] },
    { source: 'taleo', hosts: ['taleo.net'], path: /\/(?:jobdetail|requisition)\./i, query: ['job'],
      title: ['[id*="requisitionDescriptionInterface.reqTitleLink"]', '[id*="requisitionTitle"]'], description: ['[id*="requisitionDescriptionInterface.ID"]', '.jobdescription'] },
    { source: 'successfactors', hosts: ['successfactors.com', 'successfactors.eu', 'sapsf.com'], path: /\/(?:job|career|sfcareer)/i, query: ['career_job_req_id', 'jobId'],
      title: ['.jobTitle', '[itemprop="title"]'], description: ['.jobdescription', '[itemprop="description"]'] },
    { source: 'jobvite', hosts: ['jobvite.com'], path: /\/job\//i, query: ['j'],
      title: ['.jv-header h2', '.jv-job-detail-title'], description: ['.jv-job-detail-description'], location: ['.jv-job-detail-meta'] },
    { source: 'bamboohr', hosts: ['bamboohr.com'], path: /\/(?:careers|jobs)\/\d+/i, query: ['id'],
      title: ['[data-testid="job-title"]', '.BambooHR-ATS-board h2'], description: ['[data-testid="job-description"]', '.BambooHR-ATS-Description'] },
    { source: 'personio', hosts: ['jobs.personio.de', 'jobs.personio.com'], path: /\/job\/\d+/i,
      title: ['.job-position-title'], description: ['.job-description', '.job-details'] },
    { source: 'indeed', hosts: ['indeed.com'], path: /\/(?:viewjob|rc\/clk|pagead\/clk)/i, query: ['jk', 'vjk'],
      title: ['[data-testid="jobsearch-JobInfoHeader-title"]', '.jobsearch-JobInfoHeader-title'], description: ['#jobDescriptionText'], company: ['[data-testid="inlineHeader-companyName"]'], location: ['[data-testid="inlineHeader-companyLocation"]'], posted: ['.jobsearch-JobMetadataFooter', '[data-testid="jobsearch-JobMetadataFooter"]'] },
    { source: 'glassdoor', hosts: ['glassdoor.com'], path: /\/job-listing\//i, query: ['jobListingId', 'jl'],
      title: ['[data-test="job-title"]'], description: ['[data-test="jobDescriptionContent"]', '[class*="JobDetails_jobDescription"]'], company: ['[data-test="employer-name"]'], location: ['[data-test="location"]'] },
    { source: 'ziprecruiter', hosts: ['ziprecruiter.com'], path: /\/(?:c\/[^/]+\/Job\/|jobs\/[^/]+\/[^/]+|job\/)/i, query: ['jid', 'job_id'],
      title: ['[data-testid="job_title"]', '[data-testid="job-title"]'], description: ['[data-testid="job_description"]', '[data-testid="job-description"]', '.job_description'], company: ['[data-testid="company_name"]'] },
    { source: 'monster', hosts: ['monster.com'], path: /\/(?:job-openings|job)\//i,
      title: ['[data-testid="jobTitle"]'], description: ['[data-testid="jobDescription"]', '#JobDescription'] },
    { source: 'usajobs', hosts: ['usajobs.gov'], path: /\/job\/\d+/i,
      title: ['.usajobs-joa-banner__title', 'h1'], description: ['#job-details', '.usajobs-joa-details'], company: ['.usajobs-joa-banner__agency'], location: ['.usajobs-joa-locations'] },
    { source: 'avature', hosts: ['avature.net'], path: /\/(?:JobDetail|JobDetails)\//i,
      title: ['.article__header__text__title', '.job-title'], description: ['.article__content', '.job-description'] },
    { source: 'phenom', hosts: ['phenompeople.com', 'careers.phenom.com'], path: /\/job\//i,
      title: ['.job-title'], description: ['.job-description', '[data-ph-at-id="job-description"]'] },
  ];
  const excluded = ['linkedin.com', 'dice.com', 'hiring.cafe', 'hiringcafe.com', 'greenhouse.io', 'lever.co', 'ashbyhq.com', 'ashby.com', 'rippling.com', 'jobs.dover.com'];
  function hostMatches(host, suffix) { return host === suffix || host.endsWith(`.${suffix}`); }
  function platform(value) {
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol)) return null;
      return definitions.find(site => site.hosts.some(host => hostMatches(url.hostname, host))) || null;
    } catch (_) { return null; }
  }
  function isDetail(value) {
    const site = platform(value);
    if (!site) return false;
    const url = new URL(value);
    return site.path.test(url.pathname) || (site.query || []).some(key => Boolean(url.searchParams.get(key)));
  }
  function skip(value) {
    try {
      const url = new URL(value);
      return ['localhost', '127.0.0.1'].includes(url.hostname) || excluded.some(host => hostMatches(url.hostname, host));
    } catch (_) { return true; }
  }
  globalThis.ResumeJobSites = { definitions, platform, isDetail, skip };
})();
