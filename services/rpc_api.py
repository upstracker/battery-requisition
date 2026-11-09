"""ฟังก์ชันของ inventory_service ที่เครื่องลูกเรียกผ่านวงแลนด์ได้ (รายการอนุญาต)"""

RPC_FUNCTIONS = frozenset({
    "get_settings", "update_settings",
    "get_all_items", "get_item_by_code", "add_item", "update_item", "delete_item",
    "create_requisition", "update_requisition", "get_requisition_by_id",
    "get_requisitions_advanced", "get_today_requisitions_stats", "get_customers_list",
    "cancel_requisition", "delete_requisition", "clear_cancelled_requisitions",
    "get_db_info", "backup_database", "next_req_no",
})
