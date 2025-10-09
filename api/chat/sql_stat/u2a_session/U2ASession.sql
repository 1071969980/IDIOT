-- CreateTable
CREATE TABLE IF NOT EXISTS u2a_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    session_id CHAR(36) NOT NULL,
    title VARCHAR(255) DEFAULT '',
    archived BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(32) NOT NULL CHECK (created_by IN ('user', 'agent')),
    context_lock BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id),
    FOREIGN KEY (user_id) REFERENCES simple_users(uuid) ON DELETE CASCADE
);

CREATE INDEX idx_u2a_sessions_session_id ON u2a_sessions (session_id);

-- InsertSession
INSERT INTO u2a_sessions (user_id, session_id, title)
VALUES (:user_id, :session_id, :title);

-- UpdateSession1
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1
WHERE session_id = :session_id_value;

-- UpdateSession2
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE session_id = :session_id_value;

-- UpdateSession3
UPDATE u2a_sessions
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE session_id = :session_id_value;

-- QuerySession
SELECT *
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- QuerySessionByUserId
SELECT *
FROM u2a_sessions
WHERE user_id = :user_id_value;

-- IsExists
SELECT COUNT(*)
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- QueryField1
SELECT :field_name_1
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- QueryField2
SELECT :field_name_1, :field_name_2
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- QueryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- QueryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- DeleteSession
DELETE FROM u2a_sessions
WHERE session_id = :session_id_value;

-- GetContextLock
SELECT context_lock
FROM u2a_sessions
WHERE session_id = :session_id_value;

-- UpdateContextLock
UPDATE u2a_sessions
SET context_lock = :context_lock_value
WHERE session_id = :session_id_value;