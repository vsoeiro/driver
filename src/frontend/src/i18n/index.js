import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import ptBR from './locales/pt-BR.json';

const LANGUAGE_STORAGE_KEY = 'driver-language';
const SUPPORTED_LANGUAGES = ['pt-BR', 'en'];

const detectLanguage = () => {
    if (import.meta.env.MODE === 'test') return 'en';

    const saved = typeof window !== 'undefined' ? window.localStorage.getItem(LANGUAGE_STORAGE_KEY) : null;
    if (saved && SUPPORTED_LANGUAGES.includes(saved)) return saved;

    const browser = typeof navigator !== 'undefined' ? navigator.language : '';
    if (browser && browser.toLowerCase().startsWith('pt')) return 'pt-BR';
    return 'en';
};

if (!i18n.isInitialized) {
    i18n
        .use(initReactI18next)
        .init({
            resources: {
                en: { translation: en },
                'pt-BR': { translation: ptBR },
            },
            lng: detectLanguage(),
            fallbackLng: 'en',
            interpolation: {
                escapeValue: false,
            },
        });

    i18n.on('languageChanged', (language) => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    });
}

export { LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES };
export default i18n;

