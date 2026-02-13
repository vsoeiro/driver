import React, { useEffect, useRef } from 'react';
import { useToast } from '../contexts/ToastContext';
import { getJobs } from '../services/jobs';
import { CheckCircle, XCircle } from 'lucide-react';

export default function JobStatusNotifier() {
    const { showToast } = useToast();
    const runningJobsRef = useRef(new Set());
    const firstLoadRef = useRef(true);

    useEffect(() => {
        const checkJobs = async () => {
            try {
                const jobs = await getJobs();
                const currentRunning = new Set();

                // On first load, just populate running jobs without notifying
                if (firstLoadRef.current) {
                    jobs.forEach(job => {
                        if (job.status === 'RUNNING' || job.status === 'PENDING') {
                            runningJobsRef.current.add(job.id);
                        }
                    });
                    firstLoadRef.current = false;
                    return;
                }

                // Check for completions
                jobs.forEach(job => {
                    const wasRunning = runningJobsRef.current.has(job.id);

                    if (job.status === 'RUNNING' || job.status === 'PENDING') {
                        currentRunning.add(job.id);
                    } else if (wasRunning) {
                        // Job was running, now it's not -> Completed or Failed
                        if (job.status === 'COMPLETED') {
                            showToast(
                                <div className="flex items-center gap-2">
                                    <span>Job <strong>{job.type.replace(/_/g, ' ')}</strong> completed successfully!</span>
                                </div>,
                                'success'
                            );
                            // Dispatch event for FileBrowser to refresh
                            window.dispatchEvent(new CustomEvent('job-completed', { detail: { job } }));
                        } else if (job.status === 'FAILED') {
                            showToast(
                                <div className="flex items-center gap-2">
                                    <span>Job <strong>{job.type.replace(/_/g, ' ')}</strong> failed.</span>
                                </div>,
                                'error'
                            );
                        }
                    }
                });

                // Update ref
                runningJobsRef.current = currentRunning;

            } catch (error) {
                console.error('Error checking jobs:', error);
            }
        };

        const interval = setInterval(checkJobs, 5000); // Poll every 5 seconds
        checkJobs(); // Run immediately

        return () => clearInterval(interval);
    }, [showToast]);

    return null; // This component doesn't render anything visible
}
