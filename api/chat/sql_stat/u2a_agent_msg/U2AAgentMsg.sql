-- CreateAgentMessagesTable
CREATE TABLE IF NOT EXISTS u2a_agent_messages (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    sub_seq_index INT NOT NULL,
    message_type VARCHAR(32) NOT NULL CHECK (message_type IN ('text', 'tool', 'HIL', 'sub_session')),
    content TEXT NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('streaming', 'stop', 'complete', 'error')),
    session_task_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE
);

CREATE INDEX idx_u2a_agent_messages_session_id ON u2a_agent_messages (session_id);
CREATE INDEX idx_u2a_agent_messages_user_id ON u2a_agent_messages (user_id);
CREATE INDEX idx_u2a_agent_messages_status ON u2a_agent_messages (status);
CREATE INDEX idx_u2a_agent_messages_session_task_id ON u2a_agent_messages (session_task_id);

-- InsertAgentMessage
INSERT INTO u2a_agent_messages (user_id, session_id, sub_seq_index, message_type, content, status, session_task_id)
VALUES (:user_id, :session_id, :sub_seq_index, :message_type, :content, :status, :session_task_id)
RETURNING id;

-- UpdateAgentMessage1
UPDATE u2a_agent_messages
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateAgentMessage2
UPDATE u2a_agent_messages
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateAgentMessage3
UPDATE u2a_agent_messages
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateAgentMessageStatusByIds
UPDATE u2a_agent_messages
SET status = :status_value
WHERE id IN :ids_list;

-- UpdateAgentMessageSessionTaskByIds
UPDATE u2a_agent_messages
SET session_task_id = :session_task_id_value
WHERE id IN :ids_list;

-- QueryAgentMessageById
SELECT *
FROM u2a_agent_messages
WHERE id = :id_value;

-- QueryAgentMessagesBySession
SELECT *
FROM u2a_agent_messages
WHERE session_id = :session_id_value
ORDER BY sub_seq_index;

-- QueryAgentMessagesBySessionTask
SELECT *
FROM u2a_agent_messages
WHERE session_id = :session_id_value AND session_task_id = :session_task_id_value
ORDER BY sub_seq_index;

-- QueryAgentMessagesByUser
SELECT *
FROM u2a_agent_messages
WHERE user_id = :user_id_value
ORDER BY created_at;

-- AgentMessageExists
SELECT COUNT(*)
FROM u2a_agent_messages
WHERE id = :id_value;

-- QueryAgentMessageField1
SELECT :field_name_1
FROM u2a_agent_messages
WHERE id = :id_value;

-- QueryAgentMessageField2
SELECT :field_name_1, :field_name_2
FROM u2a_agent_messages
WHERE id = :id_value;

-- QueryAgentMessageField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_agent_messages
WHERE id = :id_value;

-- QueryAgentMessageField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_agent_messages
WHERE id = :id_value;

-- DeleteAgentMessage
DELETE FROM u2a_agent_messages
WHERE id = :id_value;

-- DeleteAgentMessagesBySession
DELETE FROM u2a_agent_messages
WHERE session_id = :session_id_value;

-- GetNextAgentMessageSubSeqIndex
SELECT COALESCE(MAX(sub_seq_index), -1) + 1 
FROM u2a_agent_messages
WHERE session_id = :session_id, session_task_id = :session_task_id;

-- CreateAgentMessageTriggers
CREATE OR REPLACE FUNCTION u2a_agent_msg_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION u2a_agent_msg_update_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE u2a_sessions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER u2a_agent_msg_before_insert
BEFORE INSERT ON u2a_agent_messages
FOR EACH ROW
EXECUTE FUNCTION u2a_agent_msg_update_timestamp();

CREATE OR REPLACE TRIGGER u2a_agent_msg_before_update
BEFORE UPDATE ON u2a_agent_messages
FOR EACH ROW
EXECUTE FUNCTION u2a_agent_msg_update_timestamp();

CREATE OR REPLACE TRIGGER u2a_agent_msg_after_insert
AFTER INSERT ON u2a_agent_messages
FOR EACH ROW
EXECUTE FUNCTION u2a_agent_msg_update_session_timestamp();

CREATE OR REPLACE TRIGGER u2a_agent_msg_after_update
AFTER UPDATE ON u2a_agent_messages
FOR EACH ROW
EXECUTE FUNCTION u2a_agent_msg_update_session_timestamp();