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
    upload_design_to_server,
    serve_local_asset,
    re_export_existing_designs,
    simple_database_test,
    test_database_update,
    auto_sync_designs,
    serve_binary_file,
    debug_binary_download,
    test_canva_api,
    play_in_vlc,
    upload_to_live_server,
    export_video_for_sharing,
    download_actual_video_file,
    check_canva_auth,
    list_designs_from_db,
    get_design_details,
    convert_to_private_designs,
    export_private_design,
    upload_private_design,
    social_auth_status,
    social_auth_save,
    social_auth_disconnect,
    unified_post_content,
    list_posted_content,
    get_posted_content,
    export_video_alternative,
    get_video_download_info,
    download_and_upload_video,
    upload_video_to_platform,
    share_video_direct,
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

    # 🔥 NEW: Comprehensive Auto-Sync for real-time database updates
    path('canva/auto-sync-designs/', auto_sync_designs),

    # 🔥 NEW: Universal design upload
    path('canva/upload/', upload_design_to_server),

    # 🔥 NEW: Serve local assets
    path('canva/local-asset/<str:design_id>/', serve_local_asset),

    # 🔥 NEW: Serve binary files from database
    path('canva/binary-file/<str:design_id>/', serve_binary_file),

    # 🔥 NEW: Debug binary file download
    path('canva/debug-binary-download/', debug_binary_download),

    # 🔥 NEW: Test Canva API response
    path('canva/test-api/', test_canva_api),

    # 🔥 NEW: Play in VLC media player
    path('canva/play-in-vlc/', play_in_vlc),

    # 🔥 NEW: Upload to live server
    path('canva/upload-live/', upload_to_live_server),

    # 🔥 NEW: Export video for sharing
    path('canva/export-video/', export_video_for_sharing),

    # 🔥 NEW: Fixed video export with proper Canva API flow
    path('canva/export-video-fixed/', export_video_for_sharing),

    # 🔥 NEW: Alternative video export (bypass rate limiting)
    path('canva/export-video-alternative/', export_video_alternative),
    path('canva/video-download-info/<str:design_id>/', get_video_download_info),

    # 🔥 NEW: Download and upload video to user's site
    path('canva/download-upload-video/', download_and_upload_video),

    # 🔥 NEW: Upload video to external platforms
    path('canva/upload-video-platform/', upload_video_to_platform),
    path('canva/share-video/', share_video_direct),

    # 🔥 NEW: Download actual video file
    path('canva/download-actual-video/', download_actual_video_file),

    # 🔥 NEW: Check Canva authentication status
    path('canva/check-auth/', check_canva_auth),

    # 🔥 NEW: List designs from database
    path('canva/designs-db/', list_designs_from_db),

    # 🔥 NEW: Get design details from database
    path('canva/designs-db/<str:design_id>/', get_design_details),

    # 🔥 NEW: Private Design System
    path('canva/convert-to-private/', convert_to_private_designs),
    path('canva/export-private/', export_private_design),
    path('canva/upload-private/', upload_private_design),

    # 🔥 NEW: Social Media OAuth Authentication
    path('social/auth-status/', social_auth_status),
    path('social/auth-save/', social_auth_save),
    path('social/auth-disconnect/', social_auth_disconnect),

    # 🔥 NEW: Unified Posting System
    path('social/unified-post/', unified_post_content),
    path('social/posted-content/', list_posted_content),
    path('social/posted-content/<int:content_id>/', get_posted_content),

    # 🔥 NEW: Re-export existing designs
    path('canva/re-export/', re_export_existing_designs),

    # 🔥 NEW: Simple database test
    path('canva/simple-test/', simple_database_test),

    # 🔥 NEW: Test database update
    path('canva/test-database-update/', test_database_update),

    # 🔥 LEGACY: Old sync endpoints (kept for compatibility)
    path('canva/sync-designs/', sync_canva_designs),
    path('canva/sync-by-url/', sync_design_by_url),
]