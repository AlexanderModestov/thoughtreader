from supabase import create_client, Client

from bot.config import settings

# Initialize Supabase client
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)


async def init_db():
    """Initialize database - tables should be created in Supabase dashboard."""
    # With Supabase, tables are managed via dashboard or migrations
    # This function is kept for compatibility but does nothing
    pass
