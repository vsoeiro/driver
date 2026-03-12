import userEvent from '@testing-library/user-event';
import { render, screen } from '@testing-library/react';

import '../i18n';
import { ToastProvider, useToast } from './ToastContext';

function ToastConsumer() {
    const { showToast } = useToast();
    return (
        <button type="button" onClick={() => showToast('Saved', 'success', 10000)}>
            Notify
        </button>
    );
}

describe('ToastContext', () => {
    it('renders toast notifications from the provider', async () => {
        const user = userEvent.setup();

        render(
            <ToastProvider>
                <ToastConsumer />
            </ToastProvider>,
        );

        await user.click(screen.getByRole('button', { name: /notify/i }));

        expect(screen.getByText('Saved')).toBeInTheDocument();
    });

    it('throws when the hook is used outside the provider', () => {
        function BrokenConsumer() {
            useToast();
            return null;
        }

        expect(() => render(<BrokenConsumer />)).toThrow('useToast must be used within a ToastProvider');
    });
});
