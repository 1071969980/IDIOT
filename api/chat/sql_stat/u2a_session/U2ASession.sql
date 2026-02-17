-- CreateTable
CREATE TABLE IF NOT EXISTS u2a_sessions (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    title VARCHAR(255) DEFAULT '',
    archived BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(32) NOT NULL CHECK (created_by IN ('user', 'agent', 'system')),
    context_lock BOOLEAN DEFAULT FALSE,
    created_from_id_by_agent UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (created_from_id_by_agent) REFERENCES u2a_sessions(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_sessions_user_id_created_by ON u2a_sessions (user_id, created_by);
--
CREATE INDEX IF NOT EXISTS idx_u2a_sessions_created_from_id_by_agent ON u2a_sessions (created_from_id_by_agent);

-- InsertSession
INSERT INTO u2a_sessions (user_id, title, created_by, created_from_id_by_agent)
VALUES (:user_id, :title, :created_by, :created_from_id_by_agent)
RETURNING id;

-- UpdateSession1
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateSession2
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateSession3
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- QuerySession
SELECT *
FROM u2a_sessions
WHERE id = :id_value;

-- QuerySessionByUserId
SELECT *
FROM u2a_sessions
WHERE user_id = :user_id_value;

-- QuerySessionByCreatedBy
SELECT *
FROM u2a_sessions
WHERE created_by = :created_by_value AND user_id = :user_id_value;

-- QuerySessionByCreatedFromIdByAgent
SELECT *
FROM u2a_sessions
WHERE created_from_id_by_agent = :created_from_id_by_agent_value;

-- IsExists
SELECT COUNT(*)
FROM u2a_sessions
WHERE id = :id_value;

-- QueryField1
SELECT :field_name_1
FROM u2a_sessions
WHERE id = :id_value;

-- QueryField2
SELECT :field_name_1, :field_name_2
FROM u2a_sessions
WHERE id = :id_value;

-- QueryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_sessions
WHERE id = :id_value;

-- QueryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_sessions
WHERE id = :id_value;

-- DeleteSession
DELETE FROM u2a_sessions
WHERE id = :id_value;

-- GetContextLock
SELECT context_lock
FROM u2a_sessions
WHERE id = :id_value;

-- UpdateContextLock
UPDATE u2a_sessions
SET context_lock = :context_lock_value
WHERE id = :id_value;

-- CreateSessionTriggers
CREATE OR REPLACE FUNCTION u2a_session_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER u2a_session_before_insert
BEFORE INSERT ON u2a_sessions
FOR EACH ROW
EXECUTE FUNCTION u2a_session_update_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_before_update
BEFORE UPDATE ON u2a_sessions
FOR EACH ROW
EXECUTE FUNCTION u2a_session_update_timestamp();