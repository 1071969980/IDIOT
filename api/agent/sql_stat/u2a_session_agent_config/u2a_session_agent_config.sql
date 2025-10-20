-- CreateTable
CREATE TABLE IF NOT EXISTS u2a_session_agent_config (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    config JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_u2a_session_agent_config_session_id ON u2a_session_agent_config (session_id);

-- InsertSessionConfig
INSERT INTO u2a_session_agent_config (session_id, config)
VALUES (:session_id, :config)
RETURNING id;

-- UpdateSessionConfig
UPDATE u2a_session_agent_config
SET config = :config, updated_at = CURRENT_TIMESTAMP
WHERE id = :id_value;

-- UpdateSessionConfigBySessionId
UPDATE u2a_session_agent_config
SET config = :config, updated_at = CURRENT_TIMESTAMP
WHERE session_id = :session_id_value;

-- QuerySessionConfig
SELECT * FROM u2a_session_agent_config
WHERE id = :id_value;

-- QuerySessionConfigBySessionId
SELECT * FROM u2a_session_agent_config
WHERE session_id = :session_id_value;

-- QueryConfigField1
SELECT :field_name_1 FROM u2a_session_agent_config
WHERE id = :id_value;

-- QueryConfigField2
SELECT :field_name_1, :field_name_2 FROM u2a_session_agent_config
WHERE id = :id_value;

-- QueryConfigField3
SELECT :field_name_1, :field_name_2, :field_name_3 FROM u2a_session_agent_config
WHERE id = :id_value;

-- QueryConfigField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4 FROM u2a_session_agent_config
WHERE id = :id_value;

-- DeleteSessionConfig
DELETE FROM u2a_session_agent_config
WHERE id = :id_value;

-- DeleteSessionConfigBySessionId
DELETE FROM u2a_session_agent_config
WHERE session_id = :session_id_value;

-- SessionConfigExists
SELECT EXISTS (
    SELECT 1 FROM u2a_session_agent_config
    WHERE id = :id_value
);

-- SessionConfigExistsBySessionId
SELECT EXISTS (
    SELECT 1 FROM u2a_session_agent_config
    WHERE session_id = :session_id_value
);