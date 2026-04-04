"""
OAuth Providers - Handlers para proveedores OAuth
Separado de oauth_profile_service.py
"""
import base64
import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger("oauth_providers")


class GoogleOAuthProvider:
    """Handler para perfil de Google OAuth"""
    
    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Google con máxima información"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Info básica
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                userinfo = userinfo_response.json()
                
                # People API
                people_response = await client.get(
                    "https://people.googleapis.com/v1/people/me",
                    params={
                        "personFields": "names,emailAddresses,photos,locales,addresses,birthdays,genders,occupations,organizations,phoneNumbers,urls,biographies,interests"
                    },
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                people_data = people_response.json()
                
                # Calendario para timezone
                calendar_response = await client.get(
                    "https://www.googleapis.com/calendar/v3/users/me/settings/timezone",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                timezone_data = calendar_response.json()
                
                return {
                    "provider": "google",
                    "basic": {
                        "email": userinfo.get("email"),
                        "name": userinfo.get("name"),
                        "given_name": userinfo.get("given_name"),
                        "family_name": userinfo.get("family_name"),
                        "picture": userinfo.get("picture"),
                        "locale": userinfo.get("locale"),
                        "verified_email": userinfo.get("verified_email", False)
                    },
                    "extended": self._parse_people_data(people_data),
                    "preferences": {
                        "timezone": timezone_data.get("value", "UTC"),
                        "language": userinfo.get("locale", "en").split("-")[0]
                    }
                }
        except Exception as e:
            logger.error(f"Error fetching Google profile: {e}")
            return {"provider": "google", "error": str(e)}
    
    def _parse_people_data(self, people_data: Dict) -> Dict[str, Any]:
        """Parsea datos de Google People API"""
        extended = {}
        
        if "addresses" in people_data:
            addresses = people_data["addresses"]
            if addresses:
                addr = addresses[0]
                extended["location"] = {
                    "city": addr.get("city"),
                    "country": addr.get("country"),
                    "formatted": addr.get("formattedValue")
                }
        
        if "organizations" in people_data:
            orgs = people_data["organizations"]
            if orgs:
                org = orgs[0]
                extended["work"] = {
                    "company": org.get("name"),
                    "title": org.get("title"),
                    "department": org.get("department")
                }
        
        if "biographies" in people_data:
            bios = people_data["biographies"]
            if bios:
                extended["bio"] = bios[0].get("value")
        
        if "interests" in people_data:
            interests = people_data["interests"]
            extended["interests"] = [i.get("value") for i in interests]
        
        if "phoneNumbers" in people_data:
            phones = people_data["phoneNumbers"]
            extended["phones"] = [p.get("value") for p in phones]
        
        if "urls" in people_data:
            urls = people_data["urls"]
            extended["urls"] = [u.get("value") for u in urls]
        
        return extended


class MicrosoftOAuthProvider:
    """Handler para perfil de Microsoft/Azure AD"""
    
    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Microsoft"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_data = response.json()
                
                # Foto de perfil
                photo_url = None
                try:
                    photo_response = await client.get(
                        "https://graph.microsoft.com/v1.0/me/photo/$value",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    if photo_response.status_code == 200:
                        photo_b64 = base64.b64encode(photo_response.content).decode("ascii")
                        photo_url = f"data:image/jpeg;base64,{photo_b64}"
                except Exception:
                    pass
                
                return {
                    "provider": "microsoft",
                    "basic": {
                        "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                        "name": user_data.get("displayName"),
                        "given_name": user_data.get("givenName"),
                        "family_name": user_data.get("surname"),
                        "picture": photo_url,
                        "job_title": user_data.get("jobTitle"),
                        "office_location": user_data.get("officeLocation"),
                        "mobile_phone": user_data.get("mobilePhone"),
                        "business_phones": user_data.get("businessPhones", [])
                    },
                    "preferences": {
                        "language": user_data.get("preferredLanguage", "en"),
                        "timezone": "UTC"
                    }
                }
        except Exception as e:
            logger.error(f"Error fetching Microsoft profile: {e}")
            return {"provider": "microsoft", "error": str(e)}


class GitHubOAuthProvider:
    """Handler para perfil de GitHub"""
    
    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de GitHub"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_data = response.json()
                
                return {
                    "provider": "github",
                    "basic": {
                        "email": user_data.get("email"),
                        "name": user_data.get("name"),
                        "username": user_data.get("login"),
                        "picture": user_data.get("avatar_url"),
                        "bio": user_data.get("bio"),
                        "location": user_data.get("location"),
                        "company": user_data.get("company"),
                        "blog": user_data.get("blog"),
                        "twitter_username": user_data.get("twitter_username")
                    },
                    "stats": {
                        "public_repos": user_data.get("public_repos", 0),
                        "followers": user_data.get("followers", 0),
                        "following": user_data.get("following", 0)
                    }
                }
        except Exception as e:
            logger.error(f"Error fetching GitHub profile: {e}")
            return {"provider": "github", "error": str(e)}


class AppleOAuthProvider:
    """Handler para perfil de Apple (limitado por privacidad)"""
    
    async def get_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Apple - información limitada por privacidad"""
        return {
            "provider": "apple",
            "basic": {
                "email": None,
                "name": None
            },
            "note": "Apple proporciona información limitada por políticas de privacidad"
        }


# Factory para obtener provider
PROVIDERS = {
    "google": GoogleOAuthProvider(),
    "microsoft": MicrosoftOAuthProvider(),
    "github": GitHubOAuthProvider(),
    "apple": AppleOAuthProvider()
}


async def get_provider_profile(provider: str, access_token: str) -> Dict[str, Any]:
    """Obtiene perfil del proveedor especificado"""
    if provider not in PROVIDERS:
        raise ValueError(f"Proveedor no soportado: {provider}")
    
    provider_instance = PROVIDERS[provider]
    return await provider_instance.get_profile(access_token)
