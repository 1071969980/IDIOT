-- CreateTable
CREATE TABLE  IF NOT EXISTS simple_users (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    user_name VARCHAR(255) NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    hashed_password TEXT NOT NULL,
    salt TEXT NOT NULL,
    UNIQUE (user_name)
);

-- InsertUser
INSERT INTO simple_users (user_name, hashed_password, salt)
VALUES (:user_name, :hashed_password, :salt)
RETURNING id;

-- UpdateUser1
UPDATE simple_users
SET :field_name_1 = :field_value_1
WHERE id = :id_value;

-- UpdateUser2
UPDATE simple_users
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2
WHERE id = :id_value;

-- UpdateUser3
UPDATE simple_users
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3
WHERE id = :id_value;

-- UpdateUser4
UPDATE simple_users
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3, :field_name_4 = :field_value_4
WHERE id = :id_value;

-- QueryUserIDByName
SELECT id
FROM simple_users
WHERE user_name = :user_name AND is_deleted = false;

-- QueryUser
SELECT *
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- QueryUserByUsername
SELECT *
FROM simple_users
WHERE user_name = :user_name AND is_deleted = false;

-- IsExists
SELECT COUNT(*)
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- QueryField1
SELECT :field_name_1
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- QueryField2
SELECT :field_name_1, :field_name_2
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- QueryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- QueryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM simple_users
WHERE id = :id_value AND is_deleted = false;

-- DeleteUser
UPDATE simple_users
SET is_deleted = true
WHERE id = :id_value AND is_deleted = false;

