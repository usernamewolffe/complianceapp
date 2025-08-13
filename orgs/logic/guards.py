from orgs.models import Membership

class GuardError(Exception):
    status_code = 400

class Forbidden(GuardError):
    status_code = 403

def ensure_owner(actor_member: Membership):
    if actor_member.role != Membership.OWNER:
        raise Forbidden("Only owners can perform this action.")

def prevent_self_change(actor_member: Membership, target_member: Membership):
    if actor_member.id == target_member.id:
        raise GuardError("You can’t change or deactivate yourself.")

def is_last_active_owner(qs, org_id, exclude_member_id=None):
    q = qs.filter(org_id=org_id, role=Membership.OWNER, is_active=True)
    if exclude_member_id:
        q = q.exclude(id=exclude_member_id)
    return not q.exists()

def guard_role_change(qs, actor_member: Membership, target_member: Membership, new_role: str):
    ensure_owner(actor_member)
    prevent_self_change(actor_member, target_member)
    if target_member.role == Membership.OWNER and new_role != Membership.OWNER:
        if is_last_active_owner(qs, target_member.org_id, exclude_member_id=target_member.id):
            raise GuardError("You can’t remove the last active Owner from an organisation.")

def guard_toggle_active(qs, actor_member: Membership, target_member: Membership, new_active: bool):
    ensure_owner(actor_member)
    prevent_self_change(actor_member, target_member)
    if target_member.role == Membership.OWNER and new_active is False:
        if is_last_active_owner(qs, target_member.org_id, exclude_member_id=target_member.id):
            raise GuardError("You can’t deactivate the last active Owner.")
