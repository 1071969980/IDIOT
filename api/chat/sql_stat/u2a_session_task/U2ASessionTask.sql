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
    storage_snapshot JSONB DEFAULT NULL,
    logic_mark JSONB DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE
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
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_storage_snapshot ON u2a_session_tasks USING GIN (storage_snapshot);
--
CREATE INDEX IF NOT EXISTS idx_u2a_session_tasks_logic_mark ON u2a_session_tasks USING GIN (logic_mark);

-- InsertSessionTask
INSERT INTO u2a_session_tasks (session_id, user_id, status, parent_task_id, branch_id, seq_in_session, tree_path, context_breakpoints, storage_snapshot, logic_mark)
VALUES (:session_id, :user_id, :status, :parent_task_id, :branch_id, :seq_in_session, :tree_path, :context_breakpoints, :storage_snapshot, :logic_mark)
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

-- QueryAncestorsByLeafTaskAndStatuses
SELECT t.id, t.session_id, t.user_id, t.status, t.parent_task_id, t.branch_id,
       t.seq_in_session, t.tree_path, t.context_breakpoints, t.storage_snapshot, t.logic_mark,
       t.created_at, t.updated_at
FROM u2a_session_tasks t
JOIN u2a_session_tasks leaf ON leaf.id = :leaf_task_id_value
WHERE t.tree_path @> leaf.tree_path
  AND t.session_id = leaf.session_id
  AND t.status IN (:status_values)
ORDER BY t.seq_in_session ASC;

-- DeprecatedQuerySessionTasksByBranchPathUntilBreakPoint
WITH leaf_info AS (
    SELECT tree_path, session_id FROM u2a_session_tasks WHERE id = :leaf_task_id_value
),
path_nodes AS (
    SELECT t.*,
           MAX(CASE WHEN COALESCE(t.context_breakpoints, '{}') <> '{}'::int[]
                    THEN t.seq_in_session END) OVER () AS bp_seq
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.tree_path @> l.tree_path
      AND t.session_id = l.session_id
)
SELECT id, session_id, user_id, status, parent_task_id, branch_id,
       seq_in_session, tree_path, context_breakpoints, storage_snapshot, logic_mark,
       created_at, updated_at
FROM path_nodes
WHERE bp_seq IS NULL OR seq_in_session >= bp_seq
ORDER BY seq_in_session ASC;

-- QuerySessionTasksByBranchPathUntilBreakPoint
WITH leaf_info AS (
    SELECT tree_path, session_id FROM u2a_session_tasks WHERE id = :leaf_task_id_value
),
bp AS (
    SELECT MAX(t.seq_in_session) AS bp_seq
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.tree_path @> l.tree_path
      AND t.session_id = l.session_id
      AND COALESCE(t.context_breakpoints, '{}') <> '{}'::int[]
)
SELECT t.id, t.session_id, t.user_id, t.status, t.parent_task_id, t.branch_id,
       t.seq_in_session, t.tree_path, t.context_breakpoints, t.storage_snapshot, t.logic_mark,
       t.created_at, t.updated_at
FROM u2a_session_tasks t, leaf_info l, bp
WHERE t.tree_path @> l.tree_path
  AND t.session_id = l.session_id
  AND (bp.bp_seq IS NULL OR t.seq_in_session >= bp.bp_seq)
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

-- UpdateSessionTaskStorageSnapshot
UPDATE u2a_session_tasks
SET storage_snapshot = :storage_snapshot_value
WHERE id = :id_value AND status = 'pending';

-- QueryNearestAncestorStorageSnapshot
WITH leaf_info AS (
    SELECT tree_path, session_id, parent_task_id FROM u2a_session_tasks WHERE id = :task_id_value
),
parent_check AS (
    SELECT t.storage_snapshot, t.seq_in_session
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.id = l.parent_task_id
      AND t.storage_snapshot IS NOT NULL
    LIMIT 1
)
SELECT storage_snapshot FROM (
    SELECT storage_snapshot, seq_in_session FROM parent_check
    UNION ALL
    SELECT t.storage_snapshot, t.seq_in_session
    FROM u2a_session_tasks t, leaf_info l
    WHERE NOT EXISTS (SELECT 1 FROM parent_check)
      AND t.tree_path @> l.tree_path
      AND t.session_id = l.session_id
      AND t.storage_snapshot IS NOT NULL
) sub
ORDER BY seq_in_session DESC
LIMIT 1;

-- CopyStorageSnapshotFromNearestAncestor
WITH leaf_info AS (
    SELECT tree_path, session_id, parent_task_id FROM u2a_session_tasks WHERE id = :task_id_value
),
parent_check AS (
    SELECT t.storage_snapshot
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.id = l.parent_task_id
      AND t.storage_snapshot IS NOT NULL
    LIMIT 1
),
nearest_ancestor AS (
    SELECT storage_snapshot FROM (
        SELECT storage_snapshot FROM parent_check
        UNION ALL
        (
            SELECT t.storage_snapshot
            FROM u2a_session_tasks t, leaf_info l
            WHERE NOT EXISTS (SELECT 1 FROM parent_check)
              AND t.tree_path @> l.tree_path
              AND t.session_id = l.session_id
              AND t.storage_snapshot IS NOT NULL
            ORDER BY t.seq_in_session DESC
            LIMIT 1
        )
    ) sub
    LIMIT 1
)
UPDATE u2a_session_tasks a
SET storage_snapshot = na.storage_snapshot
FROM nearest_ancestor na
WHERE a.id = :task_id_value;

-- UpdateSessionTaskLogicMark
UPDATE u2a_session_tasks
SET logic_mark = :logic_mark_value
WHERE id = :id_value;

-- QuerySessionTaskLogicMarkField
SELECT logic_mark->:field_key
FROM u2a_session_tasks
WHERE id = :id_value;

-- UpdateSessionTaskLogicMarkField
UPDATE u2a_session_tasks
SET logic_mark = COALESCE(logic_mark, '{}') || jsonb_build_object(:field_key, :field_value)
WHERE id = :id_value;

-- QueryBranchPathUntilLogicMark
WITH leaf_info AS (
    SELECT tree_path, session_id FROM u2a_session_tasks WHERE id = :leaf_task_id_value
),
mark_ancestor AS (
    SELECT MAX(t.seq_in_session) AS mark_seq
    FROM u2a_session_tasks t, leaf_info l
    WHERE t.tree_path @> l.tree_path
      AND t.session_id = l.session_id
      AND t.logic_mark ? :mark_key
)
SELECT t.id, t.session_id, t.user_id, t.status, t.parent_task_id, t.branch_id,
       t.seq_in_session, t.tree_path, t.context_breakpoints, t.storage_snapshot, t.logic_mark,
       t.created_at, t.updated_at
FROM u2a_session_tasks t, leaf_info l, mark_ancestor ma
WHERE t.tree_path @> l.tree_path
  AND t.session_id = l.session_id
  AND (
      ma.mark_seq IS NOT NULL AND t.seq_in_session >= ma.mark_seq
      OR ma.mark_seq IS NULL AND :fallback_to_full_path
  )
ORDER BY t.seq_in_session ASC;

-- QueryNearestAncestorLogicMarkField
SELECT t.logic_mark->:mark_key AS field_value
FROM u2a_session_tasks leaf
JOIN u2a_session_tasks t ON t.tree_path @> leaf.tree_path AND t.session_id = leaf.session_id
WHERE leaf.id = :task_id_value
  AND t.logic_mark ? :mark_key
ORDER BY t.seq_in_session DESC
LIMIT 1;

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
