vi.mock('./api', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        delete: vi.fn(),
        patch: vi.fn(),
        put: vi.fn(),
    },
}));

import api from './api';
import { metadataService } from './metadata';

describe('metadata service', () => {
    it('gets and mutates categories, attributes and item metadata', async () => {
        api.get.mockResolvedValue({ data: { categories: [] } });
        api.post.mockResolvedValue({ data: { ok: true } });
        api.patch.mockResolvedValue({ data: { ok: true } });
        api.delete.mockResolvedValue({});

        await metadataService.listCategories({ signal: 'signal' });
        await metadataService.createCategory('Docs', 'desc');
        await metadataService.createAttribute('cat-1', { name: 'Series', data_type: 'text' });
        await metadataService.updateAttribute('attr-1', { name: 'Series Title' });
        await metadataService.deleteAttribute('attr-1');
        await metadataService.getItemMetadata('acc-1', 'item-1');
        await metadataService.saveItemMetadata({ account_id: 'acc-1' });
        await metadataService.updateItemMetadataField('acc-1', 'item-1', 'attr-1', { value: 'Dylan' });
        await metadataService.deleteItemMetadata('acc-1', 'item-1');
        await metadataService.batchDeleteMetadata('acc-1', ['item-1']);
        await metadataService.getItemMetadataHistory('acc-1', 'item-1');
        await metadataService.undoMetadataBatch('batch-1');

        expect(api.get).toHaveBeenCalledWith('/metadata/categories', { signal: 'signal' });
        expect(api.post).toHaveBeenCalledWith('/metadata/categories', { name: 'Docs', description: 'desc' });
        expect(api.post).toHaveBeenCalledWith('/metadata/items/batch-delete', ['item-1'], {
            params: { account_id: 'acc-1' },
        });
    });

    it('handles rules, layouts, libraries and series summary', async () => {
        api.get.mockResolvedValue({ data: { rows: [] } });
        api.post.mockResolvedValue({ data: { ok: true } });
        api.patch.mockResolvedValue({ data: { ok: true } });
        api.put.mockResolvedValue({ data: { ok: true } });
        api.delete.mockResolvedValue({});

        await metadataService.listRules();
        await metadataService.createRule({ name: 'rule' });
        await metadataService.updateRule('rule-1', { name: 'updated' });
        await metadataService.deleteRule('rule-1');
        await metadataService.previewRule({ account_id: 'acc-1' });
        await metadataService.getCategoryStats();
        await metadataService.listFormLayouts();
        await metadataService.getFormLayout('cat-1');
        await metadataService.saveFormLayout('cat-1', { columns: 12 });
        await metadataService.getSeriesSummary('cat-1', { account_id: 'acc-1', filters: { source: 'ai' }, tags: ['x'] });
        await metadataService.listMetadataLibraries({ signal: 'signal' });
        await metadataService.activateMetadataLibrary('lib-1');
        await metadataService.deactivateMetadataLibrary('lib-1');

        expect(api.get).toHaveBeenCalledWith('/metadata/categories/cat-1/series-summary?account_id=acc-1&filters=%7B%22source%22%3A%22ai%22%7D&tags=x');
        expect(api.get).toHaveBeenCalledWith('/metadata/libraries', { signal: 'signal' });
        expect(api.put).toHaveBeenCalledWith('/metadata/layouts/cat-1', { columns: 12 });
        expect(api.post).toHaveBeenCalledWith('/metadata/libraries/lib-1/deactivate');
    });
});
