#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import BatteryRequisitionApp

def main():
    app = BatteryRequisitionApp()
    app.mainloop()

if __name__ == "__main__":
    main()
