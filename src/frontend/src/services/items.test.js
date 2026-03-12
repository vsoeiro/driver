vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

import api from './api';
import { itemsService } from './items';

describe('items service', () => {
    it('serializes list params into query string', async () => {
        api.get.mockResolvedValue({ data: { items: [] } });

        await itemsService.listItems(
            {
                page: 2,
                page_size: 10,
                q: 'Dylan',
                extensions: ['cbz', 'cbr'],
                metadata: { source: 'ai' },
            },
            { signal: 'signal' },
        );

        expect(api.get).toHaveBeenCalledWith(
            '/items?page=2&page_size=10&q=Dylan&extensions=cbz&extensions=cbr&metadata=%7B%22source%22%3A%22ai%22%7D',
            { signal: 'signal' },
        );
    });

    it('builds similar report queries and metadata batch requests', async () => {
        api.get.mockResolvedValue({ data: { groups: [] } });
        api.post.mockResolvedValue({ data: { updated: 2 } });

        await itemsService.getSimilarReport({ scope: 'account', extensions: ['cbz'] });
        await expect(itemsService.batchUpdateMetadata('acc-1', ['item-1'], 'cat-1', { title: 'Dylan' })).resolves.toEqual({ updated: 2 });

        expect(api.get).toHaveBeenCalledWith('/items/similar-report?scope=account&extensions=cbz');
        expect(api.post).toHaveBeenCalledWith('/items/metadata/batch', {
            account_id: 'acc-1',
            item_ids: ['item-1'],
            category_id: 'cat-1',
            values: { title: 'Dylan' },
        });
    });
});
