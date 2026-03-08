import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useToast } from '../contexts/ToastContext';
import { getJobs } from '../services/jobs';
import { usePolling } from '../hooks/usePolling';
import { formatJobType } from '../utils/jobLabels';

const FAST_POLL_INTERVAL_MS = 10000;
const IDLE_POLL_INTERVAL_MS = 60000;
const ACTIVE_JOB_STATUSES = new Set(['PENDING', 'RUNNING', 'RETRY_SCHEDULED', 'CANCEL_REQUESTED']);

export default function JobStatusNotifier() {
    const { showToast } = useToast();
    const { t } = useTranslation();
    const location = useLocation();
    const runningJobsRef = useRef(new Set());
    const [pollIntervalMs, setPollIntervalMs] = useState(IDLE_POLL_INTERVAL_MS);
    const jobsPageActive = location.pathname.startsWith('/jobs');

    const checkJobs = useCallback(async () => {
        try {
            const jobs = await getJobs(50, 0, [], {}, { includeEstimates: false });
            const currentRunning = new Set();

            jobs.forEach((job) => {
                const wasRunning = runningJobsRef.current.has(job.id);
                const isActive = ACTIVE_JOB_STATUSES.has(job.status);

                if (isActive) {
                    currentRunning.add(job.id);
                } else if (wasRunning) {
                    if (job.status === 'COMPLETED') {
                        showToast(
                            <div className="flex items-center gap-2">
                                <span>{t('jobNotifier.completed', { type: formatJobType(job.type, t) })}</span>
                            </div>,
                            'success'
                        );
                        window.dispatchEvent(new CustomEvent('job-completed', { detail: { job } }));
                    } else if (job.status === 'FAILED') {
                        showToast(
                            <div className="flex items-center gap-2">
                                <span>{t('jobNotifier.failed', { type: formatJobType(job.type, t) })}</span>
                            </div>,
                            'error'
                        );
                    }
                }
            });

            runningJobsRef.current = currentRunning;
            setPollIntervalMs(currentRunning.size > 0 ? FAST_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS);
        } catch (error) {
            console.error('Error checking jobs:', error);
        }
    }, [showToast, t]);

    useEffect(() => {
        const refreshWhenVisible = () => {
            if (jobsPageActive || document.visibilityState === 'hidden') return;
            void checkJobs();
        };

        document.addEventListener('visibilitychange', refreshWhenVisible);
        window.addEventListener('focus', refreshWhenVisible);
        return () => {
            document.removeEventListener('visibilitychange', refreshWhenVisible);
            window.removeEventListener('focus', refreshWhenVisible);
        };
    }, [checkJobs, jobsPageActive]);

    usePolling({
        callback: checkJobs,
        intervalMs: pollIntervalMs,
        enabled: !jobsPageActive,
        pauseWhenHidden: true,
        runImmediately: true,
    });

    return null;
}
