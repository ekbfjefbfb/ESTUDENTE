"""
Tests para el sistema multi-usuario y referidos

Ejecutar con: pytest tests/test_invitation_system.py -v
"""

import pytest
from datetime import datetime, timedelta
from services.invitation_service import InvitationService
from models.models import User, Organization, Referral
import uuid

# =============================================
# FIXTURES
# =============================================

@pytest.fixture
async def test_user(db_session):
    """Crea un usuario de prueba"""
    user = User(
        id=str(uuid.uuid4()),
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        plan_id="creator",
        referral_code="TEST1234"
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def test_organization(db_session, test_user):
    """Crea una organización de prueba"""
    org = Organization(
        id=str(uuid.uuid4()),
        name="Test Organization",
        plan_id="creator",
        shared_message_limit=3000,
        max_members=3
    )
    db_session.add(org)
    await db_session.commit()
    return org


# =============================================
# TESTS DE INVITACIONES A ORGANIZACIÓN
# =============================================

@pytest.mark.asyncio
async def test_create_organization_invitation(db_session, test_organization, test_user):
    """Test: Crear invitación a organización"""
    
    invitation = await InvitationService.create_organization_invitation(
        db=db_session,
        organization_id=test_organization.id,
        invited_by_user_id=test_user.id,
        email="newmember@example.com",
        role="member"
    )
    
    # Verificaciones
    assert invitation is not None
    assert invitation["email"] == "newmember@example.com"
    assert invitation["role"] == "member"
    assert "link" in invitation
    assert "token" in invitation
    assert "expires_at" in invitation
    
    # Verificar que expira en 7 días
    expires_at = datetime.fromisoformat(invitation["expires_at"])
    expected_expiry = datetime.utcnow() + timedelta(days=7)
    assert abs((expires_at - expected_expiry).total_seconds()) < 60


@pytest.mark.asyncio
async def test_create_invitation_without_permission(db_session, test_organization, test_user):
    """Test: No se puede invitar sin plan Creator/Business"""
    
    # Cambiar plan a Starter (no permite invitaciones)
    test_user.plan_id = "starter"
    await db_session.commit()
    
    with pytest.raises(ValueError, match="does not allow invitations"):
        await InvitationService.create_organization_invitation(
            db=db_session,
            organization_id=test_organization.id,
            invited_by_user_id=test_user.id,
            email="newmember@example.com"
        )


@pytest.mark.asyncio
async def test_accept_organization_invitation(db_session, test_organization, test_user):
    """Test: Aceptar invitación a organización"""
    
    # Crear invitación
    invitation = await InvitationService.create_organization_invitation(
        db=db_session,
        organization_id=test_organization.id,
        invited_by_user_id=test_user.id,
        email="newmember@example.com"
    )
    
    # Crear usuario que aceptará
    new_user = User(
        id=str(uuid.uuid4()),
        username="newmember",
        email="newmember@example.com",
        hashed_password="hashed",
        plan_id="trial"
    )
    db_session.add(new_user)
    await db_session.commit()
    
    # Aceptar invitación
    result = await InvitationService.accept_organization_invitation(
        db=db_session,
        token=invitation["token"],
        user_id=new_user.id
    )
    
    # Verificaciones
    assert result is not None
    assert result["organization_id"] == test_organization.id
    assert result["user_id"] == new_user.id
    assert result["role"] == "member"


@pytest.mark.asyncio
async def test_accept_expired_invitation(db_session, test_organization, test_user):
    """Test: No se puede aceptar invitación expirada"""
    
    # Crear invitación que ya expiró
    from models.models import OrganizationInvitation
    import secrets
    
    expired_invitation = OrganizationInvitation(
        id=str(uuid.uuid4()),
        organization_id=test_organization.id,
        invited_by_user_id=test_user.id,
        email="expired@example.com",
        token=secrets.token_urlsafe(32),
        role="member",
        expires_at=datetime.utcnow() - timedelta(days=1)  # Expirada
    )
    db_session.add(expired_invitation)
    await db_session.commit()
    
    # Intentar aceptar
    with pytest.raises(ValueError, match="expired"):
        await InvitationService.accept_organization_invitation(
            db=db_session,
            token=expired_invitation.token,
            user_id=str(uuid.uuid4())
        )


# =============================================
# TESTS DE PROGRAMA DE REFERIDOS
# =============================================

@pytest.mark.asyncio
async def test_create_referral_link(db_session, test_user):
    """Test: Generar link de referido"""
    
    referral_data = await InvitationService.create_referral_link(
        db=db_session,
        user_id=test_user.id
    )
    
    # Verificaciones
    assert referral_data is not None
    assert referral_data["code"] == "TEST1234"
    assert "link" in referral_data
    assert "https://app." in referral_data["link"]
    assert "/ref/TEST1234" in referral_data["link"]
    assert referral_data["total_referrals"] == 0
    assert referral_data["bonus_days_earned"] == 0
    assert referral_data["max_bonus_days"] == 14


@pytest.mark.asyncio
async def test_register_referral(db_session, test_user):
    """Test: Registrar nuevo referido y otorgar bonus"""
    
    # Crear usuario referido
    referred_user = User(
        id=str(uuid.uuid4()),
        username="referred",
        email="referred@example.com",
        hashed_password="hashed",
        plan_id="trial",
        subscription_expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db_session.add(referred_user)
    await db_session.commit()
    
    # Registrar referido
    result = await InvitationService.register_referral(
        db=db_session,
        referral_code="TEST1234",
        referred_user_id=referred_user.id
    )
    
    # Verificaciones
    assert result is not None
    assert result["referrer_id"] == test_user.id
    assert result["referred_id"] == referred_user.id
    assert result["bonus_days_granted"] == 1
    
    # Verificar que se creó registro en BD
    from sqlalchemy import select
    from models.models import Referral
    
    referral_query = await db_session.execute(
        select(Referral).where(Referral.referrer_id == test_user.id)
    )
    referral = referral_query.scalar_one_or_none()
    
    assert referral is not None
    assert referral.referred_id == referred_user.id
    assert referral.bonus_granted is True
    assert referral.bonus_days == 1
    assert referral.status == "COMPLETED"


@pytest.mark.asyncio
async def test_referral_max_bonus_limit(db_session, test_user):
    """Test: No se puede exceder el máximo de 14 días de bonus"""
    
    # Crear 15 referidos (debería dar solo 14 días)
    for i in range(15):
        referred = User(
            id=str(uuid.uuid4()),
            username=f"referred{i}",
            email=f"referred{i}@example.com",
            hashed_password="hashed",
            plan_id="trial"
        )
        db_session.add(referred)
        await db_session.commit()
        
        await InvitationService.register_referral(
            db=db_session,
            referral_code="TEST1234",
            referred_user_id=referred.id
        )
    
    # Verificar estadísticas
    stats = await InvitationService.get_referral_stats(
        db=db_session,
        user_id=test_user.id
    )
    
    assert stats["total_referrals"] == 15
    assert stats["bonus_days_earned"] == 14  # Máximo
    assert stats["max_bonus_days"] == 14


@pytest.mark.asyncio
async def test_self_referral_blocked(db_session, test_user):
    """Test: Usuario no puede referirse a sí mismo"""
    
    with pytest.raises(ValueError, match="cannot refer yourself"):
        await InvitationService.register_referral(
            db=db_session,
            referral_code="TEST1234",
            referred_user_id=test_user.id  # Mismo usuario
        )


@pytest.mark.asyncio
async def test_duplicate_referral_blocked(db_session, test_user):
    """Test: No se puede registrar el mismo referido dos veces"""
    
    # Crear usuario referido
    referred = User(
        id=str(uuid.uuid4()),
        username="referred",
        email="referred@example.com",
        hashed_password="hashed",
        plan_id="trial"
    )
    db_session.add(referred)
    await db_session.commit()
    
    # Primer registro (OK)
    await InvitationService.register_referral(
        db=db_session,
        referral_code="TEST1234",
        referred_user_id=referred.id
    )
    
    # Segundo registro (debe fallar)
    with pytest.raises(ValueError, match="already been referred"):
        await InvitationService.register_referral(
            db=db_session,
            referral_code="TEST1234",
            referred_user_id=referred.id
        )


# =============================================
# TESTS DE ESTADÍSTICAS
# =============================================

@pytest.mark.asyncio
async def test_get_referral_stats(db_session, test_user):
    """Test: Obtener estadísticas de referidos"""
    
    # Crear 3 referidos
    for i in range(3):
        referred = User(
            id=str(uuid.uuid4()),
            username=f"ref{i}",
            email=f"ref{i}@example.com",
            hashed_password="hashed",
            plan_id="trial"
        )
        db_session.add(referred)
        await db_session.commit()
        
        await InvitationService.register_referral(
            db=db_session,
            referral_code="TEST1234",
            referred_user_id=referred.id
        )
    
    # Obtener estadísticas
    stats = await InvitationService.get_referral_stats(
        db=db_session,
        user_id=test_user.id
    )
    
    # Verificaciones
    assert stats["total_referrals"] == 3
    assert stats["completed_referrals"] == 3
    assert stats["bonus_days_earned"] == 3
    assert stats["max_bonus_days"] == 14
    assert stats["progress_percent"] == (3/14) * 100
    assert len(stats["recent_referrals"]) == 3


@pytest.mark.asyncio
async def test_organization_invitation_list(db_session, test_organization, test_user):
    """Test: Listar invitaciones de una organización"""
    
    # Crear 3 invitaciones
    for i in range(3):
        await InvitationService.create_organization_invitation(
            db=db_session,
            organization_id=test_organization.id,
            invited_by_user_id=test_user.id,
            email=f"member{i}@example.com"
        )
    
    # Listar todas
    invitations = await InvitationService.get_organization_invitations(
        db=db_session,
        organization_id=test_organization.id
    )
    
    assert len(invitations) == 3
    
    # Listar solo pendientes
    pending = await InvitationService.get_organization_invitations(
        db=db_session,
        organization_id=test_organization.id,
        status="pending"
    )
    
    assert len(pending) == 3


# =============================================
# TESTS DE INTEGRACIÓN
# =============================================

@pytest.mark.asyncio
async def test_full_invitation_workflow(db_session, test_organization, test_user):
    """Test: Flujo completo de invitación"""
    
    # 1. Usuario owner invita a alguien
    invitation = await InvitationService.create_organization_invitation(
        db=db_session,
        organization_id=test_organization.id,
        invited_by_user_id=test_user.id,
        email="newmember@example.com"
    )
    
    assert "token" in invitation
    
    # 2. Nuevo usuario se registra
    new_user = User(
        id=str(uuid.uuid4()),
        username="newmember",
        email="newmember@example.com",
        hashed_password="hashed",
        plan_id="trial"
    )
    db_session.add(new_user)
    await db_session.commit()
    
    # 3. Nuevo usuario acepta invitación
    result = await InvitationService.accept_organization_invitation(
        db=db_session,
        token=invitation["token"],
        user_id=new_user.id
    )
    
    assert result["organization_id"] == test_organization.id
    
    # 4. Verificar que ahora es miembro
    from sqlalchemy import select
    from models.models import OrganizationMember
    
    member_query = await db_session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == test_organization.id,
            OrganizationMember.user_id == new_user.id
        )
    )
    member = member_query.scalar_one_or_none()
    
    assert member is not None
    assert member.role == "member"
    assert member.is_active is True


@pytest.mark.asyncio
async def test_full_referral_workflow(db_session, test_user):
    """Test: Flujo completo de referidos"""
    
    # 1. Usuario obtiene su link
    referral_data = await InvitationService.create_referral_link(
        db=db_session,
        user_id=test_user.id
    )
    
    assert referral_data["code"] == "TEST1234"
    
    # 2. Amigo se registra con el código
    friend = User(
        id=str(uuid.uuid4()),
        username="friend",
        email="friend@example.com",
        hashed_password="hashed",
        plan_id="trial",
        subscription_expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db_session.add(friend)
    await db_session.commit()
    
    # 3. Sistema registra el referido
    result = await InvitationService.register_referral(
        db=db_session,
        referral_code="TEST1234",
        referred_user_id=friend.id
    )
    
    assert result["bonus_days_granted"] == 1
    
    # 4. Verificar que el referidor ganó 1 día
    stats = await InvitationService.get_referral_stats(
        db=db_session,
        user_id=test_user.id
    )
    
    assert stats["bonus_days_earned"] == 1
    assert stats["total_referrals"] == 1


# =============================================
# EJECUTAR TESTS
# =============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
