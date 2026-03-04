import { useTranslation } from 'react-i18next';
import Modal from './Modal';

export default function ConfirmDialog({
    isOpen,
    title,
    description,
    confirmLabel,
    cancelLabel,
    onConfirm,
    onCancel,
    loading = false,
    tone = 'danger',
}) {
    const { t } = useTranslation();
    const confirmClass = tone === 'danger' ? 'btn-minimal-danger' : 'btn-minimal-primary';

    return (
        <Modal isOpen={isOpen} onClose={onCancel} title={title} maxWidthClass="max-w-md">
            <div className="space-y-4">
                <p className="text-sm text-muted-foreground">{description}</p>
                <div className="flex justify-end gap-2">
                    <button
                        type="button"
                        onClick={onCancel}
                        disabled={loading}
                        className="btn-minimal"
                    >
                        {cancelLabel || t('common.cancel')}
                    </button>
                    <button
                        type="button"
                        onClick={onConfirm}
                        disabled={loading}
                        className={confirmClass}
                    >
                        {confirmLabel || 'Confirm'}
                    </button>
                </div>
            </div>
        </Modal>
    );
}
