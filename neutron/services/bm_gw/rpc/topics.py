BM_GW_RESOURCE = 'bm_gw'

def resource_type_versioned_topic(resource, host=None):
    """
    构造带版本号和可选host的topic，用于bm_gw自定义RPC点对点通信。
    :param resource: 资源类型字符串，如 'bm_gw' 或 'port'
    :param host: 可选，指定主机名，实现点对点topic
    :return: topic字符串
    """
    topic = f"{resource}.v1"
    if host:
        topic = f"{topic}.{host}"
    return topic
