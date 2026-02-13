import { useState } from 'react';
import { jobsService } from '../services/jobs';

export function useUpload(accountId, folderId, onSuccess) {
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        setProgress(0);

        try {
            await jobsService.uploadFileBackground(
                accountId,
                folderId || 'root',
                file,
                (pct) => setProgress(pct)
            );

            if (onSuccess) onSuccess();
        } catch (e) {
            console.error(e);
            // Error is now handled by the generic error handler or we can show toast
            // But let's keep alert for now to be safe or use toast if available in context (not passed here)
            alert(`Upload failed: ${e.message || 'Unknown error'}`);
        } finally {
            setUploading(false);
            setProgress(0);
        }
    };

    return { upload, uploading, progress };
}
