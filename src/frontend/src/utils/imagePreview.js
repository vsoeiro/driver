const IMAGE_EXTENSIONS = new Set([
    'jpg',
    'jpeg',
    'png',
    'gif',
    'webp',
    'bmp',
    'avif',
    'svg',
    'tif',
    'tiff',
    'ico',
    'jfif',
    'heic',
    'heif',
]);
const PDF_EXTENSIONS = new Set(['pdf']);

export const getFileExtension = (filename = '') => {
    const dotIndex = String(filename).lastIndexOf('.');
    if (dotIndex < 0) return '';
    return String(filename).slice(dotIndex + 1).toLowerCase();
};

export const isImageFileName = (filename = '') => IMAGE_EXTENSIONS.has(getFileExtension(filename));
export const isPdfFileName = (filename = '') => PDF_EXTENSIONS.has(getFileExtension(filename));
export const isPreviewableFileName = (filename = '') => isImageFileName(filename) || isPdfFileName(filename);
