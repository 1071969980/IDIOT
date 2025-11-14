-- CreateAgentShortTermMemoryTable
CREATE TABLE IF NOT EXISTS u2a_agent_short_term_memory (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    sub_seq_index INT NOT NULL,
    content JSONB NOT NULL,
    session_task_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_agent_short_term_memory_session_id ON u2a_agent_short_term_memory (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_agent_short_term_memory_user_id ON u2a_agent_short_term_memory (user_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_agent_short_term_memory_session_task_id ON u2a_agent_short_term_memory (session_task_id);

-- InsertAgentShortTermMemory
INSERT INTO u2a_agent_short_term_memory (user_id, session_id, sub_seq_index, content, session_task_id)
VALUES (:user_id, :session_id, :sub_seq_index, :content, :session_task_id)
RETURNING id;

-- InsertAgentShortTermMemoriesBatch
INSERT INTO u2a_agent_short_term_memory (user_id, session_id, sub_seq_index, content, session_task_id)
SELECT
    unnest(:user_ids_list) as user_id,
    unnest(:session_ids_list) as session_id,
    unnest(:sub_seq_indices_list) as sub_seq_index,
    unnest(:contents_list) as content,
    unnest(:session_task_ids_list) as session_task_id
RETURNING id;

-- UpdateAgentShortTermMemory1
UPDATE u2a_agent_short_term_memory
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateAgentShortTermMemory2
UPDATE u2a_agent_short_term_memory
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateAgentShortTermMemory3
UPDATE u2a_agent_short_term_memory
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateAgentShortTermMemorySessionTaskByIds
UPDATE u2a_agent_short_term_memory
SET session_task_id = :session_task_id_value
WHERE id IN (:ids_list);


-- QueryAgentShortTermMemoryById
SELECT *
FROM u2a_agent_short_term_memory
WHERE id = :id_value;


-- QueryAgentShortTermMemoryBySession
SELECT *
FROM u2a_agent_short_term_memory
WHERE session_id = :session_id_value

-- QueryAgentShortTermMemoryBySessionTask
SELECT *
FROM u2a_agent_short_term_memory
WHERE session_task_id = :session_task_id_value
ORDER BY sub_seq_index;

-- QueryAgentShortTermMemoryByAgent
SELECT *
FROM u2a_agent_short_term_memory
WHERE user_id = :user_id_value
ORDER BY created_at;

-- AgentShortTermMemoryExists
SELECT COUNT(*)
FROM u2a_agent_short_term_memory
WHERE id = :id_value;


-- QueryAgentShortTermMemoryField1
SELECT :field_name_1
FROM u2a_agent_short_term_memory
WHERE id = :id_value;

-- QueryAgentShortTermMemoryField2
SELECT :field_name_1, :field_name_2
FROM u2a_agent_short_term_memory
WHERE id = :id_value;

-- QueryAgentShortTermMemoryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM u2a_agent_short_term_memory
WHERE id = :id_value;

-- QueryAgentShortTermMemoryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM u2a_agent_short_term_memory
WHERE id = :id_value;

-- DeleteAgentShortTermMemory
DELETE FROM u2a_agent_short_term_memory
WHERE id = :id_value;

-- DeleteAgentShortTermMemoryBySession
DELETE FROM u2a_agent_short_term_memory
WHERE session_id = :session_id_value;

-- DeleteAgentShortTermMemoryBySessionTask
DELETE FROM u2a_agent_short_term_memory
WHERE session_task_id = :session_task_id_value;

-- GetNextAgentShortTermMemorySubSeqIndex
SELECT COALESCE(MAX(sub_seq_index), -1) + 1 FROM u2a_agent_short_term_memory WHERE session_id = :session_id AND session_task_id = :session_task_id;
