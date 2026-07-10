from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must not be blank")
        if not self.actor_id.strip():
            raise ValueError("actor_id must not be blank")


def require_tenant_context(ctx: TenantContext) -> TenantContext:
    if not isinstance(ctx, TenantContext):
        raise TypeError("an explicit TenantContext is required")
    return ctx
