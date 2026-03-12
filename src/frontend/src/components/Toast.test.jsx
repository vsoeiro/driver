import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import '../i18n';
import Toast from './Toast';

describe('Toast', () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    it('formats nested messages and closes manually', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();

        render(
            <Toast
                id="toast-1"
                type="warning"
                message={[
                    { msg: 'Bad value', loc: ['body', 'field'] },
                    { detail: 'Something happened' },
                ]}
                onClose={onClose}
                duration={10000}
            />,
        );

        expect(screen.getByText(/field: Bad value/i)).toBeInTheDocument();
        expect(screen.getByText(/Something happened/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /close toast/i }));

        expect(onClose).toHaveBeenCalledWith('toast-1');
    });

    it('auto closes after the configured duration and stringifies unknown objects', async () => {
        vi.useFakeTimers();
        const onClose = vi.fn();

        render(
            <Toast
                id="toast-2"
                type="error"
                message={{ foo: 'bar' }}
                onClose={onClose}
                duration={1000}
            />,
        );

        expect(screen.getByText('{"foo":"bar"}')).toBeInTheDocument();

        await act(async () => {
            vi.advanceTimersByTime(1000);
        });

        expect(onClose).toHaveBeenCalledWith('toast-2');
    });
});
