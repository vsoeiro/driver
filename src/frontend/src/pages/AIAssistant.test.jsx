import { screen } from '@testing-library/react';

vi.mock('../components/AIAssistantWorkspace', () => ({
    default: ({ showPageHeader }) => <div>Workspace header {String(showPageHeader)}</div>,
}));

import { renderWithProviders } from '../test/render';
import AIAssistant from './AIAssistant';

describe('AIAssistant page', () => {
    it('renders the assistant workspace with the page header enabled', () => {
        renderWithProviders(<AIAssistant />);

        expect(screen.getByText('Workspace header true')).toBeInTheDocument();
    });
});
