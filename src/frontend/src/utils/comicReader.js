export const COMIC_READER_PLUGIN_KEY = 'comics_core';
export const COMIC_READER_SUPPORTED_EXTENSIONS = new Set([
    'cbz',
    'cbr',
    'cb7',
    'cbt',
    'zip',
    'rar',
    '7z',
    'tar',
    'cbw',
]);
export const COMIC_READER_LIBRARY_ONLY_EXTENSIONS = new Set(['pdf', 'epub']);

export const getComicFileExtension = (filename = '') => {
    const normalized = String(filename || '').trim().toLowerCase();
    const dotIndex = normalized.lastIndexOf('.');
    return dotIndex >= 0 ? normalized.slice(dotIndex + 1) : '';
};

export const isComicReaderKnownExtension = (extension) => (
    COMIC_READER_SUPPORTED_EXTENSIONS.has(extension)
    || COMIC_READER_LIBRARY_ONLY_EXTENSIONS.has(extension)
);

export const getComicReaderEligibility = (item, categoryPluginKey) => {
    const extension = getComicFileExtension(item?.name || item?.extension || '');
    const isFile = item?.item_type === 'file';
    const hasComicsMetadata = categoryPluginKey === COMIC_READER_PLUGIN_KEY;
    const isSupported = COMIC_READER_SUPPORTED_EXTENSIONS.has(extension);
    const isLibraryOnly = COMIC_READER_LIBRARY_ONLY_EXTENSIONS.has(extension);

    return {
        extension,
        isFile,
        hasComicsMetadata,
        isSupported,
        isLibraryOnly,
        canRead: isFile && hasComicsMetadata && isSupported,
    };
};

export const getReaderSpreadPageIndexes = (pageIndex, pageCount, singlePageMode) => {
    if (pageCount <= 0) return [];
    const normalizedIndex = Math.max(0, Math.min(pageIndex, pageCount - 1));
    if (singlePageMode || normalizedIndex === 0) {
        return [normalizedIndex];
    }

    const spreadStart = 1 + Math.floor((normalizedIndex - 1) / 2) * 2;
    const indexes = [spreadStart];
    if (spreadStart + 1 < pageCount) {
        indexes.push(spreadStart + 1);
    }
    return indexes;
};

export const getNextReaderPageIndex = (pageIndex, pageCount, singlePageMode) => {
    if (pageCount <= 1) return 0;
    if (singlePageMode) {
        return Math.min(pageCount - 1, pageIndex + 1);
    }
    if (pageIndex === 0) {
        return 1;
    }
    const visibleIndexes = getReaderSpreadPageIndexes(pageIndex, pageCount, false);
    const nextIndex = visibleIndexes[visibleIndexes.length - 1] + 1;
    return nextIndex < pageCount ? nextIndex : pageIndex;
};

export const getPreviousReaderPageIndex = (pageIndex, _pageCount, singlePageMode) => {
    if (pageIndex <= 0) return 0;
    if (singlePageMode) {
        return Math.max(0, pageIndex - 1);
    }
    if (pageIndex <= 2) {
        return 0;
    }
    const visibleIndexes = getReaderSpreadPageIndexes(pageIndex, Number.MAX_SAFE_INTEGER, false);
    return Math.max(1, visibleIndexes[0] - 2);
};
