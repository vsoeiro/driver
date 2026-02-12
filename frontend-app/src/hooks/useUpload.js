import { useState } from 'react';
import { uploadFileSimple, createUploadSession, uploadChunkProxy } from '../services/api';

export function useUpload(accountId, folderId, onSuccess) {
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        setProgress(0);

        try {
            const MAX_SIMPLE = 4 * 1024 * 1024; // 4MB

            if (file.size <= MAX_SIMPLE) {
                await uploadFileSimple(accountId, folderId || 'root', file);
            } else {
                // Large File Upload
                const session = await createUploadSession(accountId, folderId || 'root', file.name, file.size);
                const uploadUrl = session.upload_url;
                const chunkSize = 320 * 1024 * 10; // 3.2MB

                let start = 0;
                while (start < file.size) {
                    const end = Math.min(start + chunkSize, file.size);
                    const chunk = file.slice(start, end);

                    await uploadChunkProxy(accountId, uploadUrl, chunk, start, end, file.size);

                    start = end;
                    const pct = Math.floor((start / file.size) * 100);
                    setProgress(pct);
                }
            }
            if (onSuccess) onSuccess();
        } catch (e) {
            console.error(e);
            alert(`Upload failed: ${e.message}`);
        } finally {
            setUploading(false);
            setProgress(0);
        }
    };

    return { upload, uploading, progress };
}
