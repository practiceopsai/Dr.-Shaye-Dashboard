from app.config import Settings


def test_allowed_origins_parses_local_and_production_urls():
    settings = Settings(
        allowed_origins="http://localhost:3000, https://eli-commandcenter.up.railway.app"
    )

    assert settings.origins == [
        "http://localhost:3000",
        "https://eli-commandcenter.up.railway.app",
    ]
