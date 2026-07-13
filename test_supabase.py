from pharmagpt.services.supabase_client import supabase

try:
    response = (
        supabase
        .table("connection_test")
        .select("*")
        .execute()
    )

    print("✅ Connected Successfully")
    print(response.data)

except Exception as e:
    print("❌ Connection Failed")
    print(e)