import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useToast } from './ToastContext';
import { formatJobType } from '../utils/jobLabels';
import { useJobActivityQuery } from '../features/jobs/hooks/useJobsData';

const FAST_POLL_INTERVAL_MS = 10000;
const IDLE_POLL_INTERVAL_MS = 60000;
const ACTIVE_JOB_STATUSES = new Set(['PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'CANCEL_REQUESTED']);

const JobActivityContext = createContext({
    jobs: [],
    hasActiveJobs: false,
    isLoading: false,
    refetch: async () => undefined,
    canRefresh: false,
});

export function JobActivityProvider({ children }) {
    const { showToast } = useToast();
    const { t } = useTranslation();
    const location = useLocation();
    const previousActiveJobsRef = useRef(new Set());
    const jobsPageActive = location.pathname.startsWith('/jobs');

    const jobsQuery = useJobActivityQuery({
        enabled: !jobsPageActive,
        refetchInterval: (query) => {
            if (jobsPageActive) return false;
            const jobs = Array.isArray(query.state.data) ? query.state.data : [];
            return jobs.some((job) => ACTIVE_JOB_STATUSES.has(job.status))
                ? FAST_POLL_INTERVAL_MS
                : IDLE_POLL_INTERVAL_MS;
        },
        refetchIntervalInBackground: false,
    });

    const { data: jobs = [], isLoading, refetch: refetchJobs } = jobsQuery;
    const hasActiveJobs = jobs.some((job) => ACTIVE_JOB_STATUSES.has(job.status));

    useEffect(() => {
        const currentActiveJobs = new Set();

        jobs.forEach((job) => {
            const wasActive = previousActiveJobsRef.current.has(job.id);
            const isActive = ACTIVE_JOB_STATUSES.has(job.status);

            if (isActive) {
                currentActiveJobs.add(job.id);
                return;
            }

            if (!wasActive) {
                return;
            }

            if (job.status === 'COMPLETED') {
                showToast(
                    t('jobNotifier.completed', { type: formatJobType(job.type, t) }),
                    'success',
                );
                window.dispatchEvent(new CustomEvent('job-completed', { detail: { job } }));
                return;
            }

            if (job.status === 'FAILED') {
                showToast(
                    t('jobNotifier.failed', { type: formatJobType(job.type, t) }),
                    'error',
                );
            }
        });

        previousActiveJobsRef.current = currentActiveJobs;
    }, [jobs, showToast, t]);

    const refetch = useCallback(async () => {
        if (jobsPageActive) return jobs;
        const result = await refetchJobs();
        return result.data;
    }, [jobs, jobsPageActive, refetchJobs]);

    useEffect(() => {
        const refreshWhenVisible = () => {
            if (jobsPageActive || document.visibilityState === 'hidden') return;
            void refetch();
        };

        document.addEventListener('visibilitychange', refreshWhenVisible);
        window.addEventListener('focus', refreshWhenVisible);
        return () => {
            document.removeEventListener('visibilitychange', refreshWhenVisible);
            window.removeEventListener('focus', refreshWhenVisible);
        };
    }, [jobsPageActive, refetch]);

    const value = useMemo(() => ({
        jobs,
        hasActiveJobs,
        isLoading,
        refetch,
        canRefresh: !jobsPageActive,
    }), [hasActiveJobs, isLoading, jobs, jobsPageActive, refetch]);

    return (
        <JobActivityContext.Provider value={value}>
            {children}
        </JobActivityContext.Provider>
    );
}

export function useJobActivity() {
    return useContext(JobActivityContext);
}

export default JobActivityContext;
