import { useState } from 'react';
import { jobsService } from '../services/jobs';

export function useUpload(accountId, folderId, onSuccess, onError) {
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);

    const upload = async (input) => {
        const files = input instanceof File
            ? [input]
            : Array.isArray(input)
                ? input.filter(Boolean)
                : Array.from(input || []).filter(Boolean);
        if (files.length === 0) return;

        setUploading(true);
        setProgress(0);

        let failed = 0;
        try {
            for (let index = 0; index < files.length; index += 1) {
                const file = files[index];
                try {
                    await jobsService.uploadFileBackground(
                        accountId,
                        folderId || 'root',
                        file,
                        (pct) => {
                            const overall = ((index + (pct / 100)) / files.length) * 100;
                            setProgress(Math.max(0, Math.min(100, Math.round(overall))));
                        }
                    );
                    setProgress(Math.round(((index + 1) / files.length) * 100));
                } catch (error) {
                    failed += 1;
                    console.error(error);
                }
            }

            if (onSuccess) onSuccess();
        } finally {
            setUploading(false);
            setProgress(0);
        }

        if (failed > 0 && onError) onError(failed);
    };

    return { upload, uploading, progress };
}
