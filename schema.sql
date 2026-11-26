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
    row_hash         text        NOT NULL,
    team_id          text        NOT NULL DEFAULT 'default',
    loaded_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, row_hash)
);

-- Existing installations belong to the default team.
ALTER TABLE task_events ADD COLUMN IF NOT EXISTS team_id text NOT NULL DEFAULT 'default';

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'task_events'::regclass
          AND contype = 'p'
          AND pg_get_constraintdef(oid) = 'PRIMARY KEY (row_hash)'
    ) THEN
        ALTER TABLE task_events DROP CONSTRAINT task_events_pkey;
        ALTER TABLE task_events ADD PRIMARY KEY (team_id, row_hash);
    END IF;
END;
$migration$;

CREATE INDEX IF NOT EXISTS idx_task_events_team_task_ts
    ON task_events (team_id, task_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_task_events_team_file_hash
    ON task_events (team_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_task_events_team_ts
    ON task_events (team_id, "timestamp");
CREATE INDEX IF NOT EXISTS idx_task_events_changed
    ON task_events (changed_value);

CREATE TABLE IF NOT EXISTS web_teams (
    team_id   text PRIMARY KEY,
    name      text NOT NULL,
    project   text NOT NULL,
    subsystem text NOT NULL DEFAULT '',
    UNIQUE (project, subsystem)
);

-- A NULL display name hides a removed file-configured team.
CREATE TABLE IF NOT EXISTS configured_team_overrides (
    team_id      text PRIMARY KEY,
    display_name text
);

CREATE TABLE IF NOT EXISTS team_display_names (
    team_id text PRIMARY KEY,
    name    text NOT NULL
);

-- Existing imports can be named when their stored task IDs have one prefix.
INSERT INTO team_display_names (team_id, name)
SELECT events.team_id,
       MIN(substring(events.task_id FROM '^([^[:space:]]+)-[0-9]+$'))
FROM task_events AS events
WHERE NOT EXISTS (
    SELECT 1 FROM team_display_names AS names WHERE names.team_id = events.team_id
)
GROUP BY events.team_id
HAVING COUNT(DISTINCT substring(events.task_id FROM '^([^[:space:]]+)-[0-9]+$')) = 1
ON CONFLICT (team_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash      text   PRIMARY KEY,
    username        text   NOT NULL,
    credential_hash text   NOT NULL,
    expires_at      bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires
    ON auth_sessions (expires_at);
