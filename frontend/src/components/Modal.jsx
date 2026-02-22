import { X } from 'lucide-react';
import { createPortal } from 'react-dom';

export default function Modal({
    isOpen,
    onClose,
    title,
    children,
    maxWidthClass = 'max-w-md',
    bodyClassName = '',
}) {
    if (!isOpen) return null;

    if (typeof document === 'undefined') return null;

    return createPortal(
        <div className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-slate-900/35 p-4 pt-10 backdrop-blur-sm">
            <div className={`w-full ${maxWidthClass} max-h-[90vh] flex flex-col rounded-2xl border border-border/70 bg-card/95 text-card-foreground shadow-[0_22px_60px_-30px_rgba(10,25,50,0.65)] animate-in fade-in zoom-in-95 duration-200`}>
                <div className="flex items-center justify-between border-b border-border/70 p-4">
                    <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
                    <button
                        onClick={onClose}
                        className="ghost-icon-button"
                        aria-label="Close modal"
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
