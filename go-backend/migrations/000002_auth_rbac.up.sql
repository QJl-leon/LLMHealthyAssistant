-- 000002_auth_rbac.up.sql
-- 登录 / OAuth / RBAC：用户凭证与角色

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

-- 同租户邮箱唯一（允许多个 NULL 邮箱的遗留/匿名用户）
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_email
    ON users (tenant_id, email)
    WHERE email IS NOT NULL AND email <> '';

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)
    WHERE email IS NOT NULL AND email <> '';
