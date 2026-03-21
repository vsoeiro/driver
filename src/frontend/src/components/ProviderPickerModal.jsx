import Modal from './Modal';
import ProviderIcon from './ProviderIcon';
import { useTranslation } from 'react-i18next';
import { useAccountsActions } from '../features/accounts/hooks/useAccountsData';

export default function ProviderPickerModal({ isOpen, onClose, onSelect }) {
    const { t } = useTranslation();
    const { linkAccount } = useAccountsActions();

    const providers = [
        { id: 'microsoft', label: 'OneDrive' },
        { id: 'google', label: 'Google Drive' },
        { id: 'dropbox', label: 'Dropbox' },
    ];

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={t('providerPicker.title')}>
            <div className="space-y-2">
                {providers.map((provider) => (
                    <button
                        key={provider.id}
                        onClick={() => {
                            onClose();
                            if (onSelect) {
                                onSelect(provider.id);
                                return;
                            }
                            linkAccount(provider.id);
                        }}
                        className="w-full flex items-center gap-3 px-3 py-3 rounded-md border hover:bg-accent text-left"
                    >
                        <ProviderIcon provider={provider.id} className="w-5 h-5" />
                        <span className="text-sm font-medium">{provider.label}</span>
                    </button>
                ))}
            </div>
        </Modal>
    );
}
