-- 000001_initial_schema.down.sql
-- 按外键依赖逆序删除。

DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS users;
