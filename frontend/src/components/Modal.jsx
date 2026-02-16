
import { X } from 'lucide-react';

export default function Modal({
    isOpen,
    onClose,
    title,
    children,
    maxWidthClass = 'max-w-md',
    bodyClassName = '',
}) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-8 bg-background/80 backdrop-blur-sm overflow-y-auto">
            <div className={`bg-card border text-card-foreground rounded-lg shadow-lg w-full ${maxWidthClass} max-h-[90vh] flex flex-col animate-in fade-in zoom-in-95 duration-200`}>
                <div className="flex items-center justify-between p-4 border-b">
                    <h3 className="font-semibold text-lg">{title}</h3>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-accent rounded-md transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>
                <div className={`p-4 overflow-y-auto ${bodyClassName}`}>
                    {children}
                </div>
            </div>
        </div>
    );
}
