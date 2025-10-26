-- CreatTable
CREATE TABLE IF NOT EXISTS a2a_session_A_side_msg (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    session_task_id UUID NOT NULL,
    seq_index INT NOT NULL,
    message_type VARCHAR(32) NOT NULL CHECK (message_type IN ('text', 'tool_call', 'agent_msg_as_user')),
    content TEXT NOT NULL,
    json_content JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES a2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES a2a_session_tasks(id) ON DELETE CASCADE
);

CREATE INDEX idx_a2a_session_A_side_msg_session_id ON a2a_session_A_side_msg (session_id);

CREATE TABLE IF NOT EXISTS a2a_session_B_side_msg (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    session_task_id UUID,
    seq_index INT NOT NULL,
    message_type VARCHAR(32) NOT NULL CHECK (message_type IN ('text', 'tool_call', 'agent_msg_as_user')),
    content TEXT NOT NULL,
    json_content JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES a2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES a2a_session_tasks(id) ON DELETE CASCADE
);

-- InsertSideMessage
INSERT INTO :table_name (session_id, session_task_id, seq_index, message_type, content, json_content)
VALUES (:session_id, :session_task_id, :seq_index, :message_type, :content, :json_content)
RETURNING id;

-- InsertSideMessagesBatch
INSERT INTO :table_name (session_id, session_task_id, seq_index, message_type, content, json_content)
SELECT
    unnest(:session_ids_list) as session_id,
    unnest(:session_task_ids_list) as session_task_id,
    unnest(:seq_indices_list) as seq_index,
    unnest(:message_types_list) as message_type,
    unnest(:contents_list) as content,
    unnest(:json_contents_list) as json_content
RETURNING id;

-- UpdateSideMessage1
UPDATE :table_name
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateSideMessage2
UPDATE :table_name
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateSideMessage3
UPDATE :table_name
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateSideMessageSessionTaskByIds
UPDATE :table_name
SET session_task_id = :session_task_id_value
WHERE id IN :ids_list;

-- QuerySideMessageById
SELECT *
FROM :table_name
WHERE id = :id_value;

-- QuerySideMessagesBySession
SELECT *
FROM :table_name
WHERE session_id = :session_id_value
ORDER BY seq_index;

-- QuerySideMessagesBySessionTask
SELECT *
FROM :table_name
WHERE session_task_id = :session_task_id_value
ORDER BY seq_index;

-- SideMessageExists
SELECT COUNT(*)
FROM :table_name
WHERE id = :id_value;

-- QuerySideMessageField1
SELECT :field_name_1
FROM :table_name
WHERE id = :id_value;

-- QuerySideMessageField2
SELECT :field_name_1, :field_name_2
FROM :table_name
WHERE id = :id_value;

-- QuerySideMessageField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM :table_name
WHERE id = :id_value;

-- QuerySideMessageField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM :table_name
WHERE id = :id_value;

-- DeleteSideMessage
DELETE FROM :table_name
WHERE id = :id_value;

-- DeleteSideMessagesBySession
DELETE FROM :table_name
WHERE session_id = :session_id_value;

-- DeleteSideMessagesBySessionTask
DELETE FROM :table_name
WHERE session_task_id = :session_task_id_value;

-- GetNextSideMessageSeqIndex
SELECT COALESCE(MAX(seq_index), -1) + 1
FROM :table_name
WHERE session_id = :session_id;