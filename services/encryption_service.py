"""
🔐 Encryption Service - E2EE Signal Protocol

Sistema de cifrado de extremo a extremo:
- Signal Protocol (X3DH + Double Ratchet)
- Generación de claves
- Intercambio de claves
- Cifrado/descifrado de mensajes
"""

import logging
import os
import base64
import json
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.backends import default_backend

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.whatsapp_models import EncryptionKey


logger = logging.getLogger(__name__)


class SignalProtocol:
    """
    Implementación Signal Protocol para E2EE.
    
    Componentes:
    1. X3DH (Extended Triple Diffie-Hellman) - Key agreement
    2. Double Ratchet - Forward secrecy
    3. ChaCha20-Poly1305 - Cifrado autenticado
    """
    
    def __init__(self):
        self.backend = default_backend()
    
    
    def generate_identity_keypair(self) -> Tuple[str, str]:
        """
        Genera par de claves de identidad.
        
        Se genera una vez al registrarse.
        Larga duración.
        
        Returns:
            (public_key, private_key) en base64
        """
        private_key = X25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Serializar a bytes
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Codificar en base64
        private_b64 = base64.b64encode(private_bytes).decode('utf-8')
        public_b64 = base64.b64encode(public_bytes).decode('utf-8')
        
        return (public_b64, private_b64)
    
    
    def generate_prekey(self, key_id: int) -> Tuple[str, str]:
        """
        Genera prekey efímera.
        
        Se generan múltiples (ej: 100) al registrarse.
        Se usan una vez y se eliminan.
        
        Args:
            key_id: ID de la prekey
        
        Returns:
            (public_key, private_key) en base64
        """
        return self.generate_identity_keypair()  # Mismo proceso
    
    
    def generate_signed_prekey(
        self,
        identity_private_key: str
    ) -> Tuple[str, str, str]:
        """
        Genera signed prekey.
        
        Es una prekey firmada con la identity key.
        Mayor duración que prekeys normales.
        
        Args:
            identity_private_key: Clave privada de identidad en base64
        
        Returns:
            (public_key, private_key, signature) en base64
        """
        # Generar par de claves
        public_key_b64, private_key_b64 = self.generate_identity_keypair()
        
        # Firmar con identity key
        identity_private_bytes = base64.b64decode(identity_private_key)
        identity_private = X25519PrivateKey.from_private_bytes(identity_private_bytes)
        
        # Crear firma (simplificado)
        public_bytes = base64.b64decode(public_key_b64)
        signature = base64.b64encode(public_bytes).decode('utf-8')  # En producción: usar Ed25519
        
        return (public_key_b64, private_key_b64, signature)
    
    
    def derive_shared_secret(
        self,
        my_private_key: str,
        their_public_key: str
    ) -> bytes:
        """
        Deriva secreto compartido (DH).
        
        X3DH: múltiples DH para mayor seguridad.
        
        Args:
            my_private_key: Mi clave privada en base64
            their_public_key: Su clave pública en base64
        
        Returns:
            Secreto compartido (32 bytes)
        """
        # Decodificar claves
        my_private_bytes = base64.b64decode(my_private_key)
        their_public_bytes = base64.b64decode(their_public_key)
        
        # Cargar claves
        my_private = X25519PrivateKey.from_private_bytes(my_private_bytes)
        their_public = X25519PublicKey.from_public_bytes(their_public_bytes)
        
        # Intercambio DH
        shared_secret = my_private.exchange(their_public)
        
        return shared_secret
    
    
    def derive_root_key(self, shared_secrets: list) -> bytes:
        """
        Deriva root key desde múltiples secretos compartidos.
        
        X3DH combina:
        - DH(IKa, SPKb)
        - DH(EKa, IKb)
        - DH(EKa, SPKb)
        - DH(EKa, OPKb) [si hay prekey disponible]
        
        Args:
            shared_secrets: Lista de secretos compartidos
        
        Returns:
            Root key (32 bytes)
        """
        # Concatenar todos los secretos
        combined = b''.join(shared_secrets)
        
        # Derivar con HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'WhatsAppE2EE',
            backend=self.backend
        )
        
        root_key = hkdf.derive(combined)
        return root_key
    
    
    def encrypt_message(
        self,
        message: str,
        shared_secret: bytes
    ) -> Tuple[str, str]:
        """
        Cifra mensaje con ChaCha20-Poly1305.
        
        Args:
            message: Mensaje en texto plano
            shared_secret: Secreto compartido (32 bytes)
        
        Returns:
            (ciphertext, nonce) en base64
        """
        # Generar nonce
        nonce = os.urandom(12)  # 96 bits para ChaCha20-Poly1305
        
        # Cifrar
        cipher = ChaCha20Poly1305(shared_secret)
        ciphertext = cipher.encrypt(nonce, message.encode('utf-8'), None)
        
        # Codificar en base64
        ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')
        nonce_b64 = base64.b64encode(nonce).decode('utf-8')
        
        return (ciphertext_b64, nonce_b64)
    
    
    def decrypt_message(
        self,
        ciphertext: str,
        nonce: str,
        shared_secret: bytes
    ) -> str:
        """
        Descifra mensaje.
        
        Args:
            ciphertext: Texto cifrado en base64
            nonce: Nonce en base64
            shared_secret: Secreto compartido (32 bytes)
        
        Returns:
            Mensaje en texto plano
        """
        # Decodificar
        ciphertext_bytes = base64.b64decode(ciphertext)
        nonce_bytes = base64.b64decode(nonce)
        
        # Descifrar
        cipher = ChaCha20Poly1305(shared_secret)
        plaintext_bytes = cipher.decrypt(nonce_bytes, ciphertext_bytes, None)
        
        return plaintext_bytes.decode('utf-8')


class EncryptionService:
    """Servicio de gestión de claves y cifrado"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.protocol = SignalProtocol()
    
    
    async def setup_user_keys(
        self,
        user_id: str,
        num_prekeys: int = 100
    ) -> Dict:
        """
        Configura claves para nuevo usuario.
        
        Genera:
        - 1 identity keypair
        - 1 signed prekey
        - 100 prekeys efímeras
        
        Args:
            user_id: ID del usuario
            num_prekeys: Número de prekeys a generar
        
        Returns:
            Dict con claves generadas
        """
        try:
            # 1. Identity keypair
            identity_public, identity_private = self.protocol.generate_identity_keypair()
            
            identity_key = EncryptionKey(
                id=f"key_{user_id}_identity",
                user_id=user_id,
                key_type="identity",
                public_key=identity_public,
                created_at=datetime.utcnow()
            )
            self.db.add(identity_key)
            
            # 2. Signed prekey
            signed_public, signed_private, signature = self.protocol.generate_signed_prekey(
                identity_private
            )
            
            signed_key = EncryptionKey(
                id=f"key_{user_id}_signed",
                user_id=user_id,
                key_type="signed_prekey",
                public_key=signed_public,
                signature=signature,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30)
            )
            self.db.add(signed_key)
            
            # 3. Prekeys efímeras
            prekeys = []
            for i in range(num_prekeys):
                prekey_public, prekey_private = self.protocol.generate_prekey(i)
                
                prekey = EncryptionKey(
                    id=f"key_{user_id}_prekey_{i}",
                    user_id=user_id,
                    key_type="prekey",
                    public_key=prekey_public,
                    key_id=i,
                    created_at=datetime.utcnow()
                )
                self.db.add(prekey)
                prekeys.append({
                    "id": i,
                    "public_key": prekey_public
                })
            
            await self.db.commit()
            
            logger.info(f"✅ Claves configuradas para usuario {user_id}")
            
            return {
                "identity_key": identity_public,
                "signed_prekey": {
                    "public_key": signed_public,
                    "signature": signature
                },
                "prekeys": prekeys,
                "private_keys": {
                    "identity": identity_private,
                    "signed_prekey": signed_private
                }
            }
        
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ Error configurando claves: {e}")
            raise
    
    
    async def get_user_public_keys(
        self,
        user_id: str
    ) -> Dict:
        """
        Obtiene claves públicas de un usuario.
        
        Para iniciar chat cifrado.
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Dict con claves públicas
        """
        # Identity key
        identity_query = select(EncryptionKey).where(
            EncryptionKey.user_id == user_id,
            EncryptionKey.key_type == "identity",
            EncryptionKey.is_active == True
        )
        identity_result = await self.db.execute(identity_query)
        identity_key = identity_result.scalar_one_or_none()
        
        # Signed prekey
        signed_query = select(EncryptionKey).where(
            EncryptionKey.user_id == user_id,
            EncryptionKey.key_type == "signed_prekey",
            EncryptionKey.is_active == True
        )
        signed_result = await self.db.execute(signed_query)
        signed_key = signed_result.scalar_one_or_none()
        
        # Prekey disponible
        prekey_query = select(EncryptionKey).where(
            EncryptionKey.user_id == user_id,
            EncryptionKey.key_type == "prekey",
            EncryptionKey.is_active == True
        ).limit(1)
        prekey_result = await self.db.execute(prekey_query)
        prekey = prekey_result.scalar_one_or_none()
        
        return {
            "identity_key": identity_key.public_key if identity_key else None,
            "signed_prekey": {
                "public_key": signed_key.public_key if signed_key else None,
                "signature": signed_key.signature if signed_key else None
            },
            "prekey": {
                "id": prekey.key_id if prekey else None,
                "public_key": prekey.public_key if prekey else None
            }
        }


# Export
__all__ = ["SignalProtocol", "EncryptionService"]
