import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, BookOpen, ChevronLeft, ChevronRight, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import Modal from './Modal';
import { useDriveActions } from '../features/drive/hooks/useDriveData';
import {
    getNextReaderPageIndex,
    getPreviousReaderPageIndex,
    getReaderSpreadPageIndexes,
} from '../utils/comicReader';

const MOBILE_READER_MEDIA_QUERY = '(max-width: 1023px)';

const getReaderErrorMessage = (error, t) => (
    error?.response?.data?.detail
    || error?.message
    || t('comicReader.failedLoad')
);

export default function ComicReaderModal({
    isOpen,
    onClose,
    accountId,
    itemId,
    filename,
}) {
    const { t } = useTranslation();
    const { createComicReaderSession, getComicReaderPageUrl } = useDriveActions();
    const [readerSession, setReaderSession] = useState(null);
    const [currentPageIndex, setCurrentPageIndex] = useState(0);
    const [loadingSession, setLoadingSession] = useState(false);
    const [loadingPages, setLoadingPages] = useState(false);
    const [error, setError] = useState('');
    const [isSinglePageMode, setIsSinglePageMode] = useState(() => (
        typeof window !== 'undefined'
        && typeof window.matchMedia === 'function'
        && window.matchMedia(MOBILE_READER_MEDIA_QUERY).matches
    ));
    const [visiblePageUrls, setVisiblePageUrls] = useState({});
    const pageUrlsRef = useRef(new Map());
    const requestIdRef = useRef(0);
    const sessionRetryCountRef = useRef(0);

    const releasePageUrls = () => {
        pageUrlsRef.current.forEach((url) => {
            window.URL.revokeObjectURL(url);
        });
        pageUrlsRef.current.clear();
        setVisiblePageUrls({});
    };

    useEffect(() => () => {
        releasePageUrls();
    }, []);

    useEffect(() => {
        if (!isOpen) {
            setReaderSession(null);
            setCurrentPageIndex(0);
            setLoadingSession(false);
            setLoadingPages(false);
            setError('');
            sessionRetryCountRef.current = 0;
            releasePageUrls();
        }
    }, [isOpen]);

    useEffect(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
        const mediaQuery = window.matchMedia(MOBILE_READER_MEDIA_QUERY);
        const updateMode = () => setIsSinglePageMode(Boolean(mediaQuery.matches));
        updateMode();
        mediaQuery.addEventListener?.('change', updateMode);
        mediaQuery.addListener?.(updateMode);
        return () => {
            mediaQuery.removeEventListener?.('change', updateMode);
            mediaQuery.removeListener?.(updateMode);
        };
    }, []);

    useEffect(() => {
        if (!isOpen || !accountId || !itemId) return undefined;

        let cancelled = false;
        requestIdRef.current += 1;
        sessionRetryCountRef.current = 0;
        releasePageUrls();
        setReaderSession(null);
        setCurrentPageIndex(0);
        setError('');
        setLoadingPages(false);
        setLoadingSession(true);

        (async () => {
            try {
                const nextSession = await createComicReaderSession(accountId, itemId);
                if (cancelled) return;
                setReaderSession(nextSession);
            } catch (nextError) {
                if (cancelled) return;
                setError(getReaderErrorMessage(nextError, t));
            } finally {
                if (!cancelled) {
                    setLoadingSession(false);
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, [accountId, createComicReaderSession, isOpen, itemId, t]);

    const visiblePageIndexes = useMemo(() => (
        readerSession
            ? getReaderSpreadPageIndexes(
                currentPageIndex,
                readerSession.page_count,
                isSinglePageMode,
            )
            : []
    ), [currentPageIndex, isSinglePageMode, readerSession]);

    const canGoPrevious = currentPageIndex > 0;
    const canGoNext = Boolean(
        readerSession
        && getNextReaderPageIndex(currentPageIndex, readerSession.page_count, isSinglePageMode) !== currentPageIndex
    );

    const currentCounterLabel = visiblePageIndexes.length > 0
        ? visiblePageIndexes.map((pageIndex) => pageIndex + 1).join('-')
        : '0';

    const fetchPageBlobUrl = async (sessionManifest, pageIndex) => {
        const response = await fetch(
            getComicReaderPageUrl(accountId, sessionManifest.session_id, pageIndex),
            { credentials: 'same-origin' },
        );
        if (!response.ok) {
            const fetchError = new Error(t('comicReader.failedLoad'));
            fetchError.status = response.status;
            throw fetchError;
        }
        const blob = await response.blob();
        const objectUrl = window.URL.createObjectURL(blob);
        pageUrlsRef.current.set(pageIndex, objectUrl);
        return objectUrl;
    };

    const ensurePageUrls = async (sessionManifest, pageIndexes, allowSessionRetry = true) => {
        const missingIndexes = pageIndexes.filter((pageIndex) => !pageUrlsRef.current.has(pageIndex));
        if (missingIndexes.length === 0) {
            return pageIndexes.reduce((acc, pageIndex) => {
                acc[pageIndex] = pageUrlsRef.current.get(pageIndex);
                return acc;
            }, {});
        }

        try {
            await Promise.all(missingIndexes.map((pageIndex) => fetchPageBlobUrl(sessionManifest, pageIndex)));
        } catch (fetchError) {
            if (fetchError?.status === 404 && allowSessionRetry && sessionRetryCountRef.current < 1) {
                sessionRetryCountRef.current += 1;
                const refreshedSession = await createComicReaderSession(accountId, itemId);
                setReaderSession(refreshedSession);
                return ensurePageUrls(refreshedSession, pageIndexes, false);
            }
            throw fetchError;
        }

        return pageIndexes.reduce((acc, pageIndex) => {
            acc[pageIndex] = pageUrlsRef.current.get(pageIndex);
            return acc;
        }, {});
    };

    useEffect(() => {
        if (!isOpen || !readerSession || visiblePageIndexes.length === 0) return undefined;

        const activeRequestId = ++requestIdRef.current;
        let cancelled = false;
        setLoadingPages(true);
        setError('');

        (async () => {
            try {
                const nextVisibleUrls = await ensurePageUrls(readerSession, visiblePageIndexes, true);
                if (cancelled || activeRequestId !== requestIdRef.current) return;
                setVisiblePageUrls(nextVisibleUrls);
            } catch (loadError) {
                if (cancelled || activeRequestId !== requestIdRef.current) return;
                setError(getReaderErrorMessage(loadError, t));
            } finally {
                if (!cancelled && activeRequestId === requestIdRef.current) {
                    setLoadingPages(false);
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    }, [accountId, createComicReaderSession, getComicReaderPageUrl, isOpen, itemId, readerSession, t, visiblePageIndexes]);

    useEffect(() => {
        if (!readerSession || visiblePageIndexes.length === 0) return;
        const nextPageIndex = getNextReaderPageIndex(
            currentPageIndex,
            readerSession.page_count,
            isSinglePageMode,
        );
        const previousPageIndex = getPreviousReaderPageIndex(
            currentPageIndex,
            readerSession.page_count,
            isSinglePageMode,
        );
        const prefetchIndexes = new Set();
        if (nextPageIndex !== currentPageIndex) {
            getReaderSpreadPageIndexes(nextPageIndex, readerSession.page_count, isSinglePageMode)
                .forEach((pageIndex) => prefetchIndexes.add(pageIndex));
        }
        if (previousPageIndex !== currentPageIndex) {
            getReaderSpreadPageIndexes(previousPageIndex, readerSession.page_count, isSinglePageMode)
                .forEach((pageIndex) => prefetchIndexes.add(pageIndex));
        }
        visiblePageIndexes.forEach((pageIndex) => prefetchIndexes.delete(pageIndex));
        if (prefetchIndexes.size === 0) return;
        void ensurePageUrls(readerSession, Array.from(prefetchIndexes), false).catch(() => {});
    }, [currentPageIndex, isSinglePageMode, readerSession, visiblePageIndexes]);

    useEffect(() => {
        if (!isOpen || !readerSession) return undefined;
        const onKeyDown = (event) => {
            if (event.key === 'ArrowRight' && canGoNext) {
                event.preventDefault();
                setCurrentPageIndex((previous) => getNextReaderPageIndex(previous, readerSession.page_count, isSinglePageMode));
            }
            if (event.key === 'ArrowLeft' && canGoPrevious) {
                event.preventDefault();
                setCurrentPageIndex((previous) => getPreviousReaderPageIndex(previous, readerSession.page_count, isSinglePageMode));
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [canGoNext, canGoPrevious, isOpen, isSinglePageMode, readerSession]);

    if (!isOpen) return null;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={filename || readerSession?.item_name || t('comicReader.title')}
            maxWidthClass="max-w-[92rem]"
            bodyClassName="p-0"
        >
            <div className="flex items-center justify-between gap-3 border-b border-border/70 bg-card px-4 py-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <BookOpen size={16} />
                        <span>{t('comicReader.readingMode')}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                        {readerSession
                            ? t('comicReader.pageCounter', {
                                current: currentCounterLabel,
                                total: readerSession.page_count,
                            })
                            : t('comicReader.preparing')}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        className="rounded-md border border-border/70 px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
                        onClick={() => setCurrentPageIndex((previous) => getPreviousReaderPageIndex(previous, readerSession?.page_count || 0, isSinglePageMode))}
                        disabled={!canGoPrevious || loadingSession}
                    >
                        <span className="inline-flex items-center gap-1">
                            <ChevronLeft size={16} />
                            {t('comicReader.previous')}
                        </span>
                    </button>
                    <button
                        type="button"
                        className="rounded-md border border-border/70 px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
                        onClick={() => setCurrentPageIndex((previous) => getNextReaderPageIndex(previous, readerSession?.page_count || 0, isSinglePageMode))}
                        disabled={!canGoNext || loadingSession}
                    >
                        <span className="inline-flex items-center gap-1">
                            {t('comicReader.next')}
                            <ChevronRight size={16} />
                        </span>
                    </button>
                </div>
            </div>

            <div className="relative h-[78vh] overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.08),_transparent_32%),linear-gradient(180deg,_#141414,_#060606)]">
                {(loadingSession || loadingPages) && !error && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/20">
                        <Loader2 className="animate-spin text-white/90" size={30} />
                    </div>
                )}

                {error ? (
                    <div className="flex h-full items-center justify-center px-6">
                        <div className="max-w-md rounded-xl border border-white/10 bg-white/5 p-5 text-center text-white shadow-2xl backdrop-blur">
                            <div className="mb-3 flex justify-center">
                                <AlertCircle size={28} />
                            </div>
                            <div className="text-base font-semibold">{t('comicReader.failedTitle')}</div>
                            <p className="mt-2 text-sm text-white/75">{error}</p>
                            <button
                                type="button"
                                onClick={async () => {
                                    setError('');
                                    setLoadingSession(true);
                                    sessionRetryCountRef.current = 0;
                                    try {
                                        const nextSession = await createComicReaderSession(accountId, itemId);
                                        setReaderSession(nextSession);
                                    } catch (retryError) {
                                        setError(getReaderErrorMessage(retryError, t));
                                    } finally {
                                        setLoadingSession(false);
                                    }
                                }}
                                className="mt-4 inline-flex items-center gap-2 rounded-md border border-white/15 px-3 py-2 text-sm hover:bg-white/10"
                            >
                                <RefreshCw size={14} />
                                {t('comicReader.retry')}
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="flex h-full items-center justify-center overflow-auto px-4 py-8 sm:px-8 lg:px-12">
                        <div
                            className={`grid w-full max-w-6xl gap-6 ${visiblePageIndexes.length > 1 ? 'lg:grid-cols-2' : 'grid-cols-1'}`}
                            style={{ gridTemplateColumns: visiblePageIndexes.length > 1 ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)' }}
                        >
                            {visiblePageIndexes.map((pageIndex) => (
                                <div
                                    key={pageIndex}
                                    className="relative flex min-h-[24rem] items-center justify-center rounded-[1.5rem] border border-white/10 bg-[#f5f0e8] p-4 shadow-[0_24px_60px_rgba(0,0,0,0.45)]"
                                >
                                    {visiblePageUrls[pageIndex] ? (
                                        <img
                                            src={visiblePageUrls[pageIndex]}
                                            alt={t('comicReader.pageAlt', {
                                                name: filename || readerSession?.item_name || '',
                                                page: pageIndex + 1,
                                            })}
                                            className="max-h-[68vh] w-auto max-w-full rounded-md object-contain shadow-[0_14px_30px_rgba(0,0,0,0.18)]"
                                        />
                                    ) : (
                                        <Loader2 className="animate-spin text-slate-500" size={26} />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </Modal>
    );
}
