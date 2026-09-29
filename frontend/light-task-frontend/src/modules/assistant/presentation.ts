const fieldNames: Record<string, string> = {
  title: 'Название', description: 'Описание', task_id: 'Задача',
  column_id: 'Колонка', new_column_id: 'Новая колонка',
  priority: 'Приоритет', assignee_id: 'Исполнитель',
  deadline_at: 'Срок', tag_ids: 'Теги', name: 'Название', new_name: 'Новое название',
  before_column_id: 'Перед колонкой', tag_id: 'Тег', color: 'Цвет',
};
const priorityLabels: Record<string, string> = {
  LOW: 'Низкий', MEDIUM: 'Средний', HIGH: 'Высокий', CRITICAL: 'Критический',
};
const emptyLabels: Record<string, string> = {
  assignee_id: 'Без исполнителя', deadline_at: 'Без срока', tag_ids: 'Без тегов',
  before_column_id: 'В конец доски', priority: 'Без приоритета',
};

export function formatDeadline(value: string): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}(?:T00:00:00(?:\.0+)?(?:Z|[+-]00:00)?)?$/.test(value);
  const date = new Date(dateOnly ? `${value.slice(0, 10)}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
    ...(dateOnly ? { timeZone: 'UTC' } : { hour: '2-digit', minute: '2-digit' }),
  }).format(date);
}

export function actionFields(args: Record<string, unknown>, display: Record<string, unknown> = {}) {
  return Object.entries(args).filter(([key]) => key in fieldNames).map(([key, raw]) => {
    const value = display[key] ?? raw;
    let formatted: string;
    if (value == null || (Array.isArray(value) && value.length === 0)) formatted = emptyLabels[key] ?? '—';
    else if (key === 'deadline_at') formatted = formatDeadline(String(value));
    else if (key === 'priority') formatted = priorityLabels[String(value)] ?? String(value);
    else if ((key.endsWith('_id') || key === 'tag_ids') && display[key] == null) formatted = 'Название недоступно';
    else formatted = Array.isArray(value) ? value.join(', ') : String(value);
    return { key, label: fieldNames[key], value: formatted };
  });
}
