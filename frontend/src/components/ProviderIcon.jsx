import React from 'react';

export default function ProviderIcon({ provider, className = 'w-4 h-4' }) {
    const normalized = (provider || '').toLowerCase();

    if (normalized === 'google') {
        return (
            <svg viewBox="0 0 24 24" className={className} aria-label="Google Drive">
                <polygon points="8,2 12,2 18,12 14,12" fill="#0F9D58" />
                <polygon points="8,2 2,12 6,12 12,2" fill="#4285F4" />
                <polygon points="6,12 2,12 8,22 12,22 18,12 14,12 10,19 8,19" fill="#F4B400" />
            </svg>
        );
    }

    return (
        <svg viewBox="0 0 24 24" className={className} aria-label="OneDrive">
            <path d="M9.5 9.2a4.6 4.6 0 0 1 8.4 1.9 3.8 3.8 0 0 1 .8 7.5H7.1a4.1 4.1 0 0 1-.6-8.2 4.7 4.7 0 0 1 3-1.2z" fill="#0078D4" />
        </svg>
    );
}
