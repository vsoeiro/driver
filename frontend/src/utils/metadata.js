export function getSelectOptions(attrOptions) {
    const options = attrOptions?.options;
    if (!Array.isArray(options)) return [];

    return options
        .map((opt) => {
            if (typeof opt === 'string') return opt.trim();
            if (opt && typeof opt === 'object') {
                return String(opt.value ?? opt.label ?? '').trim();
            }
            return String(opt ?? '').trim();
        })
        .filter(Boolean);
}
