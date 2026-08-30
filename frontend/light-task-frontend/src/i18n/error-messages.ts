export const RU_ERROR_MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: 'Неверное имя пользователя или пароль',
  TOKEN_EXPIRED: 'Срок действия токена истек',
  COULD_NOT_VALIDATE: 'Не удалось проверить учетные данные',
  REFRESH_TOKEN_MISSING: 'Отсутствует refresh token',
  INVALID_TOKEN_TYPE: 'Неверный тип токена',
  INVALID_TOKEN_PAYLOAD: 'Недействительный payload токена',
  NOT_AUTHENTICATED: 'Не авторизован',

  USER_NOT_FOUND: 'Пользователь не найден',
  INACTIVE_USER: 'Пользователь не активен',
  USERNAME_OR_EMAIL_EXISTS: 'Email или имя пользователя уже используются',
  USERNAME_TAKEN: 'Имя пользователя уже занято',
  PASSWORD_LOGIN_UNAVAILABLE: 'У этого аккаунта ещё нет пароля. Войдите через Yandex и задайте пароль в профиле.',
  CURRENT_PASSWORD_REQUIRED: 'Введите текущий пароль',
  INVALID_CURRENT_PASSWORD: 'Текущий пароль указан неверно',

  PROJECT_NOT_FOUND: 'Проект не найден',
  INSUFFICIENT_PERMISSIONS: 'У вас недостаточно прав для выполнения этого действия',

  COLUMN_NOT_FOUND: 'Колонка не найдена',
  COLUMN_BELONGS_ANOTHER_PROJECT: 'Колонка принадлежит другому проекту',
  COLUMN_TASK_LIMIT_REACHED: 'Достигнут лимит задач в колонке',
  ASSIGNEE_NOT_PROJECT_MEMBER: 'Исполнитель не является участником проекта',
  INVALID_TAG_IDS: 'Некорректные идентификаторы тегов',
  INVALID_TARGET_COLUMN: 'Недопустимая целевая колонка',
  ANCHOR_TASK_NOT_FOUND: 'Опорная задача не найдена',
  TASK_NOT_FOUND: 'Задача не найдена',
  MEMBERS_ONLY_OWN_TASKS: 'Участники могут редактировать только свои собственные задачи',

  TAG_ALREADY_EXISTS: 'Тег с таким именем уже существует в проекте',
  TAG_NOT_FOUND: 'Тег не найден',

  INVITATION_NOT_FOUND: 'Приглашение не найдено',
  INVITATION_EXPIRED: 'Срок действия приглашения истек',
  INVITATION_USAGE_LIMIT_REACHED: 'Превышен лимит использования приглашения',
  INVITATION_FOR_OTHER_EMAIL: 'Это приглашение было отправлено другому адресу электронной почты',

  MEMBER_NOT_FOUND: 'Участник не найден',
  NOT_A_PROJECT_MEMBER: 'Вы не являетесь участником этого проекта',
  CANNOT_REMOVE_OWNER: 'Нельзя удалить владельца проекта',
  MANAGERS_CANNOT_REMOVE: 'Менеджеры не могут удалять других менеджеров. Обратитесь к владельцу.',
  CANNOT_CHANGE_OWNER_ROLE: 'Нельзя изменить роль владельца проекта',

  DATABASE_ERROR: 'Ошибка базы данных',
  FILE_UPLOAD_FAILED: 'Не удалось загрузить файл',
  DB_COMMIT_FAILED: 'Ошибка сохранения в базе данных',
  FILE_TOO_LARGE: 'Файл слишком большой. Максимальный размер: {max_size_mb} MB',
  INVALID_FILE_TYPE: 'Недопустимый тип файла. Разрешено: {allowed}',

  UNKNOWN_ERROR: 'Произошла неизвестная ошибка',
};
