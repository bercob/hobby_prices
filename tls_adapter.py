import ssl

from requests.adapters import HTTPAdapter


class TLSAdapter(HTTPAdapter):
    def __init__(self, tls_version=None, **kwargs):
        self.tls_version = tls_version
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.SSLContext(self.tls_version)
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)
