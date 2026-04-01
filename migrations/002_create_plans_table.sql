-- =============================================
-- CREAR TABLA PLANS (Si no existe)
-- Necesaria para la relación plan_id en users
-- =============================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'plans') THEN
        CREATE TABLE plans (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            price FLOAT NOT NULL DEFAULT 0.0,
            currency VARCHAR(3) DEFAULT 'USD',
            requests_per_month INTEGER DEFAULT 0,
            max_file_size_mb INTEGER DEFAULT 1,
            features JSONB DEFAULT '[]',
            is_active BOOLEAN DEFAULT TRUE,
            is_demo BOOLEAN DEFAULT FALSE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        COMMENT ON TABLE plans IS 'Planes de suscripción disponibles';
        COMMENT ON COLUMN plans.name IS 'Identificador único del plan (demo, normal, pro, enterprise)';
        COMMENT ON COLUMN plans.display_name IS 'Nombre visible para usuarios';
        
        -- Insertar planes por defecto
        INSERT INTO plans (name, display_name, description, price, requests_per_month, max_file_size_mb, features, is_demo) VALUES
        ('demo', 'Demo', 'Plan de prueba gratuito', 0, 50, 1, '["basic_chat"]', TRUE),
        ('normal', 'Normal', 'Plan básico para usuarios individuales', 9.99, 1000, 10, '["basic_chat", "file_upload", "vision"]', FALSE),
        ('pro', 'Pro', 'Plan profesional con funciones avanzadas', 29.99, 5000, 50, '["basic_chat", "file_upload", "vision", "advanced_agents", "priority_support"]', FALSE),
        ('enterprise', 'Enterprise', 'Plan empresarial con soporte dedicado', 99.99, 50000, 100, '["all_features", "dedicated_support", "custom_agents", "analytics"]', FALSE);
        
        RAISE NOTICE '✅ Tabla plans creada con planes por defecto';
    ELSE
        RAISE NOTICE 'ℹ️ Tabla plans ya existe';
    END IF;
END $$;
