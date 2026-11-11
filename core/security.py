"""دوال تشفير كلمات المرور والتحقق منها."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .config import PBKDF2_ITERATIONS


def hash_password(password: str) -> str:
    """ينشئ بصمة آمنة لكلمة المرور باستخدام PBKDF2-HMAC-SHA256."""
    if not isinstance(password, str) or not password:
        raise ValueError("كلمة المرور لا يمكن أن تكون فارغة.")

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    """يتحقق من كلمة المرور بطريقة آمنة ضد هجمات التوقيت."""
    if not password or not stored:
        return False

    try:
        algorithm, iterations, salt, digest = str(stored).split("$", 3)
        if algorithm != "pbkdf2":
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(calculated, digest)
    except (ValueError, TypeError):
        return False


def validate_password(password: str) -> str | None:
    """يعيد رسالة الخطأ إن كانت كلمة المرور غير صالحة، أو None إن كانت صالحة."""
    if not isinstance(password, str) or len(password) < 8:
        return "كلمة المرور يجب أن تكون 8 أحرف على الأقل."
    if not any(character.isalpha() for character in password):
        return "كلمة المرور يجب أن تحتوي على حرف واحد على الأقل."
    if not any(character.isdigit() for character in password):
        return "كلمة المرور يجب أن تحتوي على رقم واحد على الأقل."
    if password.strip() != password:
        return "لا يمكن أن تبدأ كلمة المرور أو تنتهي بمسافات."
    return None
