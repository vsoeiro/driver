const STATUS_KEYS = {
    PENDING: 'jobStatus.PENDING',
    RUNNING: 'jobStatus.RUNNING',
    COMPLETED: 'jobStatus.COMPLETED',
    FAILED: 'jobStatus.FAILED',
    RETRY_SCHEDULED: 'jobStatus.RETRY_SCHEDULED',
    CANCEL_REQUESTED: 'jobStatus.CANCEL_REQUESTED',
    CANCELLED: 'jobStatus.CANCELLED',
    DEAD_LETTER: 'jobStatus.DEAD_LETTER',
};

export function formatJobStatus(status, t = null) {
    if (!status) return t ? t('jobStatus.unknown') : 'Unknown';
    if (STATUS_KEYS[status]) {
        return t ? t(STATUS_KEYS[status]) : status;
    }
    return status
        .toString()
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

export function formatJobType(type, t = null) {
    if (!type) return t ? t('jobType.unknown') : 'Unknown';
    if (t) {
        const key = `jobType.${String(type).toLowerCase()}`;
        const translated = t(key);
        if (translated !== key) return translated;
    }
    return type
        .toString()
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}
