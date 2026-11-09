"""
ตัวกลางที่หน้าจอใช้เรียก inventory_service
- เครื่องเดียว (standalone): เรียกฐานข้อมูลในเครื่องโดยตรง
- เครื่องหลัก/เครื่องลูก: เรียกผ่านเซิร์ฟเวอร์ของเครื่องหลัก
"""
from services import inventory_service
from services.remote import RemoteClient
from services.rpc_api import RPC_FUNCTIONS


class _ServiceFacade:
    _remote = None
    mode = "standalone"

    def configure(self, cfg):
        self.mode = cfg.get("mode", "standalone")
        if self.mode == "standalone":
            self._remote = None
        else:
            host = "127.0.0.1" if self.mode == "server" else cfg.get("host", "127.0.0.1")
            self._remote = RemoteClient(host, cfg.get("port", 8765), cfg.get("token", ""))

    @property
    def remote(self):
        return self._remote

    @property
    def is_remote(self):
        return self._remote is not None

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        remote = self._remote
        if remote is not None and name in RPC_FUNCTIONS:
            return lambda *args, **kwargs: remote.call(name, *args, **kwargs)
        return getattr(inventory_service, name)


inv_service = _ServiceFacade()
