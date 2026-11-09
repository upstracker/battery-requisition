#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # เครื่องหลัก: `--server` เปิดเซิร์ฟเวอร์เบื้องหลัง ไม่มีหน้าต่าง
    if "--server" in sys.argv:
        from services.server import run_forever
        sys.exit(run_forever())

    from ui.app import BatteryRequisitionApp
    app = BatteryRequisitionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
