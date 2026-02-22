import { useEffect } from 'react';
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
            accent: 'border-emerald-400/50',
            iconWrap: 'bg-emerald-500/12 text-emerald-700',
            text: 'text-emerald-900',
            icon: <Check className="w-4 h-4" />,
        },
        error: {
            accent: 'border-rose-400/55',
            iconWrap: 'bg-rose-500/12 text-rose-700',
            text: 'text-rose-900',
            icon: <AlertCircle className="w-4 h-4" />,
        },
        info: {
            accent: 'border-sky-400/55',
            iconWrap: 'bg-sky-500/12 text-sky-700',
            text: 'text-slate-900',
            icon: <Info className="w-4 h-4" />,
        },
        warning: {
            accent: 'border-amber-400/65',
            iconWrap: 'bg-amber-500/14 text-amber-700',
            text: 'text-amber-900',
            icon: <AlertTriangle className="w-4 h-4" />,
        },
    };

    const style = styles[type] || styles.info;

    return (
        <div className={`pointer-events-auto flex items-start gap-3 rounded-xl border bg-card/95 p-3 shadow-[0_18px_42px_-32px_rgba(7,24,48,0.72)] backdrop-blur-md ${style.accent} animate-enter-stagger`}>
            <div className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${style.iconWrap}`}>
                {style.icon}
            </div>
            <div className="min-w-[180px] flex-1">
                <p className={`text-sm font-medium ${style.text}`}>{message}</p>
            </div>
            <button
                onClick={() => onClose(id)}
                className="ghost-icon-button p-1.5"
                aria-label="Close toast"
            >
                <X className="h-4 w-4" />
            </button>
        </div>
    );
}
