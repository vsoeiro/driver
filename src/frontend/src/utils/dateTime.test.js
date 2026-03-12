import { formatDateOnly, formatDateTime } from './dateTime';

describe('dateTime utils', () => {
    it('formats date time using the requested locale', () => {
        expect(formatDateTime('2026-03-10T14:15:00Z', 'en')).toBeTruthy();
        expect(formatDateTime('2026-03-10T14:15:00Z', 'pt-BR')).toBeTruthy();
    });

    it('formats only the date portion', () => {
        expect(formatDateOnly('2026-03-10T14:15:00Z', 'en')).toMatch(/03|10/);
    });

    it('returns dash when the value is invalid', () => {
        expect(formatDateTime('invalid-date', 'en')).toBe('-');
        expect(formatDateOnly(null, 'pt-BR')).toBe('-');
    });
});
