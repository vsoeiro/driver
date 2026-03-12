import { cn } from './utils';

describe('lib utils', () => {
    it('merges class names with tailwind conflict resolution', () => {
        expect(cn('px-2', false, 'px-4', 'text-sm')).toBe('px-4 text-sm');
    });
});
