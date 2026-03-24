"""
📱 Cliente de ejemplo para VoiceNotes SST - React Native / JavaScript
Demuestra el uso del sistema offline-first, resumible e idempotente.
"""

import { VoiceNoteClient } from './voice_note_client';

// =============================================
// EJEMPLO 1: Grabar nota offline y subir después
// =============================================

async function recordAndSyncOffline() {
    const client = new VoiceNoteClient({
        apiBaseUrl: 'https://api.tu-app.com',
        authToken: 'tu-jwt-token',
        deviceId: 'device-123-abc',
        chunkSize: 256 * 1024, // 256KB chunks
    });

    // 1. GRABAR LOCALMENTE (sin conexión)
    console.log('🎙️ Iniciando grabación local...');
    const recording = await client.startLocalRecording({
        title: 'Nota de reunión con equipo',
    });

    // Grabar por 30 segundos...
    await recording.recordFor(30000);

    // 2. GUARDAR LOCALMENTE (offline)
    const localNote = await recording.saveLocal();
    console.log('💾 Nota guardada localmente:', localNote.clientRecordId);

    // 3. CUANDO HAY CONEXIÓN: Subir
    console.log('📤 Iniciando subida resumible...');
    
    // La subida es resumible: si falla, se puede continuar
    const uploadResult = await client.uploadVoiceNote(localNote, {
        onProgress: (progress) => {
            console.log(`📊 Progreso: ${progress.percentage}%`);
        },
        onChunkUploaded: (chunkIndex, total) => {
            console.log(`✅ Chunk ${chunkIndex + 1}/${total} subido`);
        },
    });

    console.log('🎉 Subida completada:', uploadResult.voiceNoteId);

    // 4. PROCESAR (STT + Resumen)
    console.log('⚙️ Encolando procesamiento...');
    const job = await client.enqueueProcessing(uploadResult.voiceNoteId, {
        jobType: 'full_pipeline', // transcription + summarization + extraction
    });

    // 5. POLLING del estado
    const finalNote = await client.waitForCompletion(
        uploadResult.voiceNoteId,
        job.id,
        { maxWaitMs: 60000 }
    );

    console.log('✅ Nota procesada:');
    console.log('   Transcripción:', finalNote.transcript_preview);
    console.log('   Resumen:', finalNote.summary);
    console.log('   Items extraídos:', finalNote.extracted_items_count);
}


// =============================================
// EJEMPLO 2: Sincronización offline-first
// =============================================

async function syncOfflineNotes() {
    const client = new VoiceNoteClient({
        apiBaseUrl: 'https://api.tu-app.com',
        authToken: 'tu-jwt-token',
        deviceId: 'device-123-abc',
    });

    // 1. Obtener notas locales
    const localNotes = await client.getLocalVoiceNotes();
    const localRecordIds = localNotes.map(n => n.clientRecordId);

    console.log(`📱 Cliente tiene ${localRecordIds.length} notas locales`);

    // 2. SYNC CHECK - Qué necesita subir/bajar
    const syncStatus = await client.syncCheck({
        clientLastSyncAt: new Date('2026-03-20T10:00:00Z'),
        clientRecordIds: localRecordIds,
    });

    console.log('🔄 Sync Check Results:');
    console.log('   Necesita subir:', syncStatus.missing_on_server.length);
    console.log('   Necesita bajar:', syncStatus.missing_on_client.length);
    console.log('   Conflictos:', syncStatus.conflicts.length);

    // 3. SUBIR lo que falta en servidor
    for (const recordId of syncStatus.missing_on_server) {
        const localNote = localNotes.find(n => n.clientRecordId === recordId);
        if (localNote) {
            console.log(`📤 Subiendo ${recordId}...`);
            await client.uploadVoiceNote(localNote);
        }
    }

    // 4. BAJAR lo que falta en cliente
    for (const noteInfo of syncStatus.details_to_download) {
        console.log(`📥 Descargando ${noteInfo.id}...`);
        const fullNote = await client.getVoiceNote(noteInfo.id);
        await client.saveLocal(fullNote);
    }

    console.log('✅ Sincronización completada');
}


// =============================================
// EJEMPLO 3: Reanudar subida interrumpida
// =============================================

async function resumeInterruptedUpload() {
    const client = new VoiceNoteClient({ /* config */ });

    // Subida anterior se interrumpió en el chunk 15 de 42
    const voiceNoteId = 'voice-note-uuid-del-servidor';

    // 1. CHECK STATUS - Saber qué chunks faltan
    const status = await client.getUploadStatus(voiceNoteId);
    
    console.log(`📊 Estado de subida:`);
    console.log(`   Progreso: ${status.upload_progress_pct}%`);
    console.log(`   Chunks faltantes: ${status.missing_chunks.length}`);
    console.log(`   Índices faltantes:`, status.missing_chunks);

    // 2. REANUDAR desde donde quedó
    // El cliente automáticamente solo sube los chunks faltantes
    const localNote = await client.getLocalVoiceNoteByServerId(voiceNoteId);
    
    await client.uploadVoiceNote(localNote, {
        resumeFromStatus: status, // Solo sube los que faltan
        onProgress: (p) => console.log(`${p.percentage}% completado`),
    });

    console.log('✅ Subida reanudada y completada');
}


// =============================================
// EJEMPLO 4: Idempotencia - crear sin duplicar
// =============================================

async function idempotentCreate() {
    const client = new VoiceNoteClient({ /* config */ });

    // El client_record_id es determinístico y único
    // Si el servidor ya tiene este ID, retorna la existente (201 si nueva, 200 si existe)
    const clientRecordId = `user-123:device-abc:${Date.now()}:random-xyz`;

    // Esto es idempotente: llamar 10 veces = mismo resultado
    const note = await client.createVoiceNote({
        clientRecordId: clientRecordId,
        deviceId: 'device-abc',
        totalDurationMs: 60000,
        totalBytes: 1024000,
        audioFormat: 'webm',
        language: 'es',
        recordedAt: new Date(),
    });

    console.log('Nota creada/existente:', note.id);
    console.log('Era nueva?', note.isNew); // true si se creó, false si ya existía
}


// =============================================
// IMPLEMENTACIÓN DEL CLIENTE (VoiceNoteClient)
// =============================================

class VoiceNoteClient {
    constructor(config) {
        this.apiBaseUrl = config.apiBaseUrl;
        this.authToken = config.authToken;
        this.deviceId = config.deviceId;
        this.chunkSize = config.chunkSize || (256 * 1024);
    }

    async request(method, path, body = null) {
        const response = await fetch(`${this.apiBaseUrl}${path}`, {
            method,
            headers: {
                'Authorization': `Bearer ${this.authToken}`,
                'Content-Type': 'application/json',
            },
            body: body ? JSON.stringify(body) : null,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Request failed');
        }

        return response.json();
    }

    async createVoiceNote(params) {
        return this.request('POST', '/api/voice-notes/create', params);
    }

    async uploadChunk(voiceNoteId, chunkIndex, chunkData) {
        // Calcular SHA256 del chunk
        const checksum = await this.sha256(chunkData);
        
        // Convertir a base64
        const base64Data = btoa(String.fromCharCode(...new Uint8Array(chunkData)));

        return this.request('POST', `/api/voice-notes/${voiceNoteId}/chunks`, {
            chunk_index: chunkIndex,
            chunk_data: base64Data,
            checksum_sha256: checksum,
        });
    }

    async getUploadStatus(voiceNoteId) {
        return this.request('GET', `/api/voice-notes/${voiceNoteId}/upload-status`);
    }

    async uploadVoiceNote(localNote, options = {}) {
        // 1. Crear/verificar en servidor (idempotente)
        const serverNote = await this.createVoiceNote({
            clientRecordId: localNote.clientRecordId,
            deviceId: this.deviceId,
            totalDurationMs: localNote.durationMs,
            totalBytes: localNote.audioData.byteLength,
            audioFormat: localNote.format,
            language: localNote.language,
            recordedAt: localNote.recordedAt,
            title: localNote.title,
        });

        const voiceNoteId = serverNote.id;

        // 2. Si hay resume, obtener chunks faltantes
        let chunksToUpload = [];
        if (options.resumeFromStatus) {
            const missing = options.resumeFromStatus.missing_chunks;
            for (const idx of missing) {
                chunksToUpload.push({
                    index: idx,
                    data: localNote.getChunkData(idx, this.chunkSize),
                });
            }
        } else {
            // Subir todos los chunks
            const totalChunks = Math.ceil(localNote.audioData.byteLength / this.chunkSize);
            for (let i = 0; i < totalChunks; i++) {
                chunksToUpload.push({
                    index: i,
                    data: localNote.getChunkData(i, this.chunkSize),
                });
            }
        }

        // 3. Subir chunks
        let uploadedCount = 0;
        for (const chunk of chunksToUpload) {
            const result = await this.uploadChunk(voiceNoteId, chunk.index, chunk.data);
            uploadedCount++;

            if (options.onChunkUploaded) {
                options.onChunkUploaded(chunk.index, chunksToUpload.length);
            }

            if (options.onProgress) {
                options.onProgress({
                    uploaded: uploadedCount,
                    total: chunksToUpload.length,
                    percentage: Math.round((uploadedCount / chunksToUpload.length) * 100),
                });
            }
        }

        return { voiceNoteId, uploadedChunks: uploadedCount };
    }

    async enqueueProcessing(voiceNoteId, options = {}) {
        return this.request('POST', `/api/voice-notes/${voiceNoteId}/process`, {
            job_type: options.jobType || 'full_pipeline',
            priority: options.priority || 0,
            job_params: options.params || {},
        });
    }

    async getProcessingJob(voiceNoteId, jobId) {
        return this.request('GET', `/api/voice-notes/${voiceNoteId}/jobs/${jobId}`);
    }

    async waitForCompletion(voiceNoteId, jobId, options = {}) {
        const startTime = Date.now();
        const maxWait = options.maxWaitMs || 60000;
        const pollInterval = options.pollIntervalMs || 2000;

        while (Date.now() - startTime < maxWait) {
            const job = await this.getProcessingJob(voiceNoteId, jobId);

            if (job.status === 'completed') {
                // Obtener nota completa
                return this.request('GET', `/api/voice-notes/${voiceNoteId}`);
            }

            if (job.status === 'failed') {
                throw new Error(`Processing failed: ${job.error_info?.message || 'Unknown error'}`);
            }

            // Esperar antes de siguiente poll
            await new Promise(r => setTimeout(r, pollInterval));
        }

        throw new Error('Timeout waiting for processing completion');
    }

    async syncCheck(params) {
        return this.request('POST', '/api/voice-notes/sync-check', {
            device_id: this.deviceId,
            client_last_sync_at: params.clientLastSyncAt.toISOString(),
            client_record_ids: params.clientRecordIds,
        });
    }

    async getVoiceNote(voiceNoteId) {
        return this.request('GET', `/api/voice-notes/${voiceNoteId}`);
    }

    async listVoiceNotes(options = {}) {
        const query = new URLSearchParams();
        if (options.status) query.append('status', options.status);
        if (options.limit) query.append('limit', options.limit);
        if (options.offset) query.append('offset', options.offset);

        return this.request('GET', `/api/voice-notes?${query}`);
    }

    async sha256(data) {
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }

    // Métodos de storage local (AsyncStorage, SQLite, etc)
    async getLocalVoiceNotes() { /* implementación */ }
    async saveLocal(note) { /* implementación */ }
    async getLocalVoiceNoteByServerId(serverId) { /* implementación */ }
    async startLocalRecording(options) { /* implementación */ }
}


// =============================================
// EXPORTAR
// =============================================

export { VoiceNoteClient, recordAndSyncOffline, syncOfflineNotes, resumeInterruptedUpload, idempotentCreate };
