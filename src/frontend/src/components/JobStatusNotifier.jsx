import { useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useToast } from '../contexts/ToastContext';
import { getJobs } from '../services/jobs';
import { usePolling } from '../hooks/usePolling';
import { formatJobType } from '../utils/jobLabels';

export default function JobStatusNotifier() {
    const { showToast } = useToast();
    const location = useLocation();
    const runningJobsRef = useRef(new Set());
    const firstLoadRef = useRef(true);
    const jobsPageActive = location.pathname.startsWith('/jobs');

    const checkJobs = useCallback(async () => {
        try {
            const jobs = await getJobs(50, 0, [], {}, { includeEstimates: false });
            const currentRunning = new Set();

            if (firstLoadRef.current) {
                jobs.forEach((job) => {
                    if (job.status === 'RUNNING' || job.status === 'PENDING') {
                        runningJobsRef.current.add(job.id);
                    }
                });
                firstLoadRef.current = false;
                return;
            }

            jobs.forEach((job) => {
                const wasRunning = runningJobsRef.current.has(job.id);

                if (job.status === 'RUNNING' || job.status === 'PENDING') {
                    currentRunning.add(job.id);
                } else if (wasRunning) {
                    if (job.status === 'COMPLETED') {
                        showToast(
                            <div className="flex items-center gap-2">
                                <span>Job <strong>{formatJobType(job.type)}</strong> completed successfully!</span>
                            </div>,
                            'success'
                        );
                        window.dispatchEvent(new CustomEvent('job-completed', { detail: { job } }));
                    } else if (job.status === 'FAILED') {
                        showToast(
                            <div className="flex items-center gap-2">
                                <span>Job <strong>{formatJobType(job.type)}</strong> failed.</span>
                            </div>,
                            'error'
                        );
                    }
                }
            });

            runningJobsRef.current = currentRunning;
        } catch (error) {
            console.error('Error checking jobs:', error);
        }
    }, [showToast]);

    usePolling({
        callback: checkJobs,
        intervalMs: 10000,
        enabled: !jobsPageActive,
        pauseWhenHidden: true,
        runImmediately: true,
    });

    return null;
}
