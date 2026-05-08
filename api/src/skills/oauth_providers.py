from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillOAuthProvider:
    provider_name: str
    start_path: str


SKILL_OAUTH_PROVIDERS: dict[str, SkillOAuthProvider] = {
    "GoogleDrive": SkillOAuthProvider(
        provider_name="GoogleDrive",
        start_path="/auth/google-drive/start",
    ),
    "GoogleMail": SkillOAuthProvider(
        provider_name="GoogleMail",
        start_path="/auth/google-mail/start",
    ),
}


def get_skill_oauth_provider(provider_name: str | None) -> SkillOAuthProvider | None:
    if not provider_name:
        return None
    return SKILL_OAUTH_PROVIDERS.get(provider_name)
