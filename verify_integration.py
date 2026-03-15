"""
System Integration Verification Script
Checks if all services are properly connected and ready
"""
import sys
import os

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def check_status(service_name, test_func):
    """Helper to check and print service status"""
    try:
        test_func()
        print(f"{GREEN}✓{RESET} {service_name}: Connected")
        return True
    except Exception as e:
        print(f"{RED}✗{RESET} {service_name}: Failed - {str(e)}")
        return False

print("=" * 60)
print("System Integration Verification")
print("=" * 60)
print()

results = {}

# 1. Check PostgreSQL
def test_postgres():
    import psycopg2
    conn = psycopg2.connect(
        "postgresql://postgres:123456789@localhost:5432/postgres"
    )
    conn.close()

results['PostgreSQL'] = check_status('PostgreSQL Database', test_postgres)

# 2. Check RabbitMQ
def test_rabbitmq():
    import pika
    credentials = pika.PlainCredentials('admin', 'secretpassword')
    parameters = pika.ConnectionParameters('localhost', credentials=credentials)
    connection = pika.BlockingConnection(parameters)
    connection.close()

results['RabbitMQ'] = check_status('RabbitMQ Message Queue', test_rabbitmq)

# 3. Check MinIO
def test_minio():
    from minio import Minio
    client = Minio(
        'localhost:9000',
        access_key='admin',
        secret_key='password123',
        secure=False
    )
    # Just check if we can connect
    client.bucket_exists('pdf-storage')

results['MinIO'] = check_status('MinIO Storage', test_minio)

# 4. Check API (if running)
def test_api():
    import requests
    response = requests.get('http://localhost:8000/docs', timeout=2)
    if response.status_code != 200:
        raise Exception("API not responding")

api_running = check_status('FastAPI Server', test_api)
if not api_running:
    print(f"{YELLOW}  Note: Start API with 'python app/start_api.py'{RESET}")
results['API'] = api_running

print()
print("=" * 60)
print("Summary")
print("=" * 60)

total = len(results)
passed = sum(results.values())

print(f"Services Checked: {total}")
print(f"Connected: {passed}")
print(f"Failed: {total - passed}")
print()

if passed == total:
    print(f"{GREEN}✓ All systems ready! You can start testing.{RESET}")
    print()
    print("Next steps:")
    print("1. Start API: python app/start_api.py")
    print("2. Start Consumer: python rabbitmq_server/start_consumer.py")
    print("3. Upload document via http://localhost:8000/docs")
else:
    print(f"{RED}✗ Some services are not ready.{RESET}")
    print()
    print("Start failed services:")
    if not results.get('PostgreSQL'):
        print("  - cd postgres_server && docker-compose up -d")
    if not results.get('RabbitMQ'):
        print("  - cd rabbitmq_server && docker-compose up -d")
    if not results.get('MinIO'):
        print("  - cd minio_server && docker-compose up -d")

print("=" * 60)
