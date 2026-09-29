import { describe, expect, it } from 'vitest';
import { actionFields, formatDeadline } from './presentation';

describe('assistant confirmation presentation', () => {
  it('uses entity labels and readable dates, including legacy ISO midnight dates', () => {
    const fields = actionFields(
      { assignee_id: 123, column_id: 4, tag_ids: [12], deadline_at: '2026-10-02T00:00:00', priority: 'HIGH' },
      { assignee_id: 'Илья', column_id: 'Разработка', tag_ids: ['Функция'] },
    );
    expect(fields.map((field) => field.value)).toEqual(['Илья', 'Разработка', 'Функция', '2 октября 2026 г.', 'Высокий']);
    expect(formatDeadline('2026-10-02')).toBe(formatDeadline('2026-10-02T00:00:00Z'));
  });

  it('distinguishes clearing a field from an unavailable name', () => {
    const fields = actionFields({ assignee_id: null, deadline_at: null, tag_ids: [], before_column_id: null, task_id: 999 });
    expect(fields.map((field) => field.value)).toEqual(['Без исполнителя', 'Без срока', 'Без тегов', 'В конец доски', 'Название недоступно']);
  });
});
