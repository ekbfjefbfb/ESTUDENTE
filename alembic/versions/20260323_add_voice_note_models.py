"""
🎙️ VoiceNote Models Migration - Offline-first, resumible, idempotent

Revision ID: 20260323_add_voice_note_models
Revises: 20260320_add_hashed_password_to_users
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260323_add_voice_note_models'
down_revision = '20260320_add_hashed_password_to_users'
branch_labels = None
depends_on = None


def upgrade():
    # =============================================
    # ENUMS
    # =============================================
    
    # VoiceNoteStatus enum
    voicenotestatus = sa.Enum(
        'draft', 'uploading', 'uploaded', 'queued', 
        'transcribing', 'processing', 'completed', 
        'error', 'cancelled',
        name='voicenotestatus'
    )
    voicenotestatus.create(op.get_bind(), checkfirst=True)
    
    # VoiceNoteUploadStrategy enum
    voicenoteuploadstrategy = sa.Enum(
        'streaming', 'resumable', 'bulk',
        name='voicenoteuploadstrategy'
    )
    voicenoteuploadstrategy.create(op.get_bind(), checkfirst=True)
    
    # AudioChunkStatus enum
    audiochunkstatus = sa.Enum(
        'pending', 'received', 'verified', 'failed',
        name='audiochunkstatus'
    )
    audiochunkstatus.create(op.get_bind(), checkfirst=True)
    
    # ProcessingJobType enum
    processingjobtype = sa.Enum(
        'transcription', 'summarization', 'extraction', 'full_pipeline',
        name='processingjobtype'
    )
    processingjobtype.create(op.get_bind(), checkfirst=True)
    
    # ProcessingJobStatus enum
    processingjobstatus = sa.Enum(
        'pending', 'running', 'completed', 'failed', 'retrying',
        name='processingjobstatus'
    )
    processingjobstatus.create(op.get_bind(), checkfirst=True)
    
    # =============================================
    # VOICE_NOTES TABLE
    # =============================================
    op.create_table(
        'voice_notes',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('client_record_id', sa.String(255), nullable=False, unique=True),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_id', sa.String(100), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='es'),
        sa.Column('status', sa.Enum(
            'draft', 'uploading', 'uploaded', 'queued', 
            'transcribing', 'processing', 'completed', 
            'error', 'cancelled',
            name='voicenotestatus'
        ), nullable=False, server_default='draft', index=True),
        sa.Column('upload_strategy', sa.Enum(
            'streaming', 'resumable', 'bulk',
            name='voicenoteuploadstrategy'
        ), nullable=False, server_default='resumable'),
        sa.Column('total_duration_ms', sa.Integer, nullable=True),
        sa.Column('total_chunks_expected', sa.Integer, nullable=False),
        sa.Column('total_chunks_received', sa.Integer, server_default='0'),
        sa.Column('audio_format', sa.String(20), nullable=False, server_default='webm'),
        sa.Column('sample_rate', sa.Integer, nullable=True),
        sa.Column('total_bytes', sa.BigInteger, nullable=True),
        sa.Column('storage_path', sa.String(500), nullable=True),
        sa.Column('storage_etag', sa.String(255), nullable=True),
        sa.Column('transcript', sa.Text, nullable=True),
        sa.Column('transcript_confidence', sa.Float, nullable=True),
        sa.Column('summary', sa.Text, nullable=True),
        sa.Column('summary_model', sa.String(50), nullable=True),
        sa.Column('extracted_items', sa.JSON, server_default='[]'),
        sa.Column('topics', sa.JSON, server_default='[]'),
        sa.Column('entities', sa.JSON, server_default='[]'),
        sa.Column('processing_version', sa.Integer, server_default='0'),
        sa.Column('processing_checksum', sa.String(64), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('client_created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('upload_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('upload_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_deleted', sa.Boolean, server_default='false', index=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Índices compuestos
    op.create_index('idx_voice_notes_user_status', 'voice_notes', ['user_id', 'status'])
    op.create_index('idx_voice_notes_user_created', 'voice_notes', ['user_id', 'created_at'])
    op.create_index('idx_voice_notes_client_record', 'voice_notes', ['client_record_id'])
    
    # =============================================
    # VOICE_NOTE_CHUNKS TABLE
    # =============================================
    op.create_table(
        'voice_note_chunks',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('voice_note_id', sa.String(36), sa.ForeignKey('voice_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('client_chunk_id', sa.String(255), nullable=False),
        sa.Column('byte_offset', sa.BigInteger, nullable=False),
        sa.Column('byte_length', sa.Integer, nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=False),
        sa.Column('status', sa.Enum(
            'pending', 'received', 'verified', 'failed',
            name='audiochunkstatus'
        ), nullable=False, server_default='pending'),
        sa.Column('storage_path', sa.String(500), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('voice_note_id', 'chunk_index', name='idx_voice_note_chunks_note_index')
    )
    
    op.create_index('idx_voice_note_chunks_voice_note_id', 'voice_note_chunks', ['voice_note_id'])
    
    # =============================================
    # VOICE_NOTE_PROCESSING_JOBS TABLE
    # =============================================
    op.create_table(
        'voice_note_processing_jobs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('voice_note_id', sa.String(36), sa.ForeignKey('voice_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_type', sa.Enum(
            'transcription', 'summarization', 'extraction', 'full_pipeline',
            name='processingjobtype'
        ), nullable=False, index=True),
        sa.Column('status', sa.Enum(
            'pending', 'running', 'completed', 'failed', 'retrying',
            name='processingjobstatus'
        ), nullable=False, server_default='pending', index=True),
        sa.Column('audio_checksum', sa.String(64), nullable=False),
        sa.Column('params_hash', sa.String(64), nullable=False),
        sa.Column('job_params', sa.JSON, server_default='{}'),
        sa.Column('result_data', sa.JSON, nullable=True),
        sa.Column('error_info', sa.JSON, nullable=True),
        sa.Column('attempts', sa.Integer, server_default='0'),
        sa.Column('max_attempts', sa.Integer, server_default='3'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),
        sa.Column('queue_name', sa.String(50), server_default='default'),
        sa.Column('priority', sa.Integer, server_default='0'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('worker_id', sa.String(100), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Índices
    op.create_index(
        'idx_processing_jobs_idempotent', 
        'voice_note_processing_jobs', 
        ['audio_checksum', 'job_type', 'params_hash']
    )
    op.create_index(
        'idx_processing_jobs_status_queue', 
        'voice_note_processing_jobs', 
        ['status', 'queue_name', 'priority']
    )
    op.create_index('idx_processing_jobs_voice_note_id', 'voice_note_processing_jobs', ['voice_note_id'])
    
    # =============================================
    # VOICE_NOTE_SYNC_CHECKPOINTS TABLE
    # =============================================
    op.create_table(
        'voice_note_sync_checkpoints',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_id', sa.String(100), nullable=False),
        sa.Column('client_last_sync_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('client_record_ids', sa.JSON, server_default='[]'),
        sa.Column('server_sync_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('missing_on_server', sa.JSON, server_default='[]'),
        sa.Column('missing_on_client', sa.JSON, server_default='[]'),
        sa.Column('conflicts', sa.JSON, server_default='[]'),
        sa.Column('sync_duration_ms', sa.Integer, nullable=True),
        sa.Column('records_total', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index(
        'idx_sync_checkpoints_user_device', 
        'voice_note_sync_checkpoints', 
        ['user_id', 'device_id', 'created_at']
    )


def downgrade():
    # Drop tables en orden inverso (respetar FKs)
    op.drop_table('voice_note_sync_checkpoints')
    op.drop_table('voice_note_processing_jobs')
    op.drop_table('voice_note_chunks')
    op.drop_table('voice_notes')
    
    # Drop enums
    sa.Enum(name='processingjobstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='processingjobtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='audiochunkstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='voicenoteuploadstrategy').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='voicenotestatus').drop(op.get_bind(), checkfirst=True)
