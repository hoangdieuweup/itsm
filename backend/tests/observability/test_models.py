import uuid

from app.modules.observability.constants import LokiAuthType
from app.modules.observability.models import LokiConfig


def test_loki_config_model_columns():
    config = LokiConfig(
        id=uuid.uuid4(),
        environment_id=uuid.uuid4(),
        endpoint_url="http://loki:3100",
        tenant_id="tenant-a",
        auth_type=LokiAuthType.BEARER,
        credential="ciphertext",
        default_query='{job="api"}',
        default_range_minutes=60,
    )
    assert config.auth_type == LokiAuthType.BEARER
    assert config.default_range_minutes == 60
