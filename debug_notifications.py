
import uuid
from ingestion_service.database import SessionLocal
from ingestion_service.models import Notification, Tenant, User

def debug_data():
    db = SessionLocal()
    try:
        print("--- TENANTS ---")
        tenants = db.query(Tenant).all()
        for t in tenants:
            print(f"ID: {t.id} | Name: {t.name} | Email: {t.email}")
        
        print("\n--- USERS ---")
        users = db.query(User).all()
        for u in users:
            print(f"ID: {u.id} | Email: {u.email} | TenantID: {u.tenant_id}")

        print("\n--- NOTIFICATIONS ---")
        notifications = db.query(Notification).all()
        if not notifications:
            print("No notifications found in the database.")
        for n in notifications:
            print(f"ID: {n.id} | TenantID: {n.tenant_id} | Category: {n.category} | Title: {n.title} | IsRead: {n.is_read}")
            
    finally:
        db.close()

if __name__ == "__main__":
    debug_data()
