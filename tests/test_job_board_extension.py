from extension_drafts import normalize_context


def test_query_selected_jobs_keep_distinct_source_links():
    for source, path, query in [
        ('indeed', '/viewjob', 'jk=job123'),
        ('taleo', '/careersection/2/jobdetail.ftl', 'job=123'),
        ('successfactors', '/career', 'career_job_req_id=123'),
        ('glassdoor', '/job-listing/engineer.htm', 'jl=123'),
    ]:
        context = normalize_context({'source': source, 'url': f'https://jobs.example.test{path}?{query}&utm_source=tracking', 'role_title': 'Engineer', 'company_name': 'Acme', 'job_description': 'Build services. ' * 15, 'source_metadata': {'posted_at': '2026-11-03', 'updated_at': '2026-11-04'}})
        assert context['canonical_url'].endswith('?' + query)
        assert context['source_metadata']['posted_at'] == '2026-11-03'
        assert 'utm_source' not in context['canonical_url']
