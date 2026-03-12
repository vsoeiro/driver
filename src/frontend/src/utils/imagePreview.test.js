import { getFileExtension, isImageFileName, isPdfFileName, isPreviewableFileName } from './imagePreview';

describe('imagePreview utils', () => {
    it('extracts file extensions safely', () => {
        expect(getFileExtension('cover.CBZ')).toBe('cbz');
        expect(getFileExtension('no-extension')).toBe('');
    });

    it('identifies image, pdf and previewable files', () => {
        expect(isImageFileName('cover.webp')).toBe(true);
        expect(isPdfFileName('book.pdf')).toBe(true);
        expect(isPreviewableFileName('book.pdf')).toBe(true);
        expect(isPreviewableFileName('archive.cbz')).toBe(false);
    });
});
