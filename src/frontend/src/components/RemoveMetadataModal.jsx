import { useState } from 'react';
import { metadataService } from '../services/metadata';
import { jobsService } from '../services/jobs';
import { File, Loader2 } from 'lucide-react';
import Modal from './Modal';

const RemoveMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
    const [removing, setRemoving] = useState(false);

    const folders = selectedItems.filter(i => i.item_type === 'folder');
    const filesWithMeta = selectedItems.filter(i => i.item_type !== 'folder' && i.metadata);
    const foldersWithMeta = folders.filter(i => i.metadata);
    const hasAnything = filesWithMeta.length > 0 || folders.length > 0;

    const handleRemove = async () => {
        setRemoving(true);
        try {
            const promises = [];

            const directDeleteItems = [...filesWithMeta, ...foldersWithMeta];
            if (directDeleteItems.length > 0) {
                const byAccount = {};
                for (const item of directDeleteItems) {
                    if (!byAccount[item.account_id]) byAccount[item.account_id] = [];
                    byAccount[item.account_id].push(item.item_id);
                }
                for (const [accountId, itemIds] of Object.entries(byAccount)) {
                    promises.push(metadataService.batchDeleteMetadata(accountId, itemIds));
                }
            }

            for (const folder of folders) {
                promises.push(
                    jobsService.removeMetadataRecursive(folder.account_id, folder.path)
                );
            }

            await Promise.all(promises);

            const parts = [];
            if (directDeleteItems.length > 0) parts.push(`${directDeleteItems.length} item(s) cleared`);
            if (folders.length > 0) parts.push(`${folders.length} folder(s) queued for recursive removal`);
            showToast(parts.join(', ') + '.', 'success');

            onSuccess();
            onClose();
        } catch (error) {
            showToast('Failed to remove metadata: ' + error.message, 'error');
        } finally {
            setRemoving(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={`Remove Metadata from ${selectedItems.length} item${selectedItems.length > 1 ? 's' : ''}`}>
            <div className="space-y-4">
                {!hasAnything ? (
                    <p className="text-sm text-muted-foreground">None of the selected items have metadata to remove.</p>
                ) : (
                    <>
                        {filesWithMeta.length > 0 && (
                            <div>
                                <p className="text-sm font-medium mb-2">Files ({filesWithMeta.length})</p>
                                <div className="border rounded-md divide-y max-h-40 overflow-y-auto">
                                    {filesWithMeta.map(item => (
                                        <div key={item.id} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                                            <File size={14} className="text-gray-400 shrink-0" />
                                            <span className="truncate">{item.name}</span>
                                            <span className="ml-auto text-xs text-muted-foreground shrink-0">
                                                {item.metadata?.category_name}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {folders.length > 0 && (
                            <p className="text-sm text-amber-600 font-medium">
                                {folders.length} folder(s) will have metadata removed recursively.
                            </p>
                        )}

                        <p className="text-sm text-muted-foreground">
                            This action cannot be undone. Metadata values will be permanently deleted.
                        </p>
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">Cancel</button>
                    <button
                        onClick={handleRemove}
                        disabled={removing || !hasAnything}
                        className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {removing && <Loader2 className="animate-spin" size={14} />}
                        Yes, Remove Metadata
                    </button>
                </div>
            </div>
        </Modal>
    );
};

export default RemoveMetadataModal;
