-- 000002_auth_rbac.down.sql

DROP INDEX IF EXISTS idx_users_email;
DROP INDEX IF EXISTS idx_users_tenant_email;

ALTER TABLE users
    DROP COLUMN IF EXISTS role,
    DROP COLUMN IF EXISTS password_hash,
    DROP COLUMN IF EXISTS email;
