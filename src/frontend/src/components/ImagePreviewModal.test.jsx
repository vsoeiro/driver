import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const getDownloadContentUrlMock = vi.fn();

vi.mock('../services/drive', () => ({
    driveService: {
        getDownloadContentUrl: (...args) => getDownloadContentUrlMock(...args),
    },
}));

vi.mock('./Modal', () => ({
    default: ({ isOpen, title, onClose, children }) => (
        isOpen ? (
            <div role="dialog" aria-label={title}>
                <button type="button" onClick={onClose}>Close modal</button>
                {children}
            </div>
        ) : null
    ),
}));

import { renderWithProviders } from '../test/render';
import ImagePreviewModal from './ImagePreviewModal';

describe('ImagePreviewModal', () => {
    beforeEach(() => {
        getDownloadContentUrlMock.mockReset();
        getDownloadContentUrlMock.mockReturnValue('https://cdn.example/item-1');
    });

    it('renders nothing while closed', () => {
        renderWithProviders(
            <ImagePreviewModal
                isOpen={false}
                onClose={vi.fn()}
                accountId="acc-1"
                itemId="item-1"
                filename="cover.png"
            />,
        );

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('previews images, supports zoom actions and reports load errors', async () => {
        const user = userEvent.setup();
        renderWithProviders(
            <ImagePreviewModal
                isOpen
                onClose={vi.fn()}
                accountId="acc-1"
                itemId="item-1"
                filename="cover.png"
            />,
        );

        expect(getDownloadContentUrlMock).toHaveBeenCalledWith('acc-1', 'item-1', {
            autoResolveAccount: true,
        });
        expect(screen.getByText('Use + / - keys or Ctrl + wheel to zoom')).toBeInTheDocument();

        const image = screen.getByAltText('cover.png');
        fireEvent.load(image);

        expect(screen.getByText('100%')).toBeInTheDocument();

        await user.click(screen.getByTitle('Zoom in'));
        expect(screen.getByText('125%')).toBeInTheDocument();

        await user.click(screen.getByTitle('Zoom out'));
        expect(screen.getByText('100%')).toBeInTheDocument();

        fireEvent.keyDown(window, { key: '+' });
        expect(screen.getByText('125%')).toBeInTheDocument();

        fireEvent.keyDown(window, { key: '-' });
        expect(screen.getByText('100%')).toBeInTheDocument();

        fireEvent.wheel(image.parentElement, { ctrlKey: true, deltaY: -40 });
        expect(screen.getByText('110%')).toBeInTheDocument();

        fireEvent.error(image);
        expect(screen.getByText('Failed to load preview')).toBeInTheDocument();
    });

    it('renders pdf previews without zoom controls', () => {
        renderWithProviders(
            <ImagePreviewModal
                isOpen
                onClose={vi.fn()}
                accountId="acc-1"
                itemId="item-9"
                filename="manual.pdf"
            />,
        );

        expect(screen.getByText('Press Esc to close')).toBeInTheDocument();
        expect(screen.queryByTitle('Zoom in')).not.toBeInTheDocument();

        const frame = screen.getByTitle('manual.pdf');
        fireEvent.load(frame);
        fireEvent.keyDown(window, { key: '+' });
        expect(screen.queryByText('125%')).not.toBeInTheDocument();
    });
});
