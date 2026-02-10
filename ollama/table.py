from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    

    print("Starting migration: Multi-tenant TenderAI schema")

    
    ##########################################################
    # 1. Create PostgreSQL extensions
    ##########################################################
    print("\nStep 1: Creating extensions...")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    print("  [OK] Extensions created: uuid-ossp, pg_trgm, vector")
 
    ##########################################################
    # 2. Create database functions
    ##########################################################
    print("\nStep 2: Creating database functions...")
    
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE OR REPLACE FUNCTION multilingual_tsvector(content TEXT, lang TEXT DEFAULT 'simple')
        RETURNS tsvector AS $$
        BEGIN
            RETURN CASE 
                WHEN lang = 'fr' THEN to_tsvector('french', content)
                WHEN lang = 'en' THEN to_tsvector('english', content)
                WHEN lang = 'ar' THEN to_tsvector('simple', content)
                ELSE to_tsvector('simple', content) || to_tsvector('english', content)
            END;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)
    print("  [OK] Functions created: update_updated_at_column, multilingual_tsvector")
    
    ##########################################################
    # 3. Create tenants table
    ##########################################################
    print("\nStep 3: Creating tenants table...")
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()'),
                  comment='Unique tenant identifier'),
        sa.Column('name', sa.String(255), nullable=False, unique=True,
                  comment='Organization/company name'),
        sa.Column('email', sa.String(255), nullable=False, unique=True,
                  comment='Primary contact email for tenant'),
        sa.Column('subscription_plan', sa.String(50), nullable=False, 
                  server_default="'free'::character varying",
                  comment='Subscription tier: free, starter, professional, enterprise'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true',
                  comment='Tenant account active status'),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  comment='Additional tenant configuration and settings'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()'),
                  comment='Tenant creation timestamp'),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()'),
                  comment='Last update timestamp')
    )
    op.create_index('ix_tenants_email', 'tenants', ['email'], unique=True)
    op.create_index('ix_tenants_name', 'tenants', ['name'])
    op.create_index('ix_tenants_is_active', 'tenants', ['is_active'])
    print("  [OK] Tenants table created with 8 columns and 3 indexes")
    
    ##########################################################
    # 4. Create roles table
    ##########################################################
    print("\nStep 4: Creating roles table...")
    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True)),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('permissions', postgresql.JSONB(), nullable=False, 
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_roles_tenant_name')
    )


    op.create_index('ix_roles_tenant_id', 'roles', ['tenant_id'])
    op.create_index('ix_roles_name', 'roles', ['name'])
    print("  [OK] Roles table created with 8 columns and 2 indexes")
    
    ##########################################################
    # 5. Create users table
    ##########################################################
    print("\nStep 5: Creating users table...")
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True)),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_login_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_users_tenant_id_tenants', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'],  name='fk_users_role_id_roles',ondelete='SET NULL'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email')
    )
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('ix_users_role_id', 'users', ['role_id'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])
    op.execute("CREATE INDEX ix_users_is_deleted ON users (is_deleted) WHERE is_deleted = false")
    print("  [OK] Users table created with 12 columns and 5 indexes")
    
    ##########################################################
    # 6. Create documents table
    ##########################################################
    print("\nStep 6: Creating documents table...")
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True)),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True)),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('storage_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('mime_type', sa.String(100)),
        sa.Column('language', sa.String(10)),
        sa.Column('status', sa.String(50), nullable=False, 
                  server_default="'pending'::character varying"),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],  name='fk_documents_tenant_id_tenants', ondelete='CASCADE'),

        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], 
                               ondelete='SET NULL', name='fk_documents_uploaded_by_users'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], 
                               ondelete='SET NULL', name='fk_documents_created_by_users'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], 
                               ondelete='SET NULL', name='fk_documents_updated_by_users')
    )
    op.create_index('ix_documents_tenant_id', 'documents', ['tenant_id'])
    op.create_index('ix_documents_uploaded_by', 'documents', ['uploaded_by'])
    op.create_index('ix_documents_status', 'documents', ['status'])
    op.create_index('ix_documents_language', 'documents', ['language'])
    op.create_index('ix_documents_created_at', 'documents', ['created_at'])
    op.execute("CREATE INDEX ix_documents_is_deleted ON documents (is_deleted) WHERE is_deleted = false")
    op.execute("""
        CREATE INDEX ix_documents_filename_fts ON documents 
        USING gin(multilingual_tsvector(filename::text, COALESCE(language, 'simple')::text))
        WHERE is_deleted = false
    """)
    
    # Create document status ENUM type
    print("  Creating document status ENUM...")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_status') THEN
                CREATE TYPE doc_status AS ENUM ('pending', 'processing', 'completed', 'failed');
            END IF;
        END $$;
    """)
    print("  [OK] Documents table created with 15 columns and 7 indexes")
    
    ##########################################################
    # 7. Create chunks table
    ##########################################################
    print("\nStep 7: Creating chunks table...")
    op.create_table(
        'chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer()),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('embedding', Vector(1024)),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE')
    )
    op.create_index('ix_chunks_tenant_id', 'chunks', ['tenant_id'])
    op.create_index('ix_chunks_document_id', 'chunks', ['document_id'])
    op.create_index('ix_chunks_chunk_index', 'chunks', ['document_id', 'chunk_index'])
    op.execute("CREATE INDEX ix_chunks_is_deleted ON chunks (is_deleted) WHERE is_deleted = false")
    op.execute("""
        CREATE INDEX ix_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL AND is_deleted = false
    """)
    op.execute("""
        CREATE INDEX ix_chunks_content_fts ON chunks
        USING gin(to_tsvector('simple', content))
        WHERE is_deleted = false
    """)
    op.execute("""
        CREATE INDEX ix_chunks_content_fts_english ON chunks
        USING gin(to_tsvector('english', content))
        WHERE is_deleted = false
    """)
    op.execute("""
        CREATE INDEX ix_chunks_content_fts_french ON chunks
        USING gin(to_tsvector('french', content))
        WHERE is_deleted = false
    """)
    print("  [OK] Chunks table created with 10 columns, vector embeddings, and 8 indexes")
    
    ##########################################################
    # 8. Create compliance_reports table
    ##########################################################
    print("\nStep 8: Creating compliance_reports table...")
    op.create_table(
        'compliance_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('summary', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('findings', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column('compliance_score', sa.Float()),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('generated_by', sa.String(100)),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE')
    )
    op.create_index('ix_compliance_reports_tenant_id', 'compliance_reports', ['tenant_id'])
    op.create_index('ix_compliance_reports_document_id', 'compliance_reports', ['document_id'])
    op.create_index('ix_compliance_reports_status', 'compliance_reports', ['status'])
    op.create_index('ix_compliance_reports_score', 'compliance_reports', ['compliance_score'])
    op.create_index('ix_compliance_reports_created_at', 'compliance_reports', ['created_at'])
    print("  [OK] Compliance reports table created with 10 columns and 5 indexes")
    
    ##########################################################
    # 9. Create proposals table
    ##########################################################
    print("\nStep 9: Creating proposals table...")
    op.create_table(
        'proposals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True)),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text()),
        sa.Column('storage_path', sa.String(500)),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('metadata', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL',
                               name='proposals_created_by_fkey')
    )
    op.create_index('ix_proposals_tenant_id', 'proposals', ['tenant_id'])
    op.create_index('ix_proposals_document_id', 'proposals', ['document_id'])
    op.create_index('ix_proposals_created_by', 'proposals', ['created_by'])
    op.create_index('ix_proposals_status', 'proposals', ['status'])
    op.create_index('ix_proposals_created_at', 'proposals', ['created_at'])
    op.execute("CREATE INDEX ix_proposals_is_deleted ON proposals (is_deleted) WHERE is_deleted = false")
    op.execute("""
        CREATE INDEX ix_proposals_title_fts ON proposals
        USING gin(to_tsvector('simple', title::text))
        WHERE is_deleted = false
    """)
    op.execute("""
        CREATE INDEX ix_proposals_content_fts ON proposals
        USING gin(to_tsvector('simple', content))
        WHERE is_deleted = false AND content IS NOT NULL
    """)
    print("  [OK] Proposals table created with 12 columns and 8 indexes")
    
    ##########################################################
    # 10. Attach update triggers
    ##########################################################
    print("\nStep 10: Attaching update triggers...")
    for table in ['tenants', 'roles', 'users', 'documents', 'compliance_reports', 'proposals']:
        op.execute(f"""
            CREATE TRIGGER update_{table}_modtime
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)
    print("  [OK] Updated_at triggers attached to 6 tables")
    
    ##########################################################
    # 11. Enable Row-Level Security (RLS)
    ##########################################################
    print("\nStep 11: Enabling Row-Level Security...")
    
    # Tenants self-policy
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenants_self_policy ON tenants FOR SELECT
        USING (id::text = current_setting('app.current_tenant', true))
    """)
    
    # Tenant-scoped tables
    tenant_tables = ['documents', 'chunks', 'compliance_reports', 'proposals', 'users', 'roles']
    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_policy_{table} ON {table}
            USING (tenant_id::text = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant', true))
        """)
    print("  [OK] RLS enabled on 7 tables with isolation policies")
    
    ##########################################################
    # 12. Pre-seed system tenant and roles
    ##########################################################
    print("\nStep 12: Pre-seeding system data...")
    op.execute("""
        INSERT INTO tenants (id, name, email, subscription_plan, is_active)
        VALUES ('00000000-0000-0000-0000-000000000000'::uuid, 'System', 
                'system@tenderai.internal', 'enterprise', true)
        ON CONFLICT DO NOTHING
    """)
    
    system_roles = [
        ('system_admin', 'Full system access', '["*"]'),
        ('tenant_admin', 'Tenant administrator', '["tenant:*", "documents:*", "users:*"]'),
        ('analyst', 'Analyst role', '["documents:read", "documents:analyze"]'),
        ('viewer', 'Read-only access', '["documents:read"]')
    ]
    
    for name, desc, perms in system_roles:
        op.execute(f"""
            INSERT INTO roles (tenant_id, name, description, permissions, is_system)
            VALUES ('00000000-0000-0000-0000-000000000000'::uuid, '{name}', '{desc}',
                    '{{"permissions": {perms}}}'::jsonb, true)
            ON CONFLICT DO NOTHING
        """)
    print("  [OK] System tenant and 4 system roles pre-seeded")
    
    print("\n" + "=" * 80)
    print("[SUCCESS] MIGRATION COMPLETED SUCCESSFULLY!")

 


def downgrade() -> None:
    """Rollback migration - removes all created objects in reverse order."""

    print("ROLLING BACK MIGRATION")
 
    
    # Drop tables in reverse order (respecting foreign key dependencies)
    print("\nDropping tables...")
    tables = [
        'proposals',
        'compliance_reports',
        'chunks',
        'documents',
        'users',
        'roles',
        'tenants'
    ]
    
    for table in tables:
        print(f"  Dropping table: {table}")
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    
    # Drop custom types
    print("\nDropping custom types...")
    op.execute('DROP TYPE IF EXISTS doc_status CASCADE')
    print("  [OK] doc_status ENUM dropped")
    
    # Drop functions
    print("\nDropping functions...")
    op.execute('DROP FUNCTION IF EXISTS multilingual_tsvector(TEXT, TEXT) CASCADE')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE')
    print("  [OK] Functions dropped")
    
    # Drop extensions (optional - might be used by other schemas)
    print("\nDropping extensions...")
    op.execute('DROP EXTENSION IF EXISTS "vector" CASCADE')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm" CASCADE')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE')
    print("  [OK] Extensions dropped")
    
    print("\n" + "=" * 80)
    print("[SUCCESS] ROLLBACK COMPLETED")

###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, INET


# revision identifiers, used by Alembic.
revision = '0002_add_auth_security_tables'
down_revision = '0001'  # Fixed: matches actual revision ID from 0001_init_multitenant_rls.py
branch_labels = None
depends_on = None


def upgrade():
    """Add auth_sessions and login_attempts tables."""
    
    # ========================================================================
    # Table: auth_sessions
    # Purpose: Track refresh token sessions for revocation and device management
    # ========================================================================
    op.create_table(
        'auth_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('jti', UUID(as_uuid=True), nullable=False, unique=True, comment='JWT ID for refresh token'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='Browser/device user agent'),
        sa.Column('ip_address', INET(), nullable=True, comment='IP address of session creation'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment='Refresh token expiration'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True, comment='When session was revoked'),
        sa.Column('replaced_by', UUID(as_uuid=True), nullable=True, comment='ID of session that replaced this one (rotation)'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True, comment='Last time this session was used'),
    )
    
    # Indexes for auth_sessions
    op.create_index('idx_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('idx_auth_sessions_tenant_id', 'auth_sessions', ['tenant_id'])
    op.create_index('idx_auth_sessions_jti', 'auth_sessions', ['jti'])
    op.create_index('idx_auth_sessions_user_active', 'auth_sessions', ['user_id', 'revoked_at', 'expires_at'])
    op.create_index('idx_auth_sessions_expires', 'auth_sessions', ['expires_at'])
    
    # Enable RLS for auth_sessions (tenant isolation)
    op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY")
    
    # RLS Policy for auth_sessions
    op.execute("""
        CREATE POLICY tenant_isolation_policy_auth_sessions ON auth_sessions
        USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
    """)
    
    # ========================================================================
    # Table: login_attempts
    # Purpose: Security audit trail for all login attempts (successful and failed)
    # ========================================================================
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=True, comment='NULL if user not found'),
        sa.Column('email', sa.String(255), nullable=False, comment='Email attempted'),
        sa.Column('ip_address', INET(), nullable=True, comment='IP address of attempt'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='Browser/device user agent'),
        sa.Column('success', sa.Boolean(), nullable=False, default=False, comment='Whether login succeeded'),
        sa.Column('failure_reason', sa.String(100), nullable=True, comment='Reason for failure (invalid_credentials, rate_limited, etc.)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    
    # Indexes for login_attempts (NO RLS - global security table)
    op.create_index('idx_login_attempts_email_created', 'login_attempts', ['email', 'created_at'])
    op.create_index('idx_login_attempts_ip_created', 'login_attempts', ['ip_address', 'created_at'])
    op.create_index('idx_login_attempts_created', 'login_attempts', ['created_at'])
    op.create_index('idx_login_attempts_user_id', 'login_attempts', ['user_id'])
    
    # NO RLS for login_attempts - this is a global security audit table
    # Access controlled via application logic (admin-only)
    
    print(" Created auth_sessions table with RLS")
    print(" Created login_attempts table (global audit)")


def downgrade():
    """Remove auth_sessions and login_attempts tables."""
    
    # Drop login_attempts (no RLS)
    op.drop_index('idx_login_attempts_user_id', 'login_attempts')
    op.drop_index('idx_login_attempts_created', 'login_attempts')
    op.drop_index('idx_login_attempts_ip_created', 'login_attempts')
    op.drop_index('idx_login_attempts_email_created', 'login_attempts')
    op.drop_table('login_attempts')
    
    # Drop auth_sessions (with RLS)
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_auth_sessions ON auth_sessions")
    op.drop_index('idx_auth_sessions_expires', 'auth_sessions')
    op.drop_index('idx_auth_sessions_user_active', 'auth_sessions')
    op.drop_index('idx_auth_sessions_jti', 'auth_sessions')
    op.drop_index('idx_auth_sessions_tenant_id', 'auth_sessions')
    op.drop_index('idx_auth_sessions_user_id', 'auth_sessions')
    op.drop_table('auth_sessions')
    
    print(" Dropped auth_sessions and login_attempts tables")
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""

revision: str = '0003'
down_revision: Union[str, None] = '0002_add_auth_security_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add file_hash column to documents table"""

    print("Migration 0002: Add file_hash for deduplication")
  
    
    print("\n[1/2] Adding file_hash column to documents table...")
    op.add_column('documents', 
        sa.Column('file_hash', sa.String(64), nullable=True,
                  comment='SHA-256 hash of file content for deduplication')
    )
    print("   Column added: file_hash (String 64)")
    
    print("\n[2/2] Creating index on (tenant_id, file_hash) for duplicate detection...")
    op.create_index(
        'ix_documents_tenant_file_hash',
        'documents',
        ['tenant_id', 'file_hash'],
        unique=False
    )
    print("   Index created: ix_documents_tenant_file_hash")
    
    print("\n" + "=" * 80)
    print(" Migration 0002 completed successfully!")



def downgrade() -> None:
    """Remove file_hash column and index"""
    
 
    print("Rolling back migration 0002")
  
    
    print("\n[1/2] Dropping index ix_documents_tenant_file_hash...")
    op.drop_index('ix_documents_tenant_file_hash', table_name='documents')
    print("   Index dropped")
    
    print("\n[2/2] Dropping file_hash column...")
    op.drop_column('documents', 'file_hash')
    print("Column dropped")
    

    print("Rollback completed")
  

###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""




from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add company_asset table with RLS policies"""
    

    print("Migration 0004: Add company_asset table")

    
    # Step 1: Create company_asset table
    print("\n[1/9] Creating company_asset table...")
    op.create_table(
        'company_asset',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Asset classification
        sa.Column('kind', sa.String(50), nullable=False),
        
        # Content
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True, comment='Full text content for embedding'),
        
        # File reference
        sa.Column('file_uri', sa.Text(), nullable=True, comment='MinIO path: tenants/{tenant_id}/assets/{filename}'),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=True),
        
        # Metadata
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), nullable=True),
        
        # Visibility
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        
        # Soft delete (aligns with SoftDeleteMixin)
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        
        # Check constraint for kind
        sa.CheckConstraint(
            "kind IN ('certification', 'past_project', 'team_bio', 'company_description', " +
            "'technical_capability', 'financial_document', 'legal_document', " +
            "'standard_clause', 'logo', 'template', 'other')",
            name='ck_company_asset_kind'
        )
    )
    print("Table created: company_asset")
    
    # Step 2: Create indexes for performance
    print("\n[2/9] Creating indexes...")
    
    # Tenant ID index (most important for RLS)
    op.create_index(
        'idx_company_asset_tenant_id',
        'company_asset',
        ['tenant_id'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_tenant_id")
    
    # Kind index (filter by asset type)
    op.create_index(
        'idx_company_asset_kind',
        'company_asset',
        ['kind'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_kind")
    
    # Tags GIN index (array search)
    op.create_index(
        'idx_company_asset_tags',
        'company_asset',
        ['tags'],
        postgresql_using='gin',
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_tags (GIN)")
    
    # Active assets composite index
    op.create_index(
        'idx_company_asset_active',
        'company_asset',
        ['tenant_id', 'is_active'],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_active")
    
    # Created at index (for sorting)
    op.create_index(
        'idx_company_asset_created_at',
        'company_asset',
        [sa.text('created_at DESC')],
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_created_at")
    
    # Full-text search index
    op.create_index(
        'idx_company_asset_content_search',
        'company_asset',
        [sa.text("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(content, ''))")],
        postgresql_using='gin',
        postgresql_where=sa.text('deleted_at IS NULL')
    )
    print("Index created: idx_company_asset_content_search (Full-text GIN)")
    
    # Step 3: Enable Row-Level Security (RLS)
    print("\n[3/9] Enabling Row-Level Security (RLS)...")
    op.execute('ALTER TABLE company_asset ENABLE ROW LEVEL SECURITY')
    print("    RLS enabled on company_asset")
    
    # Step 4: Create RLS policy for tenant isolation
    print("\n[4/9] Creating RLS policy: tenant_isolation_policy_company_asset...")
    op.execute("""
        CREATE POLICY tenant_isolation_policy_company_asset ON company_asset
        USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
    """)
    print("    RLS policy created: tenant isolation")
    
    # Step 5: Create RLS bypass policy for service role
    print("\n[5/9] Creating RLS policy: bypass_rls_policy_company_asset...")
    op.execute("""
        CREATE POLICY bypass_rls_policy_company_asset ON company_asset
        USING (current_setting('app.bypass_rls', true)::text = 'true')
    """)
    print("    RLS policy created: bypass for service role")
    
    # Step 6: Create trigger for updated_at
    print("\n[6/9] Creating trigger for updated_at timestamp...")
    op.execute("""
        CREATE TRIGGER update_company_asset_updated_at
        BEFORE UPDATE ON company_asset
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)
    print("   Trigger created: update_company_asset_updated_at")
    
    # Step 7: Grant permissions to tenderai_app user
    print("\n[7/9] Granting permissions to tenderai_app user...")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON company_asset TO tenderai_app")
    print("   Permissions granted: SELECT, INSERT, UPDATE, DELETE")
    
    # Step 8: Add table comment
    print("\n[8/9] Adding table comments...")
    op.execute("""
        COMMENT ON TABLE company_asset IS 
        'Company assets for proposal generation and company profile management. Stores reusable content like certifications, past projects, team bios, standard clauses, and templates.'
    """)
    op.execute("""
        COMMENT ON COLUMN company_asset.kind IS 
        'Asset type: certification, past_project, team_bio, company_description, technical_capability, financial_document, legal_document, standard_clause, logo, template, other'
    """)
    op.execute("COMMENT ON COLUMN company_asset.content IS 'Full text content for embedding and semantic search'")
    op.execute("COMMENT ON COLUMN company_asset.file_uri IS 'MinIO storage path: tenants/{tenant_id}/assets/{filename}'")
    op.execute("COMMENT ON COLUMN company_asset.metadata IS 'Custom JSON metadata per asset type (flexible schema)'")
    op.execute("COMMENT ON COLUMN company_asset.is_public IS 'Whether asset can be shared across tenant users'")
    op.execute("COMMENT ON COLUMN company_asset.tags IS 'Searchable tags for categorization and filtering'")

    
    # Step 9: Verify RLS policies
    print("\n[9/9] Verifying RLS policies...")
    result = op.get_bind().execute(sa.text("""
        SELECT COUNT(*) FROM pg_policies 
        WHERE schemaname = 'public' 
        AND tablename = 'company_asset'
    """))
    policy_count = result.scalar()
    
    if policy_count >= 2:
        print(f"RLS policies verified: {policy_count} policies active")
    else:
        print(f"Warning: Expected 2 policies, found {policy_count}")
    
    print("\n" + "=" * 80)
    print(" Migration 0004 completed successfully!")
    print("=" * 80)
    


def downgrade() -> None:
    """Remove company_asset table and related objects"""
    
    print("=" * 80)
    print("Migration 0004: Downgrade - Removing company_asset table")
    print("=" * 80)
    
    # Drop trigger
    print("\n[1/3] Dropping trigger...")
    op.execute("DROP TRIGGER IF EXISTS update_company_asset_updated_at ON company_asset")
    print("Trigger dropped")
    
    # Drop RLS policies
    print("\n[2/3] Dropping RLS policies...")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_company_asset ON company_asset")
    op.execute("DROP POLICY IF EXISTS bypass_rls_policy_company_asset ON company_asset")
    print("RLS policies dropped")
    
    # Drop table (indexes will be dropped automatically)
    print("\n[3/3] Dropping company_asset table...")
    op.drop_table('company_asset')
    print("Table dropped")
    
    print("\n" + "=" * 80)
    print(" Migration 0004 downgrade completed")
    print("=" * 80)
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_logs table for immutable audit trail."""
    
    print("=" * 80)
    print("Migration 0006: Add audit_logs table (Immutable Audit Trail)")
    print("=" * 80)
    
    print("\n[1/4] Creating audit_logs table...")
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True,
                  comment='Immutable sequential audit log ID'),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'),
                  nullable=False, comment='Tenant performing the action'),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, comment='User who performed the action (NULL for system)'),
        sa.Column('action', sa.String(50), nullable=False,
                  comment='Action type: CREATE, UPDATE, DELETE, READ, AUTH_FAILURE, etc.'),
        sa.Column('resource_type', sa.String(100), nullable=False,
                  comment='Resource type: document, user, proposal, compliance_report, etc.'),
        sa.Column('resource_id', UUID(as_uuid=True), nullable=True,
                  comment='ID of the affected resource'),
        sa.Column('old_value', JSONB(), nullable=True,
                  comment='Previous state (for UPDATE operations)'),
        sa.Column('new_value', JSONB(), nullable=True,
                  comment='New state (for UPDATE/CREATE operations)'),
        sa.Column('status', sa.String(50), nullable=False, server_default="'SUCCESS'",
                  comment='Action status: SUCCESS, FAILURE, DENIED'),
        sa.Column('reason', sa.Text(), nullable=True,
                  comment='Reason for failure or denial'),
        sa.Column('ip_address', sa.String(45), nullable=True,
                  comment='IPv4 or IPv6 address of request'),
        sa.Column('user_agent', sa.Text(), nullable=True,
                  comment='HTTP User-Agent string'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'),
                  comment='Immutable creation timestamp'),
        sa.Column('hash', sa.String(64), nullable=False,
                  comment='SHA-256 hash of this record + previous hash (chain integrity)'),
        sa.Column('previous_hash', sa.String(64), nullable=True,
                  comment='SHA-256 hash of previous audit log entry (hash chain)'),
        comment='Immutable append-only audit trail for compliance and non-repudiation'
    )
    print("Table created with 15 columns")
    
    print("\n[2/4] Creating indexes for performance...")
    op.create_index('idx_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('idx_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('idx_audit_logs_resource_id', 'audit_logs', ['resource_id'])
    op.create_index('idx_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_logs_status', 'audit_logs', ['status'])
    op.create_index('idx_audit_logs_tenant_timestamp', 'audit_logs', ['tenant_id', 'timestamp'])
    op.create_index('idx_audit_logs_tenant_resource', 'audit_logs', ['tenant_id', 'resource_type', 'resource_id'])
    op.create_index('idx_audit_logs_hash_chain', 'audit_logs', ['previous_hash', 'hash'])
    print(" 10 performance indexes created")
    
    print("\n[3/4] Creating append-only enforcement trigger...")
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_logs_prevent_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: UPDATE/DELETE not allowed';
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION audit_logs_prevent_modify();
    """)
    
    op.execute("""
        CREATE TRIGGER audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION audit_logs_prevent_modify();
    """)
    print("  Append-only enforcement trigger created")
    
    print("\n[4/4] Enabling Row-Level Security (RLS)...")
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_policy_audit_logs ON audit_logs
        USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
    """)
    print("RLS policy created for tenant isolation")
    
    print("\n" + "=" * 80)
    print("Migration 0006 completed successfully!")
    print("=" * 80)
    

def downgrade() -> None:
    """Drop audit_logs table."""
    
    print("\n[1/3] Dropping append-only enforcement triggers...")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_prevent_modify()")
    print(" Triggers dropped")
    
    print("\n[2/3] Dropping RLS policies...")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_audit_logs ON audit_logs")
    print("  RLS policy dropped")
    
    print("\n[3/3] Dropping audit_logs table...")
    op.drop_index('idx_audit_logs_hash_chain', 'audit_logs')
    op.drop_index('idx_audit_logs_tenant_resource', 'audit_logs')
    op.drop_index('idx_audit_logs_tenant_timestamp', 'audit_logs')
    op.drop_index('idx_audit_logs_status', 'audit_logs')
    op.drop_index('idx_audit_logs_action', 'audit_logs')
    op.drop_index('idx_audit_logs_timestamp', 'audit_logs')
    op.drop_index('idx_audit_logs_resource_id', 'audit_logs')
    op.drop_index('idx_audit_logs_resource_type', 'audit_logs')
    op.drop_index('idx_audit_logs_user_id', 'audit_logs')
    op.drop_index('idx_audit_logs_tenant_id', 'audit_logs')
    op.drop_table('audit_logs')
    print("Table and indexes dropped")
    
    print("\n" + "=" * 80)
    print("Downgrade completed!")
    print("=" * 80)


###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
###################################""""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP


# Revision identifiers
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    # Add TOTP secret column (encrypted at application level)
    op.add_column(
        'users',
        sa.Column(
            'totp_secret',
            sa.String(64),
            nullable=True,
            comment='Encrypted TOTP secret key (base32 encoded)'
        )
    )
    
    # Add TOTP enabled flag
    op.add_column(
        'users',
        sa.Column(
            'totp_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Whether two-factor authentication is enabled'
        )
    )
    
    # Add TOTP verified timestamp (when 2FA was first activated)
    op.add_column(
        'users',
        sa.Column(
            'totp_verified_at',
            TIMESTAMP(timezone=True),
            nullable=True,
            comment='Timestamp when 2FA was first verified and enabled'
        )
    )
    
    # Add TOTP setup timestamp (when user initiated 2FA setup)
    op.add_column(
        'users',
        sa.Column(
            'totp_setup_at',
            TIMESTAMP(timezone=True),
            nullable=True,
            comment='Timestamp when 2FA setup was initiated'
        )
    )
    
    # Add backup codes array (hashed with Argon2id)
    op.add_column(
        'users',
        sa.Column(
            'backup_codes',
            ARRAY(sa.Text()),
            nullable=True,
            comment='Array of hashed backup codes for 2FA recovery'
        )
    )
    
    # Add index for querying 2FA-enabled users
    op.create_index(
        'idx_users_totp_enabled',
        'users',
        ['totp_enabled'],
        postgresql_where=sa.text('totp_enabled = true')
    )
    
    # Add comment explaining 2FA security
    op.execute("""
        COMMENT ON COLUMN users.totp_secret IS 
        'Encrypted TOTP secret key (base32 encoded). Used with Google Authenticator or similar apps. '
        'Encrypted at application level using AES-256-GCM before storage.';
    """)
    
    op.execute("""
        COMMENT ON COLUMN users.backup_codes IS 
        'Array of 10 hashed backup codes for 2FA recovery. Each code is single-use. '
        'Hashed with Argon2id (not reversible). Regenerated on request.';
    """)


def downgrade() -> None:

    
    # Drop index first
    op.drop_index('idx_users_totp_enabled', table_name='users')
    
    # Drop columns
    op.drop_column('users', 'backup_codes')
    op.drop_column('users', 'totp_setup_at')
    op.drop_column('users', 'totp_verified_at')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')