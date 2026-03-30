export interface TopicMeta {
  id: string;
  label: string;
  /** Tailwind classes for the solid chip (primary category badge) */
  cls: string;
  /** Tailwind classes for the outlined chip (secondary category badge) */
  secondary_cls: string;
  /** Tailwind ring class for active filter chips */
  ring: string;
  /** Tailwind class for bar fill in charts */
  barCls: string;
  /** Hex color for SVG rendering (Tailwind *-400 equivalent) */
  hex: string;
}

export const TOPICS: TopicMeta[] = [
  { id: 'history',       label: 'History',       cls: 'bg-amber-100 text-amber-800 hover:bg-amber-200',       secondary_cls: 'border border-amber-400 text-amber-700 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400 dark:hover:bg-amber-900/20',       ring: 'ring-amber-400',   barCls: 'bg-amber-400',   hex: '#fbbf24' },
  { id: 'science',       label: 'Science',        cls: 'bg-sky-100 text-sky-800 hover:bg-sky-200',             secondary_cls: 'border border-sky-400 text-sky-700 hover:bg-sky-50 dark:border-sky-600 dark:text-sky-400 dark:hover:bg-sky-900/20',             ring: 'ring-sky-400',     barCls: 'bg-sky-400',     hex: '#38bdf8' },
  { id: 'technology',    label: 'Technology',     cls: 'bg-indigo-100 text-indigo-800 hover:bg-indigo-200',    secondary_cls: 'border border-indigo-400 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-500 dark:text-indigo-400 dark:hover:bg-indigo-900/20',    ring: 'ring-indigo-400',  barCls: 'bg-indigo-400',  hex: '#818cf8' },
  { id: 'sports',        label: 'Sports',         cls: 'bg-green-100 text-green-800 hover:bg-green-200',       secondary_cls: 'border border-green-400 text-green-700 hover:bg-green-50 dark:border-green-600 dark:text-green-400 dark:hover:bg-green-900/20',       ring: 'ring-green-400',   barCls: 'bg-green-400',   hex: '#4ade80' },
  { id: 'geography',     label: 'Geography',      cls: 'bg-teal-100 text-teal-800 hover:bg-teal-200',          secondary_cls: 'border border-teal-400 text-teal-700 hover:bg-teal-50 dark:border-teal-600 dark:text-teal-400 dark:hover:bg-teal-900/20',          ring: 'ring-teal-400',    barCls: 'bg-teal-400',    hex: '#2dd4bf' },
  { id: 'entertainment', label: 'Entertainment',  cls: 'bg-violet-100 text-violet-800 hover:bg-violet-200',    secondary_cls: 'border border-violet-400 text-violet-700 hover:bg-violet-50 dark:border-violet-500 dark:text-violet-400 dark:hover:bg-violet-900/20',    ring: 'ring-violet-400',  barCls: 'bg-violet-400',  hex: '#a78bfa' },
  { id: 'food_drink',    label: 'Food & Drink',   cls: 'bg-orange-100 text-orange-800 hover:bg-orange-200',    secondary_cls: 'border border-orange-400 text-orange-700 hover:bg-orange-50 dark:border-orange-600 dark:text-orange-400 dark:hover:bg-orange-900/20',    ring: 'ring-orange-400',  barCls: 'bg-orange-400',  hex: '#fb923c' },
  { id: 'art_culture',   label: 'Art & Culture',  cls: 'bg-fuchsia-100 text-fuchsia-800 hover:bg-fuchsia-200', secondary_cls: 'border border-fuchsia-400 text-fuchsia-700 hover:bg-fuchsia-50 dark:border-fuchsia-500 dark:text-fuchsia-400 dark:hover:bg-fuchsia-900/20', ring: 'ring-fuchsia-400', barCls: 'bg-fuchsia-400', hex: '#e879f9' },
  { id: 'literature',    label: 'Literature',     cls: 'bg-red-100 text-red-800 hover:bg-red-200',             secondary_cls: 'border border-red-400 text-red-700 hover:bg-red-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-900/20',             ring: 'ring-red-400',     barCls: 'bg-red-400',     hex: '#f87171' },
  { id: 'business',      label: 'Business',       cls: 'bg-slate-100 text-slate-700 hover:bg-slate-200',       secondary_cls: 'border border-slate-400 text-slate-600 hover:bg-slate-50 dark:border-slate-500 dark:text-slate-400 dark:hover:bg-slate-900/20',       ring: 'ring-slate-400',   barCls: 'bg-slate-400',   hex: '#94a3b8' },
  { id: 'etymology',     label: 'Etymology',      cls: 'bg-rose-100 text-rose-800 hover:bg-rose-200',          secondary_cls: 'border border-rose-400 text-rose-700 hover:bg-rose-50 dark:border-rose-600 dark:text-rose-400 dark:hover:bg-rose-900/20',          ring: 'ring-rose-400',    barCls: 'bg-rose-400',    hex: '#fb7185' },
  { id: 'mythology',     label: 'Mythology',      cls: 'bg-purple-100 text-purple-800 hover:bg-purple-200',    secondary_cls: 'border border-purple-400 text-purple-700 hover:bg-purple-50 dark:border-purple-500 dark:text-purple-400 dark:hover:bg-purple-900/20',    ring: 'ring-purple-400',  barCls: 'bg-purple-400',  hex: '#c084fc' },
  { id: 'geology',       label: 'Geology',        cls: 'bg-stone-100 text-stone-800 hover:bg-stone-200',       secondary_cls: 'border border-stone-400 text-stone-700 hover:bg-stone-50 dark:border-stone-500 dark:text-stone-400 dark:hover:bg-stone-900/20',       ring: 'ring-stone-400',   barCls: 'bg-stone-400',   hex: '#a8a29e' },
  { id: 'general',       label: 'General',        cls: 'bg-lime-100 text-lime-800 hover:bg-lime-200',          secondary_cls: 'border border-lime-400 text-lime-700 hover:bg-lime-50 dark:border-lime-600 dark:text-lime-400 dark:hover:bg-lime-900/20',          ring: 'ring-lime-400',    barCls: 'bg-lime-400',    hex: '#a3e635' },
];

export const TOPIC_MAP = new Map(TOPICS.map(t => [t.id, t]));

export function topicCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.cls ?? 'bg-gray-100 text-gray-700 hover:bg-gray-200';
}

export function topicClsSecondary(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.secondary_cls ?? 'border border-gray-300 text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800';
}

export function topicLabel(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.label ?? topicId.replace('_', ' & ');
}

export function topicBarCls(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.barCls ?? 'bg-gray-400';
}

export function topicHex(topicId: string): string {
  return TOPIC_MAP.get(topicId)?.hex ?? '#9ca3af';
}
