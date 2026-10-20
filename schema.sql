CREATE TABLE IF NOT EXISTS task_events (
    task_id          text        NOT NULL,
    "timestamp"      timestamp   NOT NULL,
    changed_value    text        NOT NULL,
    added_values     text,
    removed_values   text,
    author_full_name text,
    activity_type    text,
    source_file      text        NOT NULL,
    file_hash        text        NOT NULL,
    row_hash         text        PRIMARY KEY,
    loaded_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_ts
    ON task_events (task_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_task_events_file_hash
    ON task_events (file_hash);
CREATE INDEX IF NOT EXISTS idx_task_events_changed
    ON task_events (changed_value);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash      text   PRIMARY KEY,
    username        text   NOT NULL,
    credential_hash text   NOT NULL,
    expires_at      bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires
    ON auth_sessions (expires_at);
