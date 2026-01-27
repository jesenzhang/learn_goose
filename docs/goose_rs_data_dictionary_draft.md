# Goose-rs Data Dictionary (Stage B Draft)

This dictionary maps database columns to Rust structs used in goose-rs phase B, with notes for how they align to stage C/D.

## Core tables

### sessions
- id: TEXT, PRIMARY KEY, NOT NULL
- name: TEXT
- description: TEXT
- user_set_name: BOOLEAN
- session_type: TEXT NOT NULL, default 'user'
- working_dir: TEXT
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
- extension_data: TEXT
- total_tokens: INTEGER
- input_tokens: INTEGER
- output_tokens: INTEGER
- accumulated_total_tokens: INTEGER
- accumulated_input_tokens: INTEGER
- accumulated_output_tokens: INTEGER
- schedule_id: TEXT
- recipe_json: TEXT
- user_recipe_values_json: TEXT
- provider_name: TEXT
- model_config_json: TEXT
Indexes: idx_sessions_type (session_type)

Rust fields:
- id -> Session.id (String)
- name -> Session.name (String)
- description -> Session.description (String)
- user_set_name -> Session.user_set_name (bool)
- session_type -> Session.session_type (SessionType)
- working_dir -> Session.working_dir (PathBuf)
- created_at -> Session.created_at (DateTime<Utc>)
- updated_at -> Session.updated_at (DateTime<Utc>)
- extension_data -> Session.extension_data (ExtensionData; serialized)
- total_tokens -> Session.total_tokens (Option<i32>)
- input_tokens -> Session.input_tokens (Option<i32>)
- output_tokens -> Session.output_tokens (Option<i32>)
- accumulated_total_tokens -> Session.accumulated_total_tokens (Option<i32>)
- accumulated_input_tokens -> Session.accumulated_input_tokens (Option<i32>)
- accumulated_output_tokens -> Session.accumulated_output_tokens (Option<i32>)
- schedule_id -> Session.schedule_id (Option<String>)
- recipe_json -> Session.recipe_json (Option<String>)
- user_recipe_values_json -> Session.user_recipe_values_json (Option<String>)
- provider_name -> Session.provider_name (Option<String>)
- model_config_json -> Session.model_config_json (Option<String>)

### messages
- id: INTEGER PRIMARY KEY AUTOINCREMENT
- session_id: TEXT NOT NULL, FOREIGN KEY REFERENCES sessions(id)
- role: TEXT NOT NULL
- content_json: TEXT NOT NULL
- created_timestamp: INTEGER NOT NULL
- timestamp: TIMESTAMP
- tokens: INTEGER
- metadata_json: TEXT
Indexes: idx_messages_session (session_id), idx_messages_timestamp (timestamp)

Rust fields:
- id -> Message.id (Option<String>)
- session_id -> Message.session_id (String)
- role -> Message.role (Role)
- content_json -> Message.content_json (Vec<MessageContent> serialized to JSON)
- created_timestamp -> Message.created (i64)
- timestamp -> Message.timestamp (DateTime or NaiveDateTime in storage)
- tokens -> Message.tokens (if used) (Option<i32>)
- metadata_json -> Message.metadata (MessageMetadata serialized)

### schema_version
- version: INTEGER PRIMARY KEY
- applied_at: TIMESTAMP

Rust mapping:
- version -> schema_version.version (i32)
- applied_at -> DateTime<Utc>

## Notes on JSON fields
- content_json stores a JSON-serialized array of MessageContent, with variants defined in MessageContent enum.
- metadata_json stores a JSON-serialized MessageMetadata struct.

## Migration planning (Stage D references)
- v1: create schema_version table
- v2: add sessions.user_recipe_values_json
- v3: add messages.metadata_json
- v4: add sessions.name, sessions.user_set_name
- v5: add sessions.session_type and index idx_sessions_type
- v6: add sessions.provider_name and sessions.model_config_json

## Data types map (Rust ↔ DB)
- String -> TEXT
- bool -> BOOLEAN
- i64/DateTime<Utc> -> TIMESTAMP or INTEGER depending on field
- Vec<T> serialized to JSON in TEXT fields
- Option<T> represented as NULLABLE columns
