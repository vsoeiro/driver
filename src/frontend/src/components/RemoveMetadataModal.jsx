import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { File, Loader2 } from 'lucide-react';
import { useMetadataActions } from '../features/metadata/hooks/useMetadataData';
import { useJobsActions } from '../features/jobs/hooks/useJobsData';
import Modal from './Modal';

const RemoveMetadataModal = ({ isOpen, onClose, selectedItems, onSuccess, showToast }) => {
    const { t } = useTranslation();
    const { batchDeleteMetadata } = useMetadataActions();
    const { removeMetadataRecursive } = useJobsActions();
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
                    promises.push(batchDeleteMetadata(accountId, itemIds));
                }
            }

            for (const folder of folders) {
                promises.push(
                    removeMetadataRecursive(folder.account_id, folder.path)
                );
            }

            await Promise.all(promises);

            const parts = [];
            if (directDeleteItems.length > 0) parts.push(t('removeMetadata.itemsCleared', { count: directDeleteItems.length }));
            if (folders.length > 0) parts.push(t('removeMetadata.foldersQueued', { count: folders.length }));
            showToast(`${parts.join(', ')}.`, 'success');

            onSuccess();
            onClose();
        } catch (error) {
            showToast(`${t('removeMetadata.failed')}: ${error.message}`, 'error');
        } finally {
            setRemoving(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={t('removeMetadata.title', { count: selectedItems.length })}>
            <div className="space-y-4">
                {!hasAnything ? (
                    <p className="text-sm text-muted-foreground">{t('removeMetadata.none')}</p>
                ) : (
                    <>
                        {filesWithMeta.length > 0 && (
                            <div>
                                <p className="text-sm font-medium mb-2">{t('removeMetadata.files', { count: filesWithMeta.length })}</p>
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
                            <p className="status-badge status-badge-warning text-sm">
                                {t('removeMetadata.recursiveWarning', { count: folders.length })}
                            </p>
                        )}

                        <p className="text-sm text-muted-foreground">
                            {t('removeMetadata.warning')}
                        </p>
                    </>
                )}

                <div className="flex justify-end gap-2 pt-2">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-md hover:bg-accent">{t('common.cancel')}</button>
                    <button
                        onClick={handleRemove}
                        disabled={removing || !hasAnything}
                        className="px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 disabled:opacity-50 flex items-center gap-2"
                    >
                        {removing && <Loader2 className="animate-spin" size={14} />}
                        {t('removeMetadata.confirm')}
                    </button>
                </div>
            </div>
        </Modal>
    );
};

export default RemoveMetadataModal;
