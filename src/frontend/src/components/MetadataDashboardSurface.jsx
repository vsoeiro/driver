import { Loader2, RefreshCw } from 'lucide-react';

import { formatDateOnly } from '../utils/dateTime';

const DASHBOARD_DATA_TYPE_LABEL_KEYS = {
    text: 'typeText',
    number: 'typeNumber',
    date: 'typeDate',
    boolean: 'typeBoolean',
    select: 'typeSelect',
    tags: 'typeTags',
};
const DASHBOARD_CHART_COLORS = ['#2563eb', '#f97316', '#14b8a6', '#ef4444', '#8b5cf6', '#eab308'];
const DASHBOARD_MONTH_BUCKET_RE = /^(\d{4})-(\d{2})$/;
const DASHBOARD_YEAR_BUCKET_RE = /^\d{4}$/;
const DASHBOARD_BAR_SLOT_WIDTH = 64;
const DASHBOARD_BAR_MAX_LABEL_LENGTH = 18;

const formatDashboardNumber = (value, language) => {
    if (!Number.isFinite(Number(value))) return '-';
    const numericValue = Number(value);
    return new Intl.NumberFormat(language, {
        maximumFractionDigits: Number.isInteger(numericValue) ? 0 : 1,
    }).format(numericValue);
};

const formatDashboardStatLabel = (statKey, t) => {
    if (statKey === 'min') return t('metadataManager.dashboard.min');
    if (statKey === 'max') return t('metadataManager.dashboard.max');
    if (statKey === 'average') return t('metadataManager.dashboard.average');
    if (statKey === 'earliest') return t('metadataManager.dashboard.earliest');
    if (statKey === 'latest') return t('metadataManager.dashboard.latest');
    return statKey;
};

const formatDashboardStatValue = (stat, language) => {
    if (stat.key === 'min' || stat.key === 'max' || stat.key === 'average') {
        return formatDashboardNumber(stat.value, language);
    }
    if (stat.key === 'earliest' || stat.key === 'latest') {
        return formatDateOnly(stat.value, language);
    }
    return String(stat.value || '-');
};

const formatDashboardDateBucketLabel = (value, language) => {
    const normalized = String(value || '').trim();
    if (!normalized) return '-';
    const monthMatch = normalized.match(DASHBOARD_MONTH_BUCKET_RE);
    if (monthMatch) {
        const [, year, month] = monthMatch;
        return new Intl.DateTimeFormat(language, { month: 'short', year: 'numeric' }).format(
            new Date(Date.UTC(Number(year), Number(month) - 1, 1)),
        );
    }
    if (DASHBOARD_YEAR_BUCKET_RE.test(normalized)) {
        return new Intl.DateTimeFormat(language, { year: 'numeric' }).format(
            new Date(Date.UTC(Number(normalized), 0, 1)),
        );
    }
    return normalized;
};

const formatDashboardPointLabel = (card, point, language, t) => {
    if (card.chart_type === 'histogram' && Number.isFinite(Number(point.range_start)) && Number.isFinite(Number(point.range_end))) {
        return `${formatDashboardNumber(point.range_start, language)} to ${formatDashboardNumber(point.range_end, language)}`;
    }
    if (card.data_type === 'boolean') {
        return point.value === 'true' ? t('common.yes') : t('common.no');
    }
    if (card.data_type === 'date') {
        return formatDashboardDateBucketLabel(point.value || point.label, language);
    }
    if (card.data_type === 'number' && point.value !== null && point.value !== undefined && point.value !== '') {
        return formatDashboardNumber(point.value, language);
    }
    return String(point.label || point.value || '-');
};

const truncateDashboardLabel = (value, maxLength = DASHBOARD_BAR_MAX_LABEL_LENGTH) => {
    const normalized = String(value || '-');
    if (normalized.length <= maxLength) return normalized;
    if (maxLength <= 3) return normalized.slice(0, maxLength);
    return `${normalized.slice(0, Math.max(1, maxLength - 3))}...`;
};

const MetadataDashboardHorizontalBarChart = ({ card, t, language }) => {
    const points = Array.isArray(card.points) ? card.points.filter((point) => Number(point?.count) > 0) : [];
    if (points.length === 0) {
        return <p className="mt-3 text-sm text-muted-foreground">{t('metadataManager.dashboard.noValues')}</p>;
    }

    const denominator = Math.max(1, Number(card.filled_count || 0));
    const peak = points.reduce((maxValue, point) => Math.max(maxValue, Number(point.count) || 0), 0);

    return (
        <div className="mt-4" role="img" aria-label={t('metadataManager.dashboard.valueHorizontalBarChart')}>
            <div className="space-y-2.5">
                {points.map((point) => {
                    const count = Number(point.count) || 0;
                    const percent = Math.round((count / denominator) * 100);
                    const widthPercent = peak > 0 ? Math.max(8, Math.round((count / peak) * 100)) : 0;
                    const label = formatDashboardPointLabel(card, point, language, t);
                    return (
                        <div key={`${card.attribute_id}-${point.key}`}>
                            <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
                                <span className="truncate text-foreground" title={label}>{label}</span>
                                <span className="shrink-0 text-xs text-muted-foreground">
                                    {count} ({percent}%)
                                </span>
                            </div>
                            <div className="h-3 overflow-hidden rounded-full bg-muted/80">
                                <div
                                    className="h-full rounded-full bg-primary/85 transition-[width] duration-300"
                                    style={{ width: `${widthPercent}%` }}
                                />
                            </div>
                        </div>
                    );
                })}
            </div>
            {['text', 'tags'].includes(card.data_type) && card.distinct_count > points.length && (
                <p className="mt-2 text-xs text-muted-foreground">
                    {t('metadataManager.dashboard.topValuesShown', { count: points.length })}
                </p>
            )}
        </div>
    );
};

const MetadataDashboardVerticalBarChart = ({ card, t, language }) => {
    const points = Array.isArray(card.points) ? card.points.filter((point) => Number(point?.count) > 0) : [];
    if (points.length === 0) {
        return <p className="mt-3 text-sm text-muted-foreground">{t('metadataManager.dashboard.noValues')}</p>;
    }

    const denominator = Math.max(1, Number(card.filled_count || 0));
    const peak = points.reduce((maxValue, point) => Math.max(maxValue, Number(point.count) || 0), 0);
    const chartHeight = 172;
    const chartTop = 18;
    const chartBottom = 194;
    const labelBaselineY = 214;
    const svgHeight = 272;
    const chartWidth = Math.max(340, (points.length * DASHBOARD_BAR_SLOT_WIDTH) + 28);
    const displayPoints = points.map((point, index) => {
        const count = Number(point.count) || 0;
        const percent = Math.round((count / denominator) * 100);
        const label = formatDashboardPointLabel(card, point, language, t);
        const barHeight = peak > 0 ? Math.max(14, Math.round((count / peak) * chartHeight)) : 0;
        const barWidth = Math.min(40, DASHBOARD_BAR_SLOT_WIDTH - 18);
        const x = 14 + (index * DASHBOARD_BAR_SLOT_WIDTH) + ((DASHBOARD_BAR_SLOT_WIDTH - barWidth) / 2);
        const y = chartBottom - barHeight;
        return {
            ...point,
            barHeight,
            barWidth,
            count,
            label,
            labelShort: truncateDashboardLabel(label),
            percent,
            x,
            y,
        };
    });
    const gridLineYs = [chartTop, chartTop + (chartHeight / 2), chartBottom];

    return (
        <div className="mt-4">
            <div className="overflow-x-auto pb-2">
                <svg
                    role="img"
                    aria-label={t('metadataManager.dashboard.valueBarChart')}
                    viewBox={`0 0 ${chartWidth} ${svgHeight}`}
                    className="h-72 w-full min-w-[340px] text-muted-foreground"
                >
                    {gridLineYs.map((lineY) => (
                        <line
                            key={`${card.attribute_id}-grid-${lineY}`}
                            x1="10"
                            x2={chartWidth - 10}
                            y1={lineY}
                            y2={lineY}
                            stroke="currentColor"
                            strokeOpacity="0.14"
                        />
                    ))}
                    {displayPoints.map((point) => (
                        <g key={`${card.attribute_id}-${point.key}`}>
                            <title>{`${point.label}: ${point.count} (${point.percent}%)`}</title>
                            <text
                                x={point.x + (point.barWidth / 2)}
                                y={Math.max(12, point.y - 8)}
                                textAnchor="middle"
                                fill="currentColor"
                                fontSize="11"
                                fontWeight="600"
                            >
                                {point.count}
                            </text>
                            <rect
                                x={point.x}
                                y={point.y}
                                width={point.barWidth}
                                height={point.barHeight}
                                rx="12"
                                fill="rgba(37, 99, 235, 0.88)"
                            />
                            <text
                                x={point.x + (point.barWidth / 2)}
                                y={labelBaselineY}
                                textAnchor="end"
                                transform={`rotate(-34 ${point.x + (point.barWidth / 2)} ${labelBaselineY})`}
                                fill="currentColor"
                                fontSize="11"
                            >
                                {point.labelShort}
                            </text>
                        </g>
                    ))}
                </svg>
            </div>
        </div>
    );
};

const MetadataDashboardPieChart = ({ card, t, language }) => {
    const points = Array.isArray(card.points) ? card.points : [];
    const total = points.reduce((sum, point) => sum + (Number(point?.count) || 0), 0);
    if (total <= 0) {
        return <p className="mt-3 text-sm text-muted-foreground">{t('metadataManager.dashboard.noValues')}</p>;
    }

    let startDeg = 0;
    const segments = points
        .filter((point) => Number(point?.count) > 0)
        .map((point, index) => {
            const count = Number(point.count) || 0;
            const sweep = (count / total) * 360;
            const segment = {
                ...point,
                color: DASHBOARD_CHART_COLORS[index % DASHBOARD_CHART_COLORS.length],
                startDeg,
                endDeg: startDeg + sweep,
            };
            startDeg += sweep;
            return segment;
        });
    const gradient = segments.length > 0
        ? `conic-gradient(${segments.map((segment) => `${segment.color} ${segment.startDeg}deg ${segment.endDeg}deg`).join(', ')})`
        : 'none';

    return (
        <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-center">
            <div className="flex justify-center lg:w-40 lg:shrink-0">
                <div
                    role="img"
                    aria-label={t('metadataManager.dashboard.booleanPieChart')}
                    className="relative h-32 w-32 rounded-full border border-border/70"
                    style={{ background: gradient }}
                >
                    <div className="absolute inset-[22%] rounded-full bg-background/95" />
                    <div className="absolute inset-0 flex items-center justify-center text-center">
                        <div>
                            <div className="text-xl font-semibold text-foreground">{total}</div>
                            <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                                {t('metadataManager.dashboard.booleanChart')}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div className="grid flex-1 gap-2">
                {points.map((point, index) => {
                    const count = Number(point.count) || 0;
                    const percent = total > 0 ? Math.round((count / total) * 100) : 0;
                    const label = formatDashboardPointLabel(card, point, language, t);
                    return (
                        <div key={`${card.attribute_id}-${point.key}`} className="rounded-xl border border-border/60 bg-background/70 px-3 py-2">
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <span
                                        className="inline-block h-2.5 w-2.5 rounded-full"
                                        style={{ backgroundColor: DASHBOARD_CHART_COLORS[index % DASHBOARD_CHART_COLORS.length] }}
                                    />
                                    <span className="text-sm text-foreground">{label}</span>
                                </div>
                                <span className="text-xs text-muted-foreground">{count} ({percent}%)</span>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

const MetadataDashboardChart = ({ card, t, language }) => {
    if (card.chart_type === 'pie') {
        return <MetadataDashboardPieChart card={card} t={t} language={language} />;
    }
    if (card.data_type === 'text' || card.data_type === 'tags') {
        return <MetadataDashboardHorizontalBarChart card={card} t={t} language={language} />;
    }
    return <MetadataDashboardVerticalBarChart card={card} t={t} language={language} />;
};

const MetadataDashboardSurface = ({
    category,
    dashboardQuery,
    metadataDashboard,
    t,
    language,
}) => (
    <section
        className="surface-card overflow-hidden"
        aria-labelledby={`metadata-dashboard-${category.id}`}
    >
        <div className="border-b border-border/70 px-4 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h2 id={`metadata-dashboard-${category.id}`} className="text-base font-semibold text-foreground">
                        {t('metadataManager.dashboard.title')}
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t('metadataManager.dashboard.subtitle')}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="status-chip">
                        {t('metadataManager.dashboard.fieldsTracked', { count: (metadataDashboard.cards || []).length })}
                    </span>
                    <button
                        type="button"
                        onClick={() => dashboardQuery.refetch()}
                        disabled={dashboardQuery.isFetching}
                        className="btn-minimal h-9 px-3 text-xs"
                    >
                        {dashboardQuery.isFetching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                        <span>{t('common.reload')}</span>
                    </button>
                </div>
            </div>
        </div>

        {dashboardQuery.isLoading ? (
            <div className="flex items-center justify-center px-4 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 animate-spin text-primary" size={18} />
                <span>{t('common.loading')}</span>
            </div>
        ) : dashboardQuery.isError ? (
            <div className="px-4 py-8">
                <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-4 py-4">
                    <div className="text-sm font-medium text-foreground">
                        {t('metadataManager.dashboard.failedLoad')}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {dashboardQuery.error?.response?.data?.detail || dashboardQuery.error?.message || t('metadataManager.dashboard.failedLoadHelp')}
                    </p>
                </div>
            </div>
        ) : (
            <>
                <div className="grid gap-3 px-4 py-4 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-2xl border border-border/70 bg-background/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                            {t('metadataManager.dashboard.totalItems')}
                        </div>
                        <div className="mt-2 text-xl font-semibold text-foreground">
                            {metadataDashboard.total_items}
                        </div>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-background/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                            {t('metadataManager.dashboard.analyzedItems')}
                        </div>
                        <div className="mt-2 text-xl font-semibold text-foreground">
                            {metadataDashboard.total_items}
                        </div>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-background/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                            {t('metadataManager.dashboard.averageCoverage')}
                        </div>
                        <div className="mt-2 text-xl font-semibold text-foreground">
                            {metadataDashboard.average_coverage}%
                        </div>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-background/80 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                            {t('metadataManager.dashboard.fieldsWithGaps')}
                        </div>
                        <div className="mt-2 text-xl font-semibold text-foreground">
                            {metadataDashboard.fields_with_gaps}
                        </div>
                    </div>
                </div>

                <div className="border-t border-border/70 px-4 py-4">
                    {!Array.isArray(metadataDashboard.cards) || metadataDashboard.cards.length === 0 ? (
                        <div className="rounded-2xl border border-dashed border-border/70 bg-background/50 px-4 py-6 text-sm text-muted-foreground">
                            {t('metadataManager.dashboard.noFields')}
                        </div>
                    ) : (
                        <div className="grid gap-3 xl:grid-cols-2">
                            {metadataDashboard.cards.map((card) => (
                                <article
                                    key={card.attribute_id}
                                    className="rounded-2xl border border-border/70 bg-background/70 px-4 py-4"
                                >
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <div className="font-medium text-foreground">{card.name}</div>
                                            <div className="mt-1 text-xs text-muted-foreground">
                                                {t(`metadataManager.${DASHBOARD_DATA_TYPE_LABEL_KEYS[card.data_type] || 'typeText'}`)}
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-lg font-semibold text-foreground">{card.fill_rate}%</div>
                                            <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                                                {t('metadataManager.dashboard.coverage')}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="mt-3 flex flex-wrap gap-2">
                                        <span className="workspace-context-chip">
                                            {t('metadataManager.dashboard.filledItems', { count: card.filled_count })}
                                        </span>
                                        <span className="workspace-context-chip">
                                            {t('metadataManager.dashboard.distinctValues', { count: card.distinct_count })}
                                        </span>
                                    </div>

                                    {Array.isArray(card.stats) && card.stats.length > 0 && (
                                        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                                            {card.stats.map((stat) => (
                                                <div
                                                    key={`${card.attribute_id}-${stat.key}`}
                                                    className="rounded-xl border border-border/60 bg-background/70 px-3 py-2"
                                                >
                                                    <div className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
                                                        {formatDashboardStatLabel(stat.key, t)}
                                                    </div>
                                                    <div className="mt-1 text-sm font-medium text-foreground">
                                                        {formatDashboardStatValue(stat, language)}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <MetadataDashboardChart card={card} t={t} language={language} />
                                </article>
                            ))}
                        </div>
                    )}
                </div>
            </>
        )}
    </section>
);

export default MetadataDashboardSurface;
