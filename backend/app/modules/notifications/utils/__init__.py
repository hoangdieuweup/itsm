"""Non business helpers for the notifications module, grouped by concern.

Add utils/<concern>.py the same way when the module needs another kind of
helper — one file, one class, per concern (see references/layer-examples.md).
"""

from app.modules.notifications.utils.loader import NotificationTemplates

__all__ = ["NotificationTemplates"]
