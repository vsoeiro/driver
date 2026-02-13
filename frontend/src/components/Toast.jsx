import React, { useEffect } from 'react';
import { X, Check, AlertCircle, Info, AlertTriangle } from 'lucide-react';

export default function Toast({ id, type, message, onClose, duration = 5000 }) {
    useEffect(() => {
        const timer = setTimeout(() => {
            onClose(id);
        }, duration);
        return () => clearTimeout(timer);
    }, [id, duration, onClose]);

    const styles = {
        success: {
            bg: 'bg-green-500/10',
            border: 'border-green-500/20',
            text: 'text-green-500',
            icon: <Check className="w-5 h-5 text-green-500" />
        },
        error: {
            bg: 'bg-red-500/10',
            border: 'border-red-500/20',
            text: 'text-red-500',
            icon: <AlertCircle className="w-5 h-5 text-red-500" />
        },
        info: {
            bg: 'bg-blue-500/10',
            border: 'border-blue-500/20',
            text: 'text-blue-500',
            icon: <Info className="w-5 h-5 text-blue-500" />
        },
        warning: {
            bg: 'bg-yellow-500/10',
            border: 'border-yellow-500/20',
            text: 'text-yellow-500',
            icon: <AlertTriangle className="w-5 h-5 text-yellow-500" />
        }
    };

    const style = styles[type] || styles.info;

    return (
        <div className={`flex items-start gap-3 p-4 rounded-lg border backdrop-blur-md shadow-lg transition-all animate-slide-in-right ${style.bg} ${style.border}`}>
            <div className="flex-shrink-0 mt-0.5">
                {style.icon}
            </div>
            <div className="flex-1 min-w-[200px]">
                <p className={`text-sm font-medium ${style.text}`}>
                    {message}
                </p>
            </div>
            <button
                onClick={() => onClose(id)}
                className={`flex-shrink-0 p-1 rounded-md transition-colors hover:bg-black/10 ${style.text}`}
            >
                <X className="w-4 h-4" />
            </button>
        </div>
    );
}
