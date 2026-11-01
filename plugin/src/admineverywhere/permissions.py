"""Server-side role gates (FR-R007 phase b) — the mirror of client rbac.ts.

docs/rbac.md is explicit that the client's filtering is presentation
only: "the server stays the actual gate." RequireGroups makes that
sentence true for any surface a host marks with it.

The allow rule mirrors roleAllows() exactly:

- superuser -> allow (the client's isSuperuser short-circuit);
- otherwise the caller must hold AT LEAST ONE of the required group
  names (the client's ``required.some(r => claims.roles.includes(r))``);
- unauthenticated -> deny here too, but DRF answers 401 before this
  class runs when IsAuthenticated composes first, so anonymous callers
  keep the 401 contract and authenticated callers without the claim get
  DRF's 403 detail body.

is_staff is deliberately NOT a bypass: /api/me/ reports Group names and
the client opens gated surfaces on the roles claim only — a staff flag
without the group claim stays locked out on both sides, so the server
and the UI can never disagree about who sees an action.

DRF instantiates permission classes without arguments, so configuration
happens at class-creation time: use ``require_groups("managers")`` in
``permission_classes=[...]``, or subclass and set ``required_groups``.
"""
from rest_framework.permissions import BasePermission


class RequireGroups(BasePermission):
    """Allow only callers holding at least one of ``required_groups``."""

    message = "You do not hold a role required for this action."

    required_groups: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user is not None and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        groups = getattr(user, "groups", None)
        if groups is None:
            return False
        return groups.filter(name__in=self.required_groups).exists()


def require_groups(*names: str) -> type[RequireGroups]:
    """A RequireGroups bound to the given group names.

    Returns a fresh class (not an instance) because DRF's
    ``get_permissions()`` instantiates every entry of
    ``permission_classes`` with no arguments.
    """
    if not names:
        raise ValueError("require_groups() needs at least one group name")
    return type("RequireGroups", (RequireGroups,), {"required_groups": names})
