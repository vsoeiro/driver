function resolveLocale(language) {
  if (!language) return 'en';
  if (language === 'pt-BR' || language === 'en') return language;
  return language;
}

function toValidDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

export function formatDateTime(value, language) {
  const date = toValidDate(value);
  if (!date) return '-';
  return new Intl.DateTimeFormat(resolveLocale(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function formatDateOnly(value, language) {
  const date = toValidDate(value);
  if (!date) return '-';
  return new Intl.DateTimeFormat(resolveLocale(language), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour12: false,
  }).format(date);
}
