CREATE TABLE uploaded_files (
    image_key TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    mime TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_uploaded_files_owner ON uploaded_files (tenant_id, user_id);
-- Storage is rooted in the application's upload directory; image_key is the
-- relative storage name. Legacy files are deliberately not assigned an owner.
