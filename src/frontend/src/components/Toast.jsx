import { useEffect } from 'react';
import { X, Check, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function formatToastMessage(message) {
    if (typeof message === 'string' || typeof message === 'number') {
        return String(message);
    }

    if (message == null) {
        return '';
    }

    if (Array.isArray(message)) {
        const parts = message
            .map((entry) => formatToastMessage(entry))
            .filter(Boolean);
        return parts.join('\n');
    }

    if (typeof message === 'object') {
        if (message.props?.children !== undefined) {
            return formatToastMessage(message.props.children);
        }
        if (Array.isArray(message.detail)) {
            return formatToastMessage(message.detail);
        }
        if (typeof message.detail === 'string') {
            return message.detail;
        }
        if (typeof message.msg === 'string') {
            const loc = Array.isArray(message.loc) ? message.loc.slice(1).join('.') : '';
            return loc ? `${loc}: ${message.msg}` : message.msg;
        }
        if (typeof message.message === 'string') {
            return message.message;
        }
        try {
            return JSON.stringify(message);
        } catch {
            return String(message);
        }
    }

    return String(message);
}

export default function Toast({ id, type, message, onClose, duration = 5000 }) {
    const { t } = useTranslation();
    const safeMessage = formatToastMessage(message);

    useEffect(() => {
        const timer = setTimeout(() => {
            onClose(id);
        }, duration);
        return () => clearTimeout(timer);
    }, [id, duration, onClose]);

    const styles = {
        success: {
            accent: 'border-emerald-500',
            icon: 'text-emerald-700',
            text: 'text-slate-900',
            iconNode: <Check className="h-4 w-4" />,
        },
        error: {
            accent: 'border-rose-500',
            icon: 'text-rose-700',
            text: 'text-slate-900',
            iconNode: <AlertCircle className="h-4 w-4" />,
        },
        info: {
            accent: 'border-sky-500',
            icon: 'text-sky-700',
            text: 'text-slate-900',
            iconNode: <Info className="h-4 w-4" />,
        },
        warning: {
            accent: 'border-amber-500',
            icon: 'text-amber-700',
            text: 'text-slate-900',
            iconNode: <AlertTriangle className="h-4 w-4" />,
        },
    };

    const style = styles[type] || styles.info;

    return (
        <div className={`pointer-events-auto flex items-center gap-2 rounded-sm border bg-white px-3 py-2 text-sm shadow-sm ${style.accent} animate-enter-stagger`}>
            <div className={`inline-flex shrink-0 items-center justify-center ${style.icon}`}>
                {style.iconNode}
            </div>
            <div className="min-w-[180px] flex-1">
                <p className={`whitespace-pre-line leading-5 ${style.text}`}>{safeMessage}</p>
            </div>
            <button
                onClick={() => onClose(id)}
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
                aria-label={t('toast.close')}
            >
                <X className="h-4 w-4" />
            </button>
        </div>
    );
}
