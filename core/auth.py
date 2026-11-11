"""المصادقة وإدارة الجلسات والصلاحيات."""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from . import db
from .config import (
    LOGIN_WINDOW_MINUTES,
    MAX_LOGIN_ATTEMPTS,
    SESSION_TIMEOUT_HOURS,
)
from .security import hash_password, validate_password, verify_password
from .utils import clean_text

ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_LABELS = {
    ROLE_ADMIN: "مدير النظام",
    ROLE_USER: "مستخدم",
}

_STATE_DEFAULTS = {
    "logged_in": False,
    "username": "",
    "full_name": "",
    "role": ROLE_USER,
    "login_at": None,
    "last_activity": None,
    "login_attempts": [],
}


def _init_state() -> None:
    for key, value in _STATE_DEFAULTS.items():
        st.session_state.setdefault(key, value)


def init_state() -> None:
    """تهيئة مفاتيح الجلسة الأساسية."""
    _init_state()


def current_username() -> str:
    return str(st.session_state.get("username") or "")


def current_user() -> dict[str, object]:
    _init_state()
    return {
        "username": st.session_state.get("username", ""),
        "full_name": st.session_state.get("full_name", ""),
        "role": st.session_state.get("role", ROLE_USER),
        "role_label": ROLE_LABELS.get(
            str(st.session_state.get("role", ROLE_USER)), "مستخدم"
        ),
        "is_admin": st.session_state.get("role") == ROLE_ADMIN,
    }


def is_admin() -> bool:
    return st.session_state.get("role") == ROLE_ADMIN


def _prune_login_attempts() -> list[datetime]:
    now = datetime.now()
    attempts = [
        attempt
        for attempt in st.session_state.get("login_attempts", [])
        if isinstance(attempt, datetime)
        and now - attempt < timedelta(minutes=LOGIN_WINDOW_MINUTES)
    ]
    st.session_state["login_attempts"] = attempts
    return attempts


def login(username: str, password: str) -> tuple[bool, str]:
    """يحاول تسجيل الدخول ويرجع (النجاح، الرسالة)."""
    _init_state()

    attempts = _prune_login_attempts()
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        oldest = attempts[0]
        remaining_minutes = max(
            1,
            LOGIN_WINDOW_MINUTES
            - int((datetime.now() - oldest).total_seconds() // 60),
        )
        return (
            False,
            f"تم تجاوز عدد المحاولات المسموح. حاول مرة أخرى بعد {remaining_minutes} دقيقة.",
        )

    username = clean_text(username, 80)
    password = str(password or "")

    if not username or not password:
        return False, "يرجى إدخال اسم المستخدم وكلمة المرور."

    user = db.fetch_one(
        "SELECT * FROM Users WHERE LOWER(TRIM(Username)) = LOWER(?)",
        (username,),
    )

    if (
        not user
        or not int(user.get("IsActive") or 0)
        or not verify_password(password, user.get("Password"))
    ):
        attempts.append(datetime.now())
        st.session_state["login_attempts"] = attempts
        remaining = MAX_LOGIN_ATTEMPTS - len(attempts)
        if remaining > 0:
            return (
                False,
                f"اسم المستخدم أو كلمة المرور غير صحيحة. المحاولات المتبقية: {remaining}.",
            )
        return (
            False,
            "اسم المستخدم أو كلمة المرور غير صحيحة. تم إيقاف المحاولات مؤقتاً لحماية النظام.",
        )

    st.session_state["login_attempts"] = []
    st.session_state["logged_in"] = True
    st.session_state["username"] = user["Username"]
    st.session_state["full_name"] = user.get("FullName") or user["Username"]
    st.session_state["role"] = user.get("Role") or ROLE_USER
    st.session_state["login_at"] = datetime.now()
    st.session_state["last_activity"] = datetime.now()

    db.execute(
        "UPDATE Users SET LastLoginAt=? WHERE ID=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user["ID"]),
    )
    db.log_audit(user["Username"], "دخول", "النظام", "", "تسجيل دخول ناجح")
    return True, "تم تسجيل الدخول بنجاح."


def logout() -> None:
    """ينهي الجلسة الحالية ويسجل الخروج."""
    username = current_username()
    if username:
        db.log_audit(username, "خروج", "النظام", "", "تسجيل خروج")

    for key in list(st.session_state.keys()):
        if key in _STATE_DEFAULTS:
            st.session_state.pop(key, None)
    _init_state()


def _session_expired() -> bool:
    last_activity = st.session_state.get("last_activity")
    if not isinstance(last_activity, datetime):
        return False
    return datetime.now() - last_activity > timedelta(hours=SESSION_TIMEOUT_HOURS)


def is_session_expired() -> bool:
    """هل انتهت مدة الجلسة الحالية؟"""
    return _session_expired()


def require_login() -> None:
    """يوقف الصفحة إن لم يكن المستخدم مسجلاً للدخول."""
    _init_state()

    if not st.session_state.get("logged_in"):
        st.warning("يرجى تسجيل الدخول أولاً من الصفحة الرئيسية.")
        st.stop()

    if _session_expired():
        logout()
        st.warning("انتهت مدة الجلسة لأسباب أمنية. يرجى تسجيل الدخول مرة أخرى.")
        st.stop()

    st.session_state["last_activity"] = datetime.now()


def require_admin() -> None:
    """يوقف الصفحة إن لم يكن المستخدم مديراً للنظام."""
    require_login()
    if not is_admin():
        st.error("هذه الصفحة متاحة لمدير النظام فقط.")
        st.stop()


def change_password(
    old_password: str,
    new_password: str,
    confirm_password: str,
) -> tuple[bool, str]:
    """يغير كلمة مرور المستخدم الحالي بعد التحقق من القديمة."""
    username = current_username()
    if not username:
        return False, "لا توجد جلسة نشطة."

    if new_password != confirm_password:
        return False, "كلمة المرور الجديدة وتأكيدها غير متطابقين."

    error = validate_password(new_password)
    if error:
        return False, error

    if old_password == new_password:
        return False, "كلمة المرور الجديدة يجب أن تختلف عن القديمة."

    user = db.fetch_one(
        "SELECT ID, Password FROM Users WHERE Username=?",
        (username,),
    )
    if not user or not verify_password(old_password, user.get("Password")):
        return False, "كلمة المرور الحالية غير صحيحة."

    db.execute(
        "UPDATE Users SET Password=? WHERE ID=?",
        (hash_password(new_password), user["ID"]),
    )
    db.log_audit(username, "تغيير كلمة المرور", "المستخدمون", username)
    return True, "تم تغيير كلمة المرور بنجاح."


def reset_password(username: str, new_password: str) -> tuple[bool, str]:
    """يعيد تعيين كلمة مرور مستخدم (للمدير فقط)."""
    if not is_admin():
        return False, "هذه العملية متاحة لمدير النظام فقط."

    error = validate_password(new_password)
    if error:
        return False, error

    user = db.fetch_one("SELECT ID FROM Users WHERE Username=?", (username,))
    if not user:
        return False, "المستخدم غير موجود."

    db.execute(
        "UPDATE Users SET Password=? WHERE ID=?",
        (hash_password(new_password), user["ID"]),
    )
    db.log_audit(
        current_username(),
        "إعادة تعيين كلمة المرور",
        "المستخدمون",
        username,
    )
    return True, "تم تحديث كلمة المرور بنجاح."
