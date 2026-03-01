import { useEffect, useMemo, useState } from 'react';
import { Loader2, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Modal from './Modal';
import { driveService } from '../services/drive';
import { isPdfFileName } from '../utils/imagePreview';

export default function ImagePreviewModal({
    isOpen,
    onClose,
    accountId,
    itemId,
    filename,
}) {
    const { t } = useTranslation();
    const [zoomLevel, setZoomLevel] = useState(1);
    const [loading, setLoading] = useState(true);
    const [hasError, setHasError] = useState(false);
    const isPdf = isPdfFileName(filename);

    const imageUrl = useMemo(() => {
        if (!accountId || !itemId) return '';
        return driveService.getDownloadContentUrl(String(accountId), String(itemId), {
            autoResolveAccount: true,
        });
    }, [accountId, itemId]);
    const pdfUrl = useMemo(() => {
        if (!imageUrl) return '';
        return `${imageUrl}#zoom=page-fit`;
    }, [imageUrl]);

    useEffect(() => {
        if (!isOpen) return;
        setZoomLevel(1);
        setLoading(true);
        setHasError(false);
    }, [isOpen, accountId, itemId]);

    useEffect(() => {
        if (!isOpen) return undefined;

        const onKeyDown = (event) => {
            if (isPdf) return;
            if (event.key === '+' || event.key === '=') {
                setZoomLevel((prev) => Math.min(4, Number((prev + 0.25).toFixed(2))));
            }
            if (event.key === '-') {
                setZoomLevel((prev) => Math.max(0.5, Number((prev - 0.25).toFixed(2))));
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [isOpen, isPdf]);

    if (!isOpen) return null;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={filename || t('imagePreview.title')}
            maxWidthClass="max-w-6xl"
            bodyClassName="p-0"
        >
            <div className="flex items-center justify-between gap-2 border-b border-border/70 px-4 py-2">
                <div className="text-xs text-muted-foreground">
                    {isPdf ? (
                        <>{t('imagePreview.useEsc')}</>
                    ) : (
                        <>{t('imagePreview.useZoomKeys')}</>
                    )}
                </div>
                {!isPdf && (
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            className="rounded border border-border/70 px-2 py-1 hover:bg-accent disabled:opacity-50"
                            onClick={() => setZoomLevel((prev) => Math.max(0.5, Number((prev - 0.25).toFixed(2))))}
                            disabled={hasError}
                            title={t('imagePreview.zoomOut')}
                        >
                            <ZoomOut size={14} />
                        </button>
                        <div className="min-w-12 text-center text-xs tabular-nums">
                            {Math.round(zoomLevel * 100)}%
                        </div>
                        <button
                            type="button"
                            className="rounded border border-border/70 px-2 py-1 hover:bg-accent disabled:opacity-50"
                            onClick={() => setZoomLevel((prev) => Math.min(4, Number((prev + 0.25).toFixed(2))))}
                            disabled={hasError}
                            title={t('imagePreview.zoomIn')}
                        >
                            <ZoomIn size={14} />
                        </button>
                    </div>
                )}
            </div>

            <div
                className="relative flex h-[72vh] w-full items-center justify-center overflow-auto bg-black/90"
                onWheel={(event) => {
                    if (isPdf) return;
                    if (!event.ctrlKey) return;
                    event.preventDefault();
                    setZoomLevel((prev) => {
                        const delta = event.deltaY < 0 ? 0.1 : -0.1;
                        return Math.max(0.5, Math.min(4, Number((prev + delta).toFixed(2))));
                    });
                }}
            >
                {loading && !hasError && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center">
                        <Loader2 className="animate-spin text-white" size={28} />
                    </div>
                )}
                {!imageUrl || hasError ? (
                    <div className="px-4 text-sm text-white/85">
                        {t('imagePreview.failed')}
                    </div>
                ) : isPdf ? (
                    <iframe
                        src={pdfUrl}
                        title={filename || t('imagePreview.pdfTitle')}
                        className="h-full w-full border-0 bg-white"
                        onLoad={() => {
                            setLoading(false);
                            setHasError(false);
                        }}
                        onError={() => {
                            setLoading(false);
                            setHasError(true);
                        }}
                    />
                ) : (
                    <img
                        src={imageUrl}
                        alt={filename || t('imagePreview.title')}
                        className="h-auto max-h-full w-auto max-w-full rounded shadow-2xl"
                        style={{ transform: `scale(${zoomLevel})`, transformOrigin: 'center center' }}
                        onLoad={() => {
                            setLoading(false);
                            setHasError(false);
                        }}
                        onError={() => {
                            setLoading(false);
                            setHasError(true);
                        }}
                    />
                )}
            </div>
        </Modal>
    );
}
