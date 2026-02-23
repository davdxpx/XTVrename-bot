import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client

async def generate_session():
    # Load environment variables if present
    load_dotenv()

    print("\n=== XTV Session Generator ===")
    print("This script will help you generate a Pyrogram Session String for your Premium account.")
    print("This string is required to enable 4GB upload support.\n")

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")

    if not api_id:
        try:
            api_id = int(input("Enter your API ID: "))
        except ValueError:
            print("Invalid API ID. Please enter a number.")
            return

    if not api_hash:
        api_hash = input("Enter your API HASH: ")

    if not api_id or not api_hash:
        print("API ID and API HASH are required.")
        return

    print(f"\nUsing API ID: {api_id}")
    print("Initiating login... (Check your Telegram app for the code)\n")

    async with Client(":memory:", api_id=api_id, api_hash=api_hash) as app:
        session_string = await app.export_session_string()

        print("\n✅ Session String Generated Successfully!\n")
        print("COPY THE FOLLOWING LINE AND ADD IT TO YOUR .env FILE:\n")
        print(f"USER_SESSION={session_string}\n")
        print("Make sure there are no spaces around the '=' sign.")
        print("====================================================\n")

if __name__ == "__main__":
    try:
        asyncio.run(generate_session())
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
