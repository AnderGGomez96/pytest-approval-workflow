import os
import requests
DEFAULT_TIMEOUT = 10.0

class ApiClient:
    def __init__(
            self,
            base_url:str | None = None,
            token: str | None = None,
            timeout: float= DEFAULT_TIMEOUT,
            ) -> None:
        self. base_url = (
            base_url or os.environ.get("APPROVAL_BASE_URL")
        ).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"]= f"Bearer {token}"

    def _request(self, method:str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self._session.request(method, f"{self.base_url}{path}",**kwargs)

    def get(self, path:str, **kwargs) -> requests.Response:
        return self._request("GET",path,**kwargs)

    def post(self, path:str, **kwargs) -> requests.Response:
        return self._request("POST",path, **kwargs)

    def put(self, path:str, **kwargs) -> requests.Response:
        return self._request("PUT", path, **kwargs)

    def close(self) -> None:
        self._session.close()