class IdentityPolicy:
    @staticmethod
    def normalize_category(category: str | None) -> str:
        return (category or "other").strip().lower()

    @staticmethod
    def can_enter_category(persona, category: str) -> bool:
        return IdentityPolicy.normalize_category(persona.category) == IdentityPolicy.normalize_category(category)

    @staticmethod
    def can_view_public_persona(viewer_persona, target_persona) -> bool:
        if not getattr(target_persona, "is_public", False):
            return False

        return (
            IdentityPolicy.normalize_category(viewer_persona.category)
            == IdentityPolicy.normalize_category(target_persona.category)
        )

    @staticmethod
    def can_start_dm(sender_persona, target_persona) -> bool:
        if not getattr(target_persona, "is_public", False):
            return False

        if sender_persona.id == target_persona.id:
            return False

        return (
            IdentityPolicy.normalize_category(sender_persona.category)
            == IdentityPolicy.normalize_category(target_persona.category)
        )

    @staticmethod
    def can_access_dm(persona, thread) -> bool:
        return persona.id in (thread.persona_a_id, thread.persona_b_id)

    @staticmethod
    def can_send_dm(persona, thread) -> bool:
        return IdentityPolicy.can_access_dm(persona, thread)

    @staticmethod
    def can_use_persona(user_id: int, persona) -> bool:
        return persona is not None and persona.user_id == user_id