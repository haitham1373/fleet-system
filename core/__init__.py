"""النواة المشتركة لنظام إدارة الأسطول.

يحتوي هذا المجلد على الإعدادات، قاعدة البيانات، الأمان، المصادقة،
ومكونات الواجهة المشتركة بين جميع صفحات النظام.
"""

__all__ = ["auth", "config", "db", "security", "services", "ui", "utils"]

# لازم يتحمل قبل core.config عشان يضبط FLEET_DB_PATH على نسخة الحالة الدائمة.
from .cloud_sync import prepare_state as _prepare_cloud_state

_prepare_cloud_state()
