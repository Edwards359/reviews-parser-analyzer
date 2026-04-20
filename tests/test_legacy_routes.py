"""Проверка совместимости: legacy-эндпоинты /api/reviews[/{id}]
продолжают быть зарегистрированы рядом с /api/v1/*, и
correlation-id middleware подключён.
"""

from __future__ import annotations


def _collect_routes() -> dict[str, set[str]]:
    from app.api.routes import router

    paths: dict[str, set[str]] = {}
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not path:
            continue
        paths.setdefault(path, set()).update(methods)
    return paths


def test_legacy_endpoints_registered():
    paths = _collect_routes()

    assert "GET" in paths.get("/api/reviews", set())
    assert "POST" in paths.get("/api/reviews", set())
    assert "PATCH" in paths.get("/api/reviews/{review_id}", set())


def test_v1_endpoints_registered():
    paths = _collect_routes()

    assert "GET" in paths.get("/api/v1/reviews", set())
    assert "POST" in paths.get("/api/v1/reviews", set())
    assert "POST" in paths.get("/api/v1/reviews/claim", set())
    assert "POST" in paths.get("/api/v1/reviews/ai-reply", set())
    assert "PATCH" in paths.get("/api/v1/reviews/{review_id}", set())
    assert "GET" in paths.get("/api/v1/reviews.csv", set())


def test_healthz_and_readyz_registered():
    paths = _collect_routes()

    assert "GET" in paths.get("/healthz", set())
    assert "GET" in paths.get("/readyz", set())


def test_correlation_middleware_is_installed():
    import importlib

    main = importlib.import_module("app.main")
    middleware_types = [m.cls.__name__ for m in main.app.user_middleware]
    assert "CorrelationIdMiddleware" in middleware_types
