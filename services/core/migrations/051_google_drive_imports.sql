-- Owner-scoped Google Drive connections and durable server-side library imports.
CREATE TABLE google_drive_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_login text NOT NULL UNIQUE,
    refresh_token_ciphertext text NOT NULL,
    granted_scope text NOT NULL DEFAULT '',
    connected_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE google_drive_oauth_states (
    state_digest text PRIMARY KEY CHECK (state_digest ~ '^[0-9a-f]{64}$'),
    actor_login text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE google_drive_imports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL REFERENCES google_drive_connections(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL UNIQUE REFERENCES assets(id) ON DELETE CASCADE,
    remote_file_id text NOT NULL,
    remote_version text NOT NULL,
    remote_name text NOT NULL,
    remote_modified_at timestamptz,
    remote_md5 text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'downloading', 'downloaded', 'failed')),
    downloaded_bytes bigint NOT NULL DEFAULT 0 CHECK (downloaded_bytes >= 0),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (connection_id, remote_file_id, remote_version)
);

CREATE INDEX google_drive_imports_work_idx
    ON google_drive_imports(status, next_attempt_at, created_at)
    WHERE status IN ('pending', 'downloading');

