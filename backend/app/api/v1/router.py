from fastapi import APIRouter

from app.api.v1.endpoints import auth, config, inventory, kitchen_tables, menu, money, orders, platform, reports_ws, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(auth.approvals)
api_router.include_router(users.router)
api_router.include_router(users.roles_router)
api_router.include_router(menu.router)
api_router.include_router(orders.router)
api_router.include_router(kitchen_tables.kitchen)
api_router.include_router(kitchen_tables.tables)
api_router.include_router(platform.notifications)
api_router.include_router(platform.audit_router)
api_router.include_router(money.bills)
api_router.include_router(money.cash)
api_router.include_router(inventory.router)
api_router.include_router(config.router)
api_router.include_router(reports_ws.router)
api_router.include_router(reports_ws.ws_router)
