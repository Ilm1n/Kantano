# GigaChat TLS

`russian_trusted_root_ca.pem` — публичный корневой сертификат НУЦ Минцифры,
полученный с `https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt`.
Источник указан в [документации GigaChat](https://developers.sber.ru/docs/ru/gigachat/certificates).

Клиент GigaChat добавляет этот CA к стандартному набору certifi в отдельном
SSL context. Проверка цепочки и имени сервера включена. Системное хранилище
сертификатов и другие HTTP-клиенты приложения не изменяются.
