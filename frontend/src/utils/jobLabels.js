const STATUS_LABELS = {
    PENDING: 'Pending',
    RUNNING: 'Running',
    COMPLETED: 'Completed',
    FAILED: 'Failed',
    RETRY_SCHEDULED: 'Retry Scheduled',
    CANCEL_REQUESTED: 'Cancelling',
    CANCELLED: 'Cancelled',
    DEAD_LETTER: 'Dead Letter',
};

export function formatJobStatus(status) {
    if (!status) return 'Unknown';
    if (STATUS_LABELS[status]) return STATUS_LABELS[status];
    return status
        .toString()
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

export function formatJobType(type) {
    if (!type) return 'Unknown';
    return type
        .toString()
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}
