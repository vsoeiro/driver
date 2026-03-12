import { act, renderHook } from '@testing-library/react';

const uploadFileBackgroundMock = vi.fn();

vi.mock('../services/jobs', () => ({
    jobsService: {
        uploadFileBackground: (...args) => uploadFileBackgroundMock(...args),
    },
}));

import { useUpload } from './useUpload';

describe('useUpload', () => {
    let consoleErrorSpy;

    beforeEach(() => {
        uploadFileBackgroundMock.mockReset();
        consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
        consoleErrorSpy.mockRestore();
    });

    it('ignores empty inputs', async () => {
        const onSuccess = vi.fn();
        const { result } = renderHook(() => useUpload('acc-1', 'folder-1', onSuccess));

        await act(async () => {
            await result.current.upload([]);
        });

        expect(uploadFileBackgroundMock).not.toHaveBeenCalled();
        expect(onSuccess).not.toHaveBeenCalled();
    });

    it('uploads a single file and falls back to the root folder when needed', async () => {
        const file = new File(['hello'], 'cover.png', { type: 'image/png' });
        uploadFileBackgroundMock.mockResolvedValue(undefined);
        const onSuccess = vi.fn();

        const { result } = renderHook(() => useUpload('acc-1', '', onSuccess));

        await act(async () => {
            await result.current.upload(file);
        });

        expect(uploadFileBackgroundMock).toHaveBeenCalledWith('acc-1', 'root', file, expect.any(Function));
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(result.current.uploading).toBe(false);
        expect(result.current.progress).toBe(0);
    });

    it('reports partial failures for batch uploads', async () => {
        const fileA = new File(['a'], 'a.txt', { type: 'text/plain' });
        const fileB = new File(['b'], 'b.txt', { type: 'text/plain' });
        const onSuccess = vi.fn();
        const onError = vi.fn();

        uploadFileBackgroundMock
            .mockImplementationOnce(async (_accountId, _folderId, _file, onProgress) => {
                onProgress(25);
                onProgress(100);
            })
            .mockRejectedValueOnce(new Error('boom'));

        const { result } = renderHook(() => useUpload('acc-1', 'folder-9', onSuccess, onError));

        await act(async () => {
            await result.current.upload([fileA, fileB]);
        });

        expect(uploadFileBackgroundMock).toHaveBeenNthCalledWith(1, 'acc-1', 'folder-9', fileA, expect.any(Function));
        expect(uploadFileBackgroundMock).toHaveBeenNthCalledWith(2, 'acc-1', 'folder-9', fileB, expect.any(Function));
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onError).toHaveBeenCalledWith(1);
        expect(consoleErrorSpy).toHaveBeenCalled();
        expect(result.current.uploading).toBe(false);
        expect(result.current.progress).toBe(0);
    });
});
