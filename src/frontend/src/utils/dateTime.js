function resolveLocale(language) {
  if (!language) return 'en';
  if (language === 'pt-BR' || language === 'en') return language;
  return language;
}

export function formatDateTime(value, language) {
  if (!value) return '-';
  return new Intl.DateTimeFormat(resolveLocale(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

export function formatDateOnly(value, language) {
  if (!value) return '-';
  return new Intl.DateTimeFormat(resolveLocale(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour12: false,
  }).format(new Date(value));
}
