-- CreateSessionBranchesTable
CREATE EXTENSION IF NOT EXISTS ltree;
--
CREATE TABLE IF NOT EXISTS u2a_session_branches (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    name TEXT NOT NULL,
    created_by VARCHAR(32) NOT NULL CHECK (created_by IN ('user', 'agent', 'system')),
    archived BOOLEAN DEFAULT FALSE,
    leaf_task_id UUID NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (leaf_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE,
    UNIQUE (session_id, name)
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_branches_session_id ON u2a_session_branches (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_branches_leaf_task_id ON u2a_session_branches (leaf_task_id);

-- CreateSessionBranchTriggers
CREATE OR REPLACE FUNCTION u2a_session_branch_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER u2a_session_branch_before_insert
BEFORE INSERT ON u2a_session_branches
FOR EACH ROW
EXECUTE FUNCTION u2a_session_branch_update_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_branch_before_update
BEFORE UPDATE ON u2a_session_branches
FOR EACH ROW
EXECUTE FUNCTION u2a_session_branch_update_timestamp();

-- InsertSessionBranch
INSERT INTO u2a_session_branches (session_id, name, created_by, leaf_task_id)
VALUES (:session_id, :name, :created_by, :leaf_task_id)
RETURNING id;

-- QuerySessionBranchById
SELECT *
FROM u2a_session_branches
WHERE id = :id_value;

-- QuerySessionBranchBySessionAndName
SELECT *
FROM u2a_session_branches
WHERE session_id = :session_id_value AND name = :name_value;

-- QuerySessionBranchesBySession
SELECT *
FROM u2a_session_branches
WHERE session_id = :session_id_value
ORDER BY created_at;

-- QuerySessionBranchByLeafTaskId
SELECT *
FROM u2a_session_branches
WHERE leaf_task_id = :leaf_task_id_value;

-- SessionBranchExists
SELECT COUNT(*)
FROM u2a_session_branches
WHERE id = :id_value;

-- UpdateSessionBranchLeafTask
UPDATE u2a_session_branches
SET leaf_task_id = :leaf_task_id_value
WHERE id = :id_value;

-- UpdateSessionBranchArchived
UPDATE u2a_session_branches
SET archived = :archived_value
WHERE id = :id_value;

-- DeleteSessionBranch
DELETE FROM u2a_session_branches
WHERE id = :id_value;

-- DeleteSessionBranchesBySession
DELETE FROM u2a_session_branches
WHERE session_id = :session_id_value;

-- QueryBranchesWithStatus
WITH session_tasks AS (
    SELECT id, tree_path, status, parent_task_id, session_id
    FROM u2a_session_tasks
    WHERE session_id = :session_id_value
),
branch_base AS (
    SELECT
        b.id AS branch_id,
        b.name,
        b.created_by,
        b.archived,
        b.leaf_task_id,
        b.created_at,
        b.updated_at,
        leaf.status AS leaf_status,
        leaf.parent_task_id AS leaf_parent_id,
        leaf.tree_path AS leaf_path
    FROM u2a_session_branches b
    JOIN session_tasks leaf ON leaf.id = b.leaf_task_id
    WHERE b.session_id = :session_id_value
),
branch_key_tasks AS (
    SELECT bb.branch_id, bb.leaf_task_id AS task_id, bb.leaf_status AS status
    FROM branch_base bb
    UNION ALL
    SELECT bb.branch_id, pt.id, pt.status
    FROM branch_base bb
    JOIN session_tasks pt ON pt.id = bb.leaf_parent_id
),
branch_has_processing AS (
    SELECT DISTINCT branch_id, TRUE AS flag
    FROM branch_key_tasks
    WHERE status = 'processing'
),
branch_has_pending AS (
    SELECT DISTINCT branch_id, TRUE AS flag
    FROM branch_key_tasks
    WHERE status = 'pending'
),
branch_has_unprocessed AS (
    SELECT DISTINCT bkt.branch_id, TRUE AS flag
    FROM branch_key_tasks bkt
    JOIN u2a_user_messages um ON um.session_task_id = bkt.task_id
    WHERE um.status = 'waiting_agent_ack_user'
      AND um.session_id = :session_id_value
),
latest_terminal AS (
    SELECT bb.branch_id, lt.last_terminal_status
    FROM branch_base bb
    LEFT JOIN LATERAL (
        SELECT t.status AS last_terminal_status
        FROM u2a_session_tasks t
        WHERE t.session_id = :session_id_value
          AND t.tree_path @> bb.leaf_path
          AND t.status NOT IN ('pending', 'processing')
        ORDER BY t.tree_path DESC
        LIMIT 1
    ) lt ON TRUE
)
SELECT
    bb.branch_id,
    bb.name,
    bb.created_by,
    bb.archived,
    bb.leaf_task_id,
    bb.created_at,
    bb.updated_at,
    COALESCE(bhp.flag, FALSE) AS has_processing_task,
    COALESCE(bhpe.flag, FALSE) AS has_pending_task,
    COALESCE(bhu.flag, FALSE) AS has_unprocessed_messages,
    lt.last_terminal_status
FROM branch_base bb
LEFT JOIN branch_has_processing bhp ON bb.branch_id = bhp.branch_id
LEFT JOIN branch_has_pending bhpe ON bb.branch_id = bhpe.branch_id
LEFT JOIN branch_has_unprocessed bhu ON bb.branch_id = bhu.branch_id
LEFT JOIN latest_terminal lt ON bb.branch_id = lt.branch_id
ORDER BY bb.created_at;
