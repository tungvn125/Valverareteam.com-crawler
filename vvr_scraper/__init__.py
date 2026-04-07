import sys

# Python 3.13 removal of audioop fix
if sys.version_info >= (3, 13):
    try:
        import audioop
    except ImportError:
        try:
            import audioop_lts
            sys.modules["audioop"] = audioop_lts
        except ImportError:
            # audioop-lts not installed, will fail when needed
            pass
