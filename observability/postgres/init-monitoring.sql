SELECT format(
    'CREATE ROLE kantano_monitor WITH LOGIN PASSWORD %L',
    :'monitor_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kantano_monitor')
\gexec

SELECT format(
    'ALTER ROLE kantano_monitor WITH LOGIN PASSWORD %L',
    :'monitor_password'
)
\gexec

GRANT pg_monitor TO kantano_monitor;
