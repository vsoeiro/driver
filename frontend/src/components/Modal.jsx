
import { X } from 'lucide-react';

export default function Modal({ isOpen, onClose, title, children }) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
            <div className="bg-card border text-card-foreground rounded-lg shadow-lg w-full max-w-md animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between p-4 border-b">
                    <h3 className="font-semibold text-lg">{title}</h3>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-accent rounded-md transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>
                <div className="p-4">
                    {children}
                </div>
            </div>
        </div>
    );
}
