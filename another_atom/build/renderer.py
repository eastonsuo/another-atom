from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    Blueprint,
    ValidationCheck,
    ValidationReport,
)


def normalize_architecture_visual_tokens(
    architecture_spec: ArchitectureSpec,
) -> ArchitectureSpec:
    """Keep the model's palette where possible while enforcing renderer contrast."""
    background = architecture_spec.background_color.upper()
    primary = _ensure_contrast(architecture_spec.primary_color, background, 4.5)
    accent = _ensure_contrast(architecture_spec.accent_color, background, 3.0)
    if accent.casefold() == primary.casefold():
        accent = _distinct_contrast_color(background, 3.0, {primary.casefold()})
    return architecture_spec.model_copy(
        update={
            "primary_color": primary,
            "accent_color": accent,
            "background_color": background,
        }
    )


def validate_app_spec(
    app_spec: AppSpec,
    prompt: str = "",
    *,
    blueprint: Blueprint | None = None,
    architecture_spec: ArchitectureSpec | None = None,
) -> ValidationReport:
    routes = {page.route for page in app_spec.pages}
    required_routes = {"/", "/catalog"}
    product_route_exists = any(route.startswith("/product/") for route in routes)
    visual_tokens_valid, visual_detail = _validate_visual_tokens(app_spec, architecture_spec)
    checks = [
        ValidationCheck(
            check_id="required-routes",
            label="Home, Catalog, and Product routes are available",
            status=(
                "pass" if required_routes.issubset(routes) and product_route_exists else "fail"
            ),
            root_cause="app_spec",
            resolvable=True,
            detail=None,
        ),
        ValidationCheck(
            check_id="product-data",
            label="At least three products contain usable content",
            status="pass" if len(app_spec.products) >= 3 else "fail",
            root_cause="app_spec",
            resolvable=True,
        ),
        ValidationCheck(
            check_id="visual-tokens",
            label="Renderer visual tokens are valid",
            status="pass" if visual_tokens_valid else "fail",
            root_cause="renderer",
            resolvable=True,
            detail=visual_detail,
        ),
    ]
    if blueprint is not None:
        page_checks = {
            "Home": "/" in routes,
            "Catalog": "/catalog" in routes,
            "Product": product_route_exists,
        }
        missing_pages = [page for page in blueprint.pages if not page_checks.get(page, False)]
        checks.append(
            ValidationCheck(
                check_id="blueprint-pages",
                label="Every Blueprint page is represented by an AppSpec route",
                status="fail" if missing_pages else "pass",
                root_cause="app_spec",
                resolvable=True,
                detail=(
                    f"Missing Blueprint pages: {', '.join(missing_pages)}"
                    if missing_pages
                    else None
                ),
            )
        )
        unsupported_mappings = [
            requirement
            for requirement in blueprint.mapped_requirements
            if not _mapped_requirement_is_satisfied(
                requirement,
                routes=routes,
                product_count=len(app_spec.products),
                visual_tokens_valid=visual_tokens_valid,
            )
        ]
        checks.append(
            ValidationCheck(
                check_id="mapped-requirements",
                label="Mapped Blueprint requirements have deterministic evidence",
                status="fail" if unsupported_mappings else "pass",
                root_cause="app_spec",
                resolvable=True,
                detail=(
                    "No deterministic evidence for: " + "; ".join(unsupported_mappings)
                    if unsupported_mappings
                    else None
                ),
            )
        )
    if "[fail:build]" in prompt.lower():
        checks.append(
            ValidationCheck(
                check_id="mock-build-failure",
                label="Controlled build acceptance hook",
                status="fail",
                root_cause="renderer",
                resolvable=True,
                detail="Mock build failure requested by the test prompt",
            )
        )
    return ValidationReport(passed=all(check.status == "pass" for check in checks), checks=checks)


def _mapped_requirement_is_satisfied(
    requirement: str,
    *,
    routes: set[str],
    product_count: int,
    visual_tokens_valid: bool,
) -> bool:
    normalized = requirement.casefold()
    evidence: list[bool] = []
    if any(term in normalized for term in ("catalog", "商品", "product catalog")):
        evidence.append("/catalog" in routes and product_count >= 3)
    if any(term in normalized for term in ("detail", "navigation", "详情", "导航")):
        evidence.append(any(route.startswith("/product/") for route in routes))
    if any(term in normalized for term in ("visual", "color", "视觉", "颜色", "editable")):
        evidence.append(visual_tokens_valid)
    if any(term in normalized for term in ("responsive", "mobile", "desktop", "响应式")):
        evidence.append("/" in routes and "/catalog" in routes)
    return bool(evidence) and all(evidence)


def _validate_visual_tokens(
    app_spec: AppSpec,
    architecture_spec: ArchitectureSpec | None,
) -> tuple[bool, str | None]:
    colors = (app_spec.primary_color, app_spec.accent_color, app_spec.background_color)
    if len(set(color.casefold() for color in colors)) != len(colors):
        return False, "Primary, accent, and background colors must be distinct"
    if _contrast_ratio(app_spec.primary_color, app_spec.background_color) < 4.5:
        return False, "Primary/background contrast is below 4.5:1"
    if _contrast_ratio(app_spec.accent_color, app_spec.background_color) < 3.0:
        return False, "Accent/background contrast is below 3:1"
    if architecture_spec is not None and tuple(color.casefold() for color in colors) != tuple(
        color.casefold()
        for color in (
            architecture_spec.primary_color,
            architecture_spec.accent_color,
            architecture_spec.background_color,
        )
    ):
        return False, "AppSpec colors do not match the approved ArchitectureSpec tokens"
    return True, None


def _ensure_contrast(color: str, background: str, minimum: float) -> str:
    color = color.upper()
    if _contrast_ratio(color, background) >= minimum:
        return color
    channels = [int(color[index : index + 2], 16) for index in (1, 3, 5)]
    lighten = _relative_luminance(background) < 0.179
    for step in range(1, 21):
        amount = step / 20
        adjusted = [
            round(channel + (255 - channel) * amount) if lighten else round(channel * (1 - amount))
            for channel in channels
        ]
        candidate = "#" + "".join(f"{channel:02X}" for channel in adjusted)
        if _contrast_ratio(candidate, background) >= minimum:
            return candidate
    return "#FFFFFF" if lighten else "#000000"


def _distinct_contrast_color(
    background: str, minimum: float, excluded: set[str]
) -> str:
    for candidate in ("#000000", "#FFFFFF", "#003366", "#5A2400", "#FFD166"):
        if candidate.casefold() not in excluded and _contrast_ratio(candidate, background) >= minimum:
            return candidate
    return "#000000"


def _contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
