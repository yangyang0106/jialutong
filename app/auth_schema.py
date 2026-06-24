AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS families (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  wechat_openid TEXT UNIQUE,
  display_name TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS family_members (
  id TEXT PRIMARY KEY,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('FAMILY_ADMIN', 'FAMILY_MEMBER', 'GUARDIAN', 'ELDER_USER')),
  relation TEXT NOT NULL DEFAULT '家属',
  status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'DISABLED')) DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(family_id, user_id)
);

CREATE TABLE IF NOT EXISTS elders (
  id TEXT PRIMARY KEY,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'DISABLED')) DEFAULT 'ACTIVE',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_elder_bindings (
  id TEXT PRIMARY KEY,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT '家属',
  can_manage_routes INTEGER NOT NULL DEFAULT 0,
  can_receive_help INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, elder_id)
);

CREATE TABLE IF NOT EXISTS elder_bind_codes (
  code TEXT PRIMARY KEY,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
  created_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT '本人',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT NOT NULL DEFAULT '',
  used_by_user_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS emergency_contacts (
  id TEXT PRIMARY KEY,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  elder_id TEXT NOT NULL REFERENCES elders(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  family_id TEXT NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_family_members_user_id ON family_members(user_id);
CREATE INDEX IF NOT EXISTS idx_family_members_family_id ON family_members(family_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_elders_family_id ON elders(family_id);
CREATE INDEX IF NOT EXISTS idx_bindings_family_id ON user_elder_bindings(family_id);
CREATE INDEX IF NOT EXISTS idx_contacts_elder_id ON emergency_contacts(elder_id);
"""
