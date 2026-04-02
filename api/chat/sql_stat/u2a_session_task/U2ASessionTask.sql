-- CreateSessionTasksTable
CREATE EXTENSION IF NOT EXISTS ltree;
--
CREATE TABLE IF NOT EXISTS u2a_session_tasks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    parent_task_id UUID,
    branch_id UUID,
    seq_in_session INT NOT NULL DEFAULT 0,
    tree_path ltree NOT NULL,
    context_breakpoints INT[] DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (branch_id) REFERENCES u2a_session_branches(id) ON DELETE SET NULL
);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_session_id ON u2a_session_tasks (session_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_user_id ON u2a_session_tasks (user_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_status ON u2a_session_tasks (status);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_tree_path ON u2a_session_tasks USING GIST (tree_path);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_parent_task_id ON u2a_session_tasks (parent_task_id);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_branch_id ON u2a_session_tasks (branch_id);

-- InsertSessionTask
INSERT INTO u2a_session_tasks (session_id, user_id, status, parent_task_id, branch_id, seq_in_session, tree_path, context_breakpoints)
VALUES (:session_id, :user_id, :status, :parent_task_id, :branch_id, :seq_in_session, :tree_path, :context_breakpoints)
RETURNING id;

-- UpdateSessionTaskStatus
UPDATE u2a_session_tasks
SET status = :status_value
WHERE id = :id_value;

-- UpdateSessionTaskBranchId
UPDATE u2a_session_tasks
SET branch_id = :branch_id_value
WHERE id = :id_value;

-- UpdateSessionTaskContextBreakpoints
UPDATE u2a_session_tasks
SET context_breakpoints = :context_breakpoints_value
WHERE id = :id_value;

-- QuerySessionTaskById
SELECT *
FROM u2a_session_tasks
WHERE id = :id_value;

-- QuerySessionTasksBySession
SELECT *
FROM u2a_session_tasks
WHERE session_id = :session_id_value
ORDER BY created_at;

-- QuerySessionTaskBySessionAndStatus
SELECT *
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value

-- QuerySessionTasksByUser
SELECT *
FROM u2a_session_tasks
WHERE user_id = :user_id_value
ORDER BY created_at;

-- GetNextSeqInSession
SELECT COALESCE(MAX(seq_in_session), -1) + 1
FROM u2a_session_tasks
WHERE session_id = :session_id_value;

-- QuerySessionTasksByBranchPath
SELECT t.*
FROM u2a_session_tasks t
JOIN u2a_session_tasks leaf ON leaf.id = :leaf_task_id_value
WHERE t.tree_path @> leaf.tree_path
  AND t.session_id = leaf.session_id
ORDER BY t.seq_in_session ASC;

-- QuerySessionTasksByBranchPathUntilBreakPoint
WITH leaf_info AS (
    SELECT tree_path, session_id FROM u2a_session_tasks WHERE id = :leaf_task_id_value
),
breakpoint_task AS (
    SELECT t.tree_path
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.tree_path @> l.tree_path
      AND t.session_id = l.session_id
      AND COALESCE(t.context_breakpoints, '{}') <> '{}'::int[]
    ORDER BY nlevel(t.tree_path) DESC
    LIMIT 1
)
SELECT t.*
FROM u2a_session_tasks t, leaf_info l
WHERE t.tree_path @> l.tree_path
  AND t.session_id = l.session_id
  AND (
    NOT EXISTS (SELECT 1 FROM breakpoint_task)
    OR t.tree_path <@ (SELECT tree_path FROM breakpoint_task)
  )
ORDER BY t.seq_in_session ASC;

-- QueryChildTasksByParentId
SELECT *
FROM u2a_session_tasks
WHERE parent_task_id = :parent_task_id_value
ORDER BY seq_in_session;

-- QuerySessionTaskTreePath
SELECT tree_path
FROM u2a_session_tasks
WHERE id = :id_value;

-- SessionTaskExists
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE id = :id_value;

-- DeleteSessionTask
DELETE FROM u2a_session_tasks
WHERE id = :id_value;

-- DeleteSessionTasksBySession
DELETE FROM u2a_session_tasks
WHERE session_id = :session_id_value;

-- CheckSessionHasTaskWithStatus
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status = :status_value;

-- CheckSessionHasTaskWithStatuses
SELECT COUNT(*)
FROM u2a_session_tasks
WHERE session_id = :session_id_value AND status IN (:status_values);

-- GetSessionTaskStatusCounts
SELECT status, COUNT(*) as count
FROM u2a_session_tasks
WHERE session_id = :session_id_value
GROUP BY status;

-- CreateSessionTaskTriggers
CREATE OR REPLACE FUNCTION u2a_session_task_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE FUNCTION u2a_session_task_update_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE u2a_sessions
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
--
CREATE OR REPLACE TRIGGER u2a_session_task_before_insert
BEFORE INSERT ON u2a_session_tasks
FOR EACH ROW
EXECUTE FUNCTION u2a_session_task_update_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_task_before_update
BEFORE UPDATE ON u2a_session_tasks
FOR EACH ROW
EXECUTE FUNCTION u2a_session_task_update_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_task_after_insert
AFTER INSERT ON u2a_session_tasks
FOR EACH ROW
EXECUTE FUNCTION u2a_session_task_update_session_timestamp();
--
CREATE OR REPLACE TRIGGER u2a_session_task_after_update
AFTER UPDATE ON u2a_session_tasks
FOR EACH ROW
EXECUTE FUNCTION u2a_session_task_update_session_timestamp();
