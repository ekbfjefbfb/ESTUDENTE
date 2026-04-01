-- =============================================
-- MIGRACIÓN COMPLETA - ACTUALIZAR SCHEMA USERS
-- Fecha: 2026-03-31
-- Descripción: Agrega todas las columnas faltantes a la tabla users
-- =============================================

-- Verificar si la tabla users existe
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        RAISE EXCEPTION 'La tabla users no existe. Crear tabla primero.';
    END IF;
END $$;

-- =============================================
-- COLUMNAS BÁSICAS DE USUARIO
-- =============================================

-- phone_number (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'phone_number') THEN
        ALTER TABLE users ADD COLUMN phone_number VARCHAR(20) UNIQUE;
        COMMENT ON COLUMN users.phone_number IS 'Número de teléfono para registro/login con SMS';
    END IF;
END $$;

-- phone_verified (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'phone_verified') THEN
        ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT FALSE;
        COMMENT ON COLUMN users.phone_verified IS 'Si el número de teléfono está verificado';
    END IF;
END $$;

-- phone_verified_at (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'phone_verified_at') THEN
        ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.phone_verified_at IS 'Fecha de verificación del teléfono';
    END IF;
END $$;

-- full_name (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'full_name') THEN
        ALTER TABLE users ADD COLUMN full_name VARCHAR(100);
        COMMENT ON COLUMN users.full_name IS 'Nombre completo del usuario';
    END IF;
END $$;

-- bio (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'bio') THEN
        ALTER TABLE users ADD COLUMN bio TEXT;
        COMMENT ON COLUMN users.bio IS 'Biografía del usuario';
    END IF;
END $$;

-- =============================================
-- COLUMNAS DE PLAN Y SUSCRIPCIÓN
-- =============================================

-- subscription_expires_at (CRÍTICO - causa error actual)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'subscription_expires_at') THEN
        ALTER TABLE users ADD COLUMN subscription_expires_at TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.subscription_expires_at IS 'Fecha de expiración de la suscripción';
    END IF;
END $$;

-- plan_id (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'plan_id') THEN
        ALTER TABLE users ADD COLUMN plan_id INTEGER REFERENCES plans(id);
        COMMENT ON COLUMN users.plan_id IS 'ID del plan de suscripción activo';
    END IF;
END $$;

-- plan_started_at (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'plan_started_at') THEN
        ALTER TABLE users ADD COLUMN plan_started_at TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.plan_started_at IS 'Fecha de inicio del plan actual';
    END IF;
END $$;

-- plan_ends_at (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'plan_ends_at') THEN
        ALTER TABLE users ADD COLUMN plan_ends_at TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.plan_ends_at IS 'Fecha de fin del plan actual';
    END IF;
END $$;

-- requests_used_this_month (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'requests_used_this_month') THEN
        ALTER TABLE users ADD COLUMN requests_used_this_month INTEGER DEFAULT 0;
        COMMENT ON COLUMN users.requests_used_this_month IS 'Número de requests usados este mes';
    END IF;
END $$;

-- last_request_reset (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_request_reset') THEN
        ALTER TABLE users ADD COLUMN last_request_reset TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.last_request_reset IS 'Último reset de contador de requests';
    END IF;
END $$;

-- last_activity (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_activity') THEN
        ALTER TABLE users ADD COLUMN last_activity TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.last_activity IS 'Última actividad del usuario';
    END IF;
END $$;

-- profile_data (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'profile_data') THEN
        ALTER TABLE users ADD COLUMN profile_data JSONB DEFAULT '{}';
        COMMENT ON COLUMN users.profile_data IS 'Datos de perfil adicionales en JSON';
    END IF;
END $$;

-- preferences (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'preferences') THEN
        ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}';
        COMMENT ON COLUMN users.preferences IS 'Preferencias del usuario en JSON';
    END IF;
END $$;

-- =============================================
-- COLUMNAS DE DEMO/TRIAL
-- =============================================

-- demo_until (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'demo_until') THEN
        ALTER TABLE users ADD COLUMN demo_until TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.demo_until IS 'Fecha límite del período demo';
    END IF;
END $$;

-- demo_requests_today (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'demo_requests_today') THEN
        ALTER TABLE users ADD COLUMN demo_requests_today INTEGER DEFAULT 0;
        COMMENT ON COLUMN users.demo_requests_today IS 'Requests usados hoy en modo demo';
    END IF;
END $$;

-- demo_last_reset (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'demo_last_reset') THEN
        ALTER TABLE users ADD COLUMN demo_last_reset TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.demo_last_reset IS 'Último reset del contador demo';
    END IF;
END $$;

-- demo_count (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'demo_count') THEN
        ALTER TABLE users ADD COLUMN demo_count INTEGER DEFAULT 0;
        COMMENT ON COLUMN users.demo_count IS 'Contador de períodos demo usados';
    END IF;
END $$;

-- last_demo_date (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_demo_date') THEN
        ALTER TABLE users ADD COLUMN last_demo_date TIMESTAMP;
        COMMENT ON COLUMN users.last_demo_date IS 'Fecha del último demo';
    END IF;
END $$;

-- =============================================
-- COLUMNAS DE OAUTH/PERFIL
-- =============================================

-- oauth_profile (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'oauth_profile') THEN
        ALTER TABLE users ADD COLUMN oauth_profile JSONB DEFAULT '{}';
        COMMENT ON COLUMN users.oauth_profile IS 'Datos completos del perfil OAuth';
    END IF;
END $$;

-- profile_picture_url (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'profile_picture_url') THEN
        ALTER TABLE users ADD COLUMN profile_picture_url VARCHAR(500);
        COMMENT ON COLUMN users.profile_picture_url IS 'URL de la foto de perfil';
    END IF;
END $$;

-- timezone (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'timezone') THEN
        ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC';
        COMMENT ON COLUMN users.timezone IS 'Zona horaria del usuario';
    END IF;
END $$;

-- preferred_language (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'preferred_language') THEN
        ALTER TABLE users ADD COLUMN preferred_language VARCHAR(10) DEFAULT 'en';
        COMMENT ON COLUMN users.preferred_language IS 'Idioma preferido';
    END IF;
END $$;

-- interests (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'interests') THEN
        ALTER TABLE users ADD COLUMN interests JSONB DEFAULT '[]';
        COMMENT ON COLUMN users.interests IS 'Lista de intereses del usuario';
    END IF;
END $$;

-- oauth_provider (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'oauth_provider') THEN
        ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(20);
        COMMENT ON COLUMN users.oauth_provider IS 'Proveedor OAuth (google, microsoft, github, apple)';
    END IF;
END $$;

-- oauth_access_token (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'oauth_access_token') THEN
        ALTER TABLE users ADD COLUMN oauth_access_token VARCHAR(500);
        COMMENT ON COLUMN users.oauth_access_token IS 'Token de acceso OAuth';
    END IF;
END $$;

-- oauth_refresh_token (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'oauth_refresh_token') THEN
        ALTER TABLE users ADD COLUMN oauth_refresh_token VARCHAR(500);
        COMMENT ON COLUMN users.oauth_refresh_token IS 'Token de refresco OAuth';
    END IF;
END $$;

-- oauth_token_expires_at (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'oauth_token_expires_at') THEN
        ALTER TABLE users ADD COLUMN oauth_token_expires_at TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN users.oauth_token_expires_at IS 'Fecha de expiración del token OAuth';
    END IF;
END $$;

-- =============================================
-- COLUMNAS DE ACTUALIZACIÓN
-- =============================================

-- updated_at (si no existe)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'updated_at') THEN
        ALTER TABLE users ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
        COMMENT ON COLUMN users.updated_at IS 'Fecha de última actualización';
    END IF;
END $$;

-- =============================================
-- ÍNDICES RECOMENDADOS
-- =============================================

-- Índice para búsqueda por email
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_users_email') THEN
        CREATE INDEX idx_users_email ON users(email) WHERE email IS NOT NULL;
    END IF;
END $$;

-- Índice para búsqueda por phone_number
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_users_phone') THEN
        CREATE INDEX idx_users_phone ON users(phone_number) WHERE phone_number IS NOT NULL;
    END IF;
END $$;

-- Índice para búsqueda por oauth_provider
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_users_oauth_provider') THEN
        CREATE INDEX idx_users_oauth_provider ON users(oauth_provider) WHERE oauth_provider IS NOT NULL;
    END IF;
END $$;

-- =============================================
-- MENSAJE DE ÉXITO
-- =============================================

DO $$
BEGIN
    RAISE NOTICE '✅ Migración completada. Todas las columnas han sido agregadas a la tabla users.';
END $$;
