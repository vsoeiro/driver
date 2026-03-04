import { X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

let modalStack = [];

export default function Modal({
    isOpen,
    onClose,
    title,
    children,
    maxWidthClass = 'max-w-md',
    bodyClassName = '',
}) {
    const { t } = useTranslation();
    const modalId = useMemo(() => `modal_${Math.random().toString(36).slice(2)}`, []);
    const canRender = isOpen && typeof document !== 'undefined';

    useEffect(() => {
        if (!canRender) return undefined;
        modalStack.push(modalId);
        const onKeyDown = (event) => {
            if (event.key !== 'Escape') return;
            const top = modalStack[modalStack.length - 1];
            if (top !== modalId) return;
            event.preventDefault();
            event.stopPropagation();
            onClose?.();
        };
        window.addEventListener('keydown', onKeyDown, true);
        return () => {
            modalStack = modalStack.filter((id) => id !== modalId);
            window.removeEventListener('keydown', onKeyDown, true);
        };
    }, [modalId, onClose, canRender]);

    if (!canRender) return null;

    return createPortal(
        <div className="layer-modal fixed inset-0 flex items-start justify-center overflow-y-auto bg-slate-900/25 p-4 pt-10 backdrop-blur-[2px]">
            <div className={`w-full ${maxWidthClass} max-h-[90vh] flex flex-col rounded-sm border border-border/85 bg-card text-card-foreground shadow-lg animate-in fade-in zoom-in-95 duration-200`}>
                <div className="flex items-center justify-between border-b border-border/70 p-4">
                    <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
                    <button
                        onClick={onClose}
                        className="btn-minimal"
                        aria-label={t('modal.close')}
                    >
                        <X size={18} />
                    </button>
                </div>
                <div className={`overflow-y-auto p-4 ${bodyClassName}`}>
                    {children}
                </div>
            </div>
        </div>,
        document.body,
    );
}
