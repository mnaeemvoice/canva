from django.urls import path
from .views import (
    canva_login,
    canva_callback,
    canva_profile,
    canva_designs,
    canva_webhook,
    canva_dashboard,
    list_saved_canva_designs,
    open_canva,
    canva_monitor,
    create_canva_design,
    sync_canva_designs,
    get_design_edit_url,
    sync_design_by_url,
    smart_sync,
    force_thumbnail_export,
    direct_thumbnail_fetch,
    auto_asset_generation,
    debug_canva_api,
    update_timestamps,
    export_video_assets,
    continuous_sync_preview_false,
    fix_video_types,
    fix_design_category,
    generate_video_asset,
    debug_design_data,
    export_animated_video,
    clear_database,
    manual_canva_sync,
    simple_database_test,
    test_database_update,
)

urlpatterns = [
    path('canva/login/', canva_login),
    path('canva/callback/', canva_callback),

    path("canva/open/", open_canva),

    path('canva/profile/', canva_profile),
    path('canva/designs/', canva_designs),

    path('canva/webhook/', canva_webhook),

    path('canva/dashboard/', canva_dashboard),
    path('canva/saved-designs/', list_saved_canva_designs),

    path('canva/monitor/', canva_monitor),

    # 🔥 NEW: Create design without webhook
    path('canva/create-design/', create_canva_design),

    # 🔥 NEW: Smart Sync (All-in-One Solution)
    path('canva/smart-sync/', smart_sync),

    # 🔥 NEW: Get design edit URL
    path('canva/design/<str:design_id>/edit-url/', get_design_edit_url),

    # 🔥 NEW: Force thumbnail export for designs without assets
    path('canva/force-thumbnails/', force_thumbnail_export),

    # 🔥 NEW: Direct thumbnail fetch and save to database
    path('canva/direct-thumbnails/', direct_thumbnail_fetch),

    # 🔥 NEW: Auto asset generation and database save system
    path('canva/auto-assets/', auto_asset_generation),

    # 🔥 DEBUG: Debug Canva API structure
    path('canva/debug-api/', debug_canva_api),

    # 🔥 NEW: Update timestamps for existing designs
    path('canva/update-timestamps/', update_timestamps),

    # 🔥 NEW: Export video assets for animated designs
    path('canva/export-videos/', export_video_assets),

    # 🔥 NEW: Continuous sync for preview=false designs
    path('canva/continuous-sync/', continuous_sync_preview_false),

    # 🔥 NEW: Fix video type detection
    path('canva/fix-video-types/', fix_video_types),

    # 🔥 NEW: Manual category fix
    path('canva/fix-category/', fix_design_category),

    # 🔥 NEW: Force video asset generation
    path('canva/generate-video/', generate_video_asset),

    # 🔥 NEW: Debug design data
    path('canva/debug-design/', debug_design_data),

    # 🔥 NEW: Export animated video for external platforms
    path('canva/export-animated/', export_animated_video),

    # 🔥 NEW: Clear database for testing
    path('canva/clear-database/', clear_database),

    # 🔥 NEW: Manual Canva sync
    path('canva/manual-sync/', manual_canva_sync),

    # 🔥 NEW: Simple database test
    path('canva/simple-test/', simple_database_test),

    # 🔥 NEW: Test database update
    path('canva/test-database-update/', test_database_update),

    # 🔥 LEGACY: Old sync endpoints (kept for compatibility)
    path('canva/sync-designs/', sync_canva_designs),
    path('canva/sync-by-url/', sync_design_by_url),
]