# orgs/logic/guards.py
from orgs.models import Membership

class GuardError(Exception):
    pass

_ORDER = {Membership.MEMBER: 1, Membership.ADMIN: 2, Membership.OWNER: 3}

def ensure_owner(actor: Membership) -> None:
    if not actor or actor.role != Membership.OWNER:
        # match test substring "Only owners"
        raise GuardError("Only owners can perform this action.")

def _is_last_active_owner(qs, member: Membership) -> bool:
    return (
        member.role == Membership.OWNER
        and member.is_active
        and qs.filter(org=member.org, role=Membership.OWNER, is_active=True).count() == 1
    )

def guard_toggle_active(qs, actor: Membership, target: Membership, new_active: bool) -> None:
    ensure_owner(actor)
    self_action = actor.user_id == target.user_id

    # ✅ Self takes precedence over last-owner (matches tests)
    if self_action and not new_active:
        raise GuardError("You can’t deactivate your own account in this organisation.")

    if not new_active and _is_last_active_owner(qs, target):
        raise GuardError("You can’t deactivate the last Owner in this organisation.")
    # reactivations OK

def guard_role_change(qs, actor: Membership, target: Membership, new_role: str) -> None:
    new_role = (new_role or "").lower()
    valid = {v for v, _ in Membership.ROLES}
    if new_role not in valid:
        raise GuardError("Invalid role.")

    ensure_owner(actor)
    self_action = actor.user_id == target.user_id
    lowering = _ORDER.get(new_role, 0) < _ORDER.get(target.role, 0)

    # ✅ Self takes precedence over last-owner (matches tests)
    if self_action and lowering:
        raise GuardError("You can’t lower your own role.")

    if lowering and target.role == Membership.OWNER and _is_last_active_owner(qs, target):
        raise GuardError("You can’t remove/demote the last Owner in this organisation.")
    # upgrades/no-op OK
