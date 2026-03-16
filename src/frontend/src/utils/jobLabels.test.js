import { formatJobStatus, formatJobType } from './jobLabels';

describe('jobLabels utils', () => {
    it('formats job statuses with and without translator', () => {
        const t = (key) => ({ 'jobStatus.PENDING': 'Pending translated', 'jobStatus.unknown': 'Unknown translated' }[key] || key);

        expect(formatJobStatus('PENDING', t)).toBe('Pending translated');
        expect(formatJobStatus('CUSTOM_STATUS')).toBe('Custom Status');
        expect(formatJobStatus('', t)).toBe('Unknown translated');
    });

    it('formats job types with translation fallback', () => {
        const t = (key) => ({
            'jobType.sync_items': 'Sync items translated',
            'jobType.extract_zip_contents': 'Extract ZIP translated',
        }[key] || key);

        expect(formatJobType('sync_items', t)).toBe('Sync items translated');
        expect(formatJobType('extract_zip_contents', t)).toBe('Extract ZIP translated');
        expect(formatJobType('extract_book_assets')).toBe('Extract Book Assets');
        expect(formatJobType(null)).toBe('Unknown');
    });
});
