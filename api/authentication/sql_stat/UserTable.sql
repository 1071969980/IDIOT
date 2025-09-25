-- CreateTable
CREATE TABLE  IF NOT EXISTS simple_users (
    id INTEGER NOT NULL,
    uuid VARCHAR(36) NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    create_time TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    hashed_password TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (uuid)
);

-- InsertUser
INSERT INTO simple_users (uuid, user_name, create_time, is_deleted, hashed_password) 
VALUES (:uuid, :user_name, :create_time, :is_deleted, :hashed_password);

-- UpdateUser1
UPDATE simple_users 
SET :field_name_1 = :field_value_1
WHERE uuid = :uuid_value;

-- UpdateUser2
UPDATE simple_users 
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2,
WHERE uuid = :uuid_value;

-- UpdateUser3
UPDATE simple_users 
SET :field_name_1 = :field_value_1, :field_name_2 = :field_value_2, :field_name_3 = :field_value_3,
WHERE uuid = :uuid_value;

-- QueryUser
SELECT *
FROM simple_users 
WHERE uuid = :uuid_value AND is_deleted = false;

-- IsExists
SELECT COUNT(*) 
FROM simple_users 
WHERE uuid = :uuid_value AND is_deleted = false;

-- QueryField1
SELECT :field_name_1
FROM simple_users 
WHERE uuid = :uuid_value AND is_deleted = false;

-- QueryField2
SELECT :field_name_1, :field_name_2
FROM simple_users 
WHERE uuid = :uuid_value AND is_deleted = false;

-- QueryField3
SELECT :field_name_1, :field_name_2, :field_name_3
FROM simple_users 
WHERE uuid = :uuid_value AND is_deleted = false;

-- QueryField4
SELECT :field_name_1, :field_name_2, :field_name_3, :field_name_4
FROM simple_users
WHERE uuid = :uuid_value AND is_deleted = false;

-- DeleteUser
UPDATE simple_users
SET is_deleted = true
WHERE uuid = :uuid_value AND is_deleted = false;

