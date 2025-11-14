-- CreateTable
CREATE TABLE IF NOT EXISTS a2a_A_side_agent_short_term_memory (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    session_task_id UUID NOT NULL,
    seq_index INT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES a2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES a2a_session_tasks(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_a2a_A_side_agent_short_term_memory_session_id ON a2a_A_side_agent_short_term_memory (session_id);
--
CREATE TABLE IF NOT EXISTS a2a_B_side_agent_short_term_memory (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    session_task_id UUID NOT NULL,
    seq_index INT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES a2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (session_task_id) REFERENCES a2a_session_tasks(id) ON DELETE CASCADE
);
--
CREATE INDEX IF NOT EXISTS idx_a2a_B_side_agent_short_term_memory_session_id ON a2a_B_side_agent_short_term_memory (session_id);

-- InsertMemory
INSERT INTO :table_name (session_id, session_task_id, seq_index, content)
VALUES (:session_id, :session_task_id, :seq_index, :content)
RETURNING id;

-- InsertMemoriesBatch
INSERT INTO :table_name (session_id, session_task_id, seq_index, content)
SELECT
    unnest(:session_ids_list) as session_id,
    unnest(:session_task_ids_list) as session_task_id,
    unnest(:seq_indices_list) as seq_index,
    unnest(:contents_list) as content
RETURNING id;

-- UpdateMemory1
UPDATE :table_name
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateMemory2
UPDATE :table_name
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateMemory3
UPDATE :table_name
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateMemorySessionTaskByIds
UPDATE :table_name
SET session_task_id = :session_task_id_value
WHERE id IN (:ids_list);

-- QueryMemoryById
SELECT *
FROM :table_name
WHERE id = :id_value;

-- QueryMemoryBySession
SELECT *
FROM :table_name
WHERE session_id = :session_id_value
ORDER BY seq_index;

-- QueryMemoryBySessionTask
SELECT *
FROM :table_name
WHERE session_task_id = :session_task_id_value
ORDER BY seq_index;

-- QueryMemoryBySessionAndTask
SELECT *
FROM :table_name
WHERE session_id = :session_id_value AND session_task_id = :session_task_id_value
ORDER BY seq_index;

-- MemoryExists
SELECT COUNT(*)
FROM :table_name
WHERE id = :id_value;

-- QueryMemoryField1
SELECT :field_name_1
FROM :table_name
WHERE id = :id_value;

-- QueryMemoryField2
SELECT :field_name_1, :field_name_2
FROM :table_name
WHERE id = :id_value;

-- QueryMemoryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM :table_name
WHERE id = :id_value;

-- QueryMemoryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM :table_name
WHERE id = :id_value;

-- DeleteMemory
DELETE FROM :table_name
WHERE id = :id_value;

-- DeleteMemoryBySession
DELETE FROM :table_name
WHERE session_id = :session_id_value;

-- DeleteMemoryBySessionTask
DELETE FROM :table_name
WHERE session_task_id = :session_task_id_value;

-- DeleteMemoryBySessionAndTask
DELETE FROM :table_name
WHERE session_id = :session_id_value AND session_task_id = :session_task_id_value;

-- GetNextSeqIndex
SELECT COALESCE(MAX(seq_index), -1) + 1
FROM :table_name
WHERE session_id = :session_id AND session_task_id = :session_task_id;

