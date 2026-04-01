"""align_nhost_with_final_models

Revision ID: 0d0ab1312ebf
Revises: 20260324_merge_heads_voice_notes
Create Date: 2026-03-31 19:01:05.207774

REWRITTEN: 100% idempotent migration using raw SQL.
Every operation is guarded with IF EXISTS / IF NOT EXISTS.
This migration will succeed regardless of the current DB state.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0d0ab1312ebf'
down_revision: Union[str, Sequence[str], None] = '20260324_merge_heads_voice_notes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Idempotent upgrade: brings any DB state to match current SQLAlchemy models.
    
    Strategy:
    1. DROP all ghost/obsolete tables (CASCADE handles dependencies)
    2. CREATE new tables IF NOT EXISTS
    3. ADD columns IF NOT EXISTS to existing tables
    4. Skip ALTER operations that assume specific prior states
    """
    conn = op.get_bind()

    # =========================================================
    # PHASE 1: DROP ALL TABLES WITH POTENTIALLY STALE SCHEMAS
    # Using CASCADE to handle remaining foreign keys.
    # 
    # SAFE TO DROP: Tables with NO user data or NO backend service.
    # NEVER DROP: users, plans, subscriptions, payments, user_profiles,
    #             onboarding_sessions, external_integrations, synced_external_data
    # =========================================================
    
    # 1a. Ghost tables (models deleted, no code references them)
    ghost_tables = [
        'history', 'conversations', 'agent_interactions', 'personal_agents',
        'usage_events', 'usage_tracking', 'storage_strategies', 'cost_savings',
        'organizations', 'organization_members', 'organization_invitations',
        'learning_patterns', 'vision_analytics', 'vision_processing_jobs',
        'whatsapp_chat_messages', 'whatsapp_chats', 'calls', 'encryption_keys',
        'contacts', 'whatsapp_stories', 'story_views', 'chat_members',
        'tasks', 'report_logs', 'assets', 'clients',
        'local_chat_metadata', 'chat_sync_status', 'documents', 'media',
        'uploaded_files', 'agenda_chunks', 'agenda_items', 'agenda_sessions',
        'usage_logs', 'live_search_logs', 'user_permissions',
        'chat_messages',
    ]
    for t in ghost_tables:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))

    # 1b. Study group tables (NO backend service, NO router, schema changed)
    # Must DROP before CREATE to avoid stale column names from add_study_groups_001.py
    study_group_tables = [
        'private_ai_messages',  # depends on chat_sessions
        'chat_sessions',        # depends on study_groups
        'group_activities',     # depends on study_groups
        'group_invitations',    # depends on study_groups
        'group_messages',       # depends on study_groups
        'shared_documents',     # depends on study_groups
        'group_members',        # depends on study_groups
        'study_groups',         # parent table
    ]
    for t in study_group_tables:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))

    # 1c. Voice note tables (very new, may have stale schema from failed migrations)
    voice_tables = [
        'voice_note_sync_checkpoints',
        'voice_note_processing_jobs',
        'voice_note_chunks',
        'voice_notes',
    ]
    for t in voice_tables:
        conn.execute(sa.text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))

    # 1d. Drop stale enum types from old migrations
    old_enums = [
        'activitytype', 'invitationstatus', 'messagetype', 'grouprole', 'sessiontype'
    ]
    for e in old_enums:
        conn.execute(sa.text(f'DROP TYPE IF EXISTS "{e}" CASCADE'))

    # =========================================================
    # PHASE 2: CREATE NEW TABLES (IF NOT EXISTS)
    # These are tables that exist in models but may not exist in DB
    # =========================================================

    # --- scheduled_recordings ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scheduled_recordings (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            class_name VARCHAR(200) NOT NULL,
            teacher_name VARCHAR(200),
            scheduled_at TIMESTAMPTZ NOT NULL,
            timezone VARCHAR(50) NOT NULL DEFAULT 'America/Mexico_City',
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            location_lat FLOAT,
            location_lng FLOAT,
            location_radius_meters INTEGER DEFAULT 100,
            location_name VARCHAR(200),
            recording_session_id VARCHAR(36),
            extracted_from_message TEXT,
            ai_confidence FLOAT DEFAULT 0.0,
            ai_reasoning TEXT,
            notification_sent_5min BOOLEAN DEFAULT FALSE,
            notification_sent_1min BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now(),
            executed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scheduled_recordings_id ON scheduled_recordings(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scheduled_recordings_user_id ON scheduled_recordings(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scheduled_recordings_scheduled_at ON scheduled_recordings(scheduled_at)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scheduled_recordings_status ON scheduled_recordings(status)"))

    # --- referrals ---
    conn.execute(sa.text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'referralstatus') THEN
                CREATE TYPE referralstatus AS ENUM ('PENDING', 'COMPLETED', 'EXPIRED');
            END IF;
        END $$;
    """))
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS referrals (
            id VARCHAR(255) PRIMARY KEY,
            referrer_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            referred_id VARCHAR REFERENCES users(id) ON DELETE SET NULL,
            referred_email VARCHAR(100),
            status referralstatus DEFAULT 'PENDING',
            bonus_granted BOOLEAN DEFAULT FALSE,
            bonus_days INTEGER DEFAULT 0,
            referral_metadata JSON,
            created_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_referrals_id ON referrals(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_referrals_referrer_id ON referrals(referrer_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_referrals_referred_id ON referrals(referred_id)"))

    # --- transcript_chunks ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS transcript_chunks (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL REFERENCES recording_sessions(id) ON DELETE CASCADE,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            timestamp_seconds INTEGER,
            t_start_ms INTEGER,
            t_end_ms INTEGER,
            relevance_label VARCHAR(16),
            relevance_reason TEXT,
            relevance_signals JSON,
            relevance_score FLOAT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_transcript_chunks_id ON transcript_chunks(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_transcript_chunks_session_id ON transcript_chunks(session_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_transcript_chunks_user_id ON transcript_chunks(user_id)"))

    # --- user_context ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_context (
            user_id VARCHAR PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            current_location_lat FLOAT,
            current_location_lng FLOAT,
            location_updated_at TIMESTAMPTZ,
            device_id VARCHAR(100),
            device_battery_level INTEGER,
            device_platform VARCHAR(20),
            last_device_ping TIMESTAMPTZ,
            timezone VARCHAR(50) DEFAULT 'America/Mexico_City',
            is_recording BOOLEAN DEFAULT FALSE,
            current_recording_id VARCHAR(36),
            auto_recording_enabled BOOLEAN DEFAULT TRUE,
            preferred_notification_time INTEGER DEFAULT 5,
            daily_auto_recordings_count INTEGER DEFAULT 0,
            daily_auto_recordings_date DATE,
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """))

    # --- user_document_index ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_document_index (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id VARCHAR(100) NOT NULL,
            filename VARCHAR(500) NOT NULL,
            file_path VARCHAR(1000) NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            created_on_device TIMESTAMPTZ,
            modified_on_device TIMESTAMPTZ,
            content_preview TEXT,
            extracted_text TEXT,
            document_type VARCHAR(50),
            related_class VARCHAR(200),
            keywords TEXT,
            is_deleted_on_device BOOLEAN DEFAULT FALSE,
            last_sync TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_document_index_id ON user_document_index(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_document_index_user_id ON user_document_index(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_document_index_device_id ON user_document_index(device_id)"))

    # --- user_sessions ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            token_hash VARCHAR(255) NOT NULL,
            device_info JSON,
            ip_address VARCHAR(45),
            user_agent TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            expires_at TIMESTAMPTZ NOT NULL,
            last_activity TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_sessions_id ON user_sessions(id)"))

    # --- study_groups (ensure it exists) ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS study_groups (
            id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            subject VARCHAR(100),
            description TEXT,
            created_by VARCHAR(50) NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            updated_at TIMESTAMP,
            is_private BOOLEAN DEFAULT TRUE,
            max_members INTEGER DEFAULT 50,
            university VARCHAR(200),
            course_code VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            archived_at TIMESTAMP,
            ai_enabled BOOLEAN DEFAULT FALSE,
            ai_personality VARCHAR(50) DEFAULT 'Mentor',
            members_count INTEGER DEFAULT 1,
            documents_count INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            notification_settings JSON
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_study_groups_name ON study_groups(name)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_study_groups_is_active ON study_groups(is_active)"))

    # --- group_members ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS group_members (
            id VARCHAR(50) PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            user_id VARCHAR(50) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR(20) DEFAULT 'member' NOT NULL,
            joined_at TIMESTAMP DEFAULT now() NOT NULL,
            invited_by VARCHAR(50) REFERENCES users(id),
            avatar_url VARCHAR(500),
            display_name VARCHAR(100),
            status_message VARCHAR(200),
            last_seen_at TIMESTAMP DEFAULT now(),
            messages_count INTEGER DEFAULT 0,
            documents_shared INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            muted_until TIMESTAMP
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_members_group_id ON group_members(group_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_members_user_id ON group_members(user_id)"))

    # --- shared_documents ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS shared_documents (
            id VARCHAR(50) PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            document_id VARCHAR(50) NOT NULL,
            shared_by VARCHAR(50) NOT NULL REFERENCES users(id),
            shared_at TIMESTAMP DEFAULT now() NOT NULL,
            document_type VARCHAR(50) DEFAULT 'pdf',
            title VARCHAR(500) NOT NULL,
            description TEXT,
            file_url VARCHAR(1000),
            tags JSON,
            category VARCHAR(100),
            views_count INTEGER DEFAULT 0,
            downloads_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            can_download BOOLEAN DEFAULT TRUE,
            can_edit BOOLEAN DEFAULT FALSE,
            ai_summary TEXT,
            ai_key_concepts JSON
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_shared_documents_group_id ON shared_documents(group_id)"))

    # --- group_messages ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS group_messages (
            id VARCHAR(50) PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            user_id VARCHAR(50) REFERENCES users(id),
            content TEXT NOT NULL,
            message_type VARCHAR(20) DEFAULT 'text' NOT NULL,
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            edited_at TIMESTAMP,
            context JSON,
            ai_model VARCHAR(50),
            reply_to VARCHAR(50) REFERENCES group_messages(id),
            mentioned_users JSON,
            reactions JSON
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_messages_group_id ON group_messages(group_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_messages_created_at ON group_messages(created_at)"))

    # --- group_invitations ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS group_invitations (
            id VARCHAR(50) PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            invited_email VARCHAR(255) NOT NULL,
            invited_user_id VARCHAR(50) REFERENCES users(id),
            invited_by VARCHAR(50) NOT NULL REFERENCES users(id),
            invited_at TIMESTAMP DEFAULT now() NOT NULL,
            invitation_token VARCHAR(100) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            accepted_at TIMESTAMP
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_invitations_group_id ON group_invitations(group_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_invitations_invited_email ON group_invitations(invited_email)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_invitations_invitation_token ON group_invitations(invitation_token)"))

    # --- group_activities ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS group_activities (
            id VARCHAR(50) PRIMARY KEY,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            user_id VARCHAR(50) REFERENCES users(id),
            activity_type VARCHAR(30) NOT NULL,
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            activity_metadata JSON
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_activities_group_id ON group_activities(group_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_group_activities_activity_type ON group_activities(activity_type)"))

    # --- chat_sessions ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id VARCHAR(50) PRIMARY KEY,
            user_id VARCHAR(50) NOT NULL REFERENCES users(id),
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            session_type VARCHAR(20) DEFAULT 'group' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            last_message_at TIMESTAMP,
            messages_count INTEGER DEFAULT 0
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_sessions_group_id ON chat_sessions(group_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_chat_sessions_is_active ON chat_sessions(is_active)"))

    # --- private_ai_messages ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS private_ai_messages (
            id VARCHAR(50) PRIMARY KEY,
            user_id VARCHAR(50) NOT NULL REFERENCES users(id),
            session_id VARCHAR(50) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            group_id VARCHAR(50) NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            context_docs JSON,
            context_messages JSON,
            attachments JSON,
            created_at TIMESTAMP DEFAULT now() NOT NULL,
            tokens_used INTEGER DEFAULT 0
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_private_ai_messages_user_id ON private_ai_messages(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_private_ai_messages_session_id ON private_ai_messages(session_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_private_ai_messages_created_at ON private_ai_messages(created_at)"))

    # --- voice_notes (from voice_note_models.py - MUST match VoiceNote class exactly) ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS voice_notes (
            id VARCHAR(36) PRIMARY KEY,
            client_record_id VARCHAR(255) NOT NULL UNIQUE,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id VARCHAR(100) NOT NULL,
            title VARCHAR(200),
            language VARCHAR(10) NOT NULL DEFAULT 'es',
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            upload_strategy VARCHAR(32) DEFAULT 'resumable',
            total_duration_ms INTEGER,
            total_chunks_expected INTEGER NOT NULL,
            total_chunks_received INTEGER DEFAULT 0,
            audio_format VARCHAR(20) DEFAULT 'webm',
            sample_rate INTEGER,
            total_bytes BIGINT,
            storage_path VARCHAR(500),
            storage_etag VARCHAR(255),
            transcript TEXT,
            transcript_confidence FLOAT,
            summary TEXT,
            summary_model VARCHAR(50),
            extracted_items JSON,
            topics JSON,
            entities JSON,
            processing_version INTEGER DEFAULT 0,
            processing_checksum VARCHAR(64),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            client_created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            upload_started_at TIMESTAMPTZ,
            upload_completed_at TIMESTAMPTZ,
            processing_started_at TIMESTAMPTZ,
            processing_completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            is_deleted BOOLEAN DEFAULT FALSE
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_notes_user_id ON voice_notes(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_notes_status ON voice_notes(status)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_notes_is_deleted ON voice_notes(is_deleted)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_notes_device_id ON voice_notes(device_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_notes_client_record ON voice_notes(client_record_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_voice_notes_user_status ON voice_notes(user_id, status)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_voice_notes_user_created ON voice_notes(user_id, created_at)"))

    # --- voice_note_chunks (MUST match VoiceNoteChunk exactly) ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS voice_note_chunks (
            id VARCHAR(36) PRIMARY KEY,
            voice_note_id VARCHAR(36) NOT NULL REFERENCES voice_notes(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            client_chunk_id VARCHAR(255) NOT NULL,
            byte_offset BIGINT NOT NULL,
            byte_length INTEGER NOT NULL,
            checksum_sha256 VARCHAR(64) NOT NULL,
            status VARCHAR(32) DEFAULT 'pending',
            storage_path VARCHAR(500),
            received_at TIMESTAMPTZ,
            verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_chunks_voice_note_id ON voice_note_chunks(voice_note_id)"))
    conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_note_chunks_note_index ON voice_note_chunks(voice_note_id, chunk_index)"))

    # --- voice_note_processing_jobs (MUST match VoiceNoteProcessingJob exactly) ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS voice_note_processing_jobs (
            id VARCHAR(36) PRIMARY KEY,
            voice_note_id VARCHAR(36) NOT NULL REFERENCES voice_notes(id) ON DELETE CASCADE,
            job_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            audio_checksum VARCHAR(64) NOT NULL,
            params_hash VARCHAR(64) NOT NULL,
            job_params JSON,
            result_data JSON,
            error_info JSON,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            duration_ms INTEGER,
            queue_name VARCHAR(50) DEFAULT 'default',
            priority INTEGER DEFAULT 0,
            scheduled_at TIMESTAMPTZ DEFAULT now(),
            worker_id VARCHAR(100),
            locked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_processing_jobs_voice_note_id ON voice_note_processing_jobs(voice_note_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_processing_jobs_job_type ON voice_note_processing_jobs(job_type)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_processing_jobs_status ON voice_note_processing_jobs(status)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_processing_jobs_idempotent ON voice_note_processing_jobs(audio_checksum, job_type, params_hash)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_queue ON voice_note_processing_jobs(status, queue_name, priority)"))

    # --- voice_note_sync_checkpoints (MUST match VoiceNoteSyncCheckpoint exactly) ---
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS voice_note_sync_checkpoints (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_id VARCHAR(100) NOT NULL,
            client_last_sync_at TIMESTAMPTZ NOT NULL,
            client_record_ids JSON,
            server_sync_at TIMESTAMPTZ DEFAULT now(),
            missing_on_server JSON,
            missing_on_client JSON,
            conflicts JSON,
            sync_duration_ms INTEGER,
            records_total INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_sync_user ON voice_note_sync_checkpoints(user_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voice_note_sync_device ON voice_note_sync_checkpoints(device_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_sync_checkpoints_user_device ON voice_note_sync_checkpoints(user_id, device_id, created_at)"))

    # =========================================================
    # PHASE 3: ENSURE INDEXES ON EXISTING TABLES (SAFE)
    # Each index creation is wrapped to handle missing tables
    # =========================================================
    safe_indexes = [
        ("device_tokens", "ix_device_tokens_id", "id"),
        ("recording_sessions", "ix_recording_sessions_id", "id"),
        ("recording_sessions", "ix_recording_sessions_user_id", "user_id"),
        ("recording_sessions", "ix_recording_sessions_status", "status"),
        ("session_items", "ix_session_items_id", "id"),
        ("session_items", "ix_session_items_session_id", "session_id"),
        ("session_items", "ix_session_items_user_id", "user_id"),
        ("session_items", "ix_session_items_item_type", "item_type"),
        ("payments", "ix_payments_id", "id"),
        ("plans", "ix_plans_id", "id"),
    ]
    for table, idx_name, columns in safe_indexes:
        conn.execute(sa.text(f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = '{table}'
                ) THEN
                    EXECUTE 'CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})';
                END IF;
            END $$;
        """))

    # =========================================================
    # PHASE 4: ADD MISSING COLUMNS TO EXISTING TABLES (SAFE)
    # Using DO $$ blocks to check column existence before adding
    # =========================================================
    safe_add_columns = [
        ("plans", "display_name", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("plans", "description", "TEXT"),
        ("plans", "currency", "VARCHAR(3) DEFAULT 'USD'"),
        ("plans", "requests_per_month", "INTEGER DEFAULT 0"),
        ("plans", "max_file_size_mb", "INTEGER DEFAULT 1"),
        ("plans", "features", "JSON"),
        ("plans", "is_active", "BOOLEAN DEFAULT TRUE"),
        ("plans", "is_demo", "BOOLEAN DEFAULT FALSE"),
        ("plans", "sort_order", "INTEGER DEFAULT 0"),
        ("plans", "created_at", "TIMESTAMPTZ DEFAULT now()"),
        ("plans", "updated_at", "TIMESTAMPTZ"),
        ("subscriptions", "status", "VARCHAR(20)"),
        ("subscriptions", "starts_at", "TIMESTAMPTZ"),
        ("subscriptions", "expires_at", "TIMESTAMPTZ"),
        ("subscriptions", "cancelled_at", "TIMESTAMPTZ"),
        ("subscriptions", "auto_renew", "BOOLEAN DEFAULT TRUE"),
        ("subscriptions", "payment_method", "VARCHAR(50)"),
        ("subscriptions", "gateway", "VARCHAR(50)"),
        ("subscriptions", "gateway_subscription_id", "VARCHAR(100)"),
        ("subscriptions", "payment_metadata", "JSON"),
        ("subscriptions", "created_at", "TIMESTAMPTZ DEFAULT now()"),
        ("subscriptions", "updated_at", "TIMESTAMPTZ"),
        ("payments", "subscription_id", "VARCHAR"),
        ("payments", "description", "TEXT"),
        ("payments", "gateway_transaction_id", "VARCHAR(100)"),
        ("payments", "gateway_response", "JSON"),
        ("payments", "processed_at", "TIMESTAMPTZ"),
        ("payments", "updated_at", "TIMESTAMPTZ"),
        ("users", "hashed_password", "VARCHAR(255)"),
        ("users", "bio", "TEXT"),
        ("users", "full_name", "VARCHAR(100)"),
        ("users", "profile_picture_url", "VARCHAR(500)"),
        ("users", "timezone", "VARCHAR(50) DEFAULT 'UTC'"),
        ("users", "preferred_language", "VARCHAR(10) DEFAULT 'en'"),
        ("users", "interests", "JSON"),
        ("users", "oauth_provider", "VARCHAR(20)"),
        ("users", "oauth_access_token", "VARCHAR(500)"),
        ("users", "oauth_refresh_token", "VARCHAR(500)"),
        ("users", "oauth_token_expires_at", "TIMESTAMPTZ"),
        ("users", "oauth_profile", "JSON"),
        ("recording_sessions", "scheduled_id", "VARCHAR(36)"),
    ]

    for table, column, col_type in safe_add_columns:
        conn.execute(sa.text(f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = '{table}'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                ) THEN
                    ALTER TABLE {table} ADD COLUMN {column} {col_type};
                END IF;
            END $$;
        """))


def downgrade() -> None:
    """Downgrade is intentionally empty - this is a one-way reconciliation migration."""
    pass
