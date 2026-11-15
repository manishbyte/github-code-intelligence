# Recruiter dashboard

Visible to `recruiter` and `admin` users (set with SQL, see README). Pages: **Overview** (latest pass rate per suite,
safety pass rate, recent runs, regression flags), **Runs** (start a run — admin only —, details, downloads),
**Quality** (mean score and latency), **Safety** (guardrail results by check type), **Failures** (failed/errored cases
with details), **Model comparison** (latest pass rate per suite for each model). Data comes from `/api/v1/evaluations/*`.
