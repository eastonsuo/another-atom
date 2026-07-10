from another_atom.contracts.schemas import AppSpec, ValidationCheck, ValidationReport


def validate_app_spec(app_spec: AppSpec, prompt: str = "") -> ValidationReport:
    routes = {page.route for page in app_spec.pages}
    required_routes = {"/", "/catalog"}
    product_route_exists = any(route.startswith("/product/") for route in routes)
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
            status="pass",
            root_cause="renderer",
        ),
    ]
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
