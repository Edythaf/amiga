"""ZIP primary controller, adapted to the existing portal API and revocable access.

The native HTML/session/SQL controller is rebased onto the shared integration
schema so there is one login, one policy, one set of immutable invoice versions.
"""
from ...api_common import (
    ALL_ROLES, AuthSession, CLIENT_ROLES, Client, Membership, Role,
    User, WorkRequest, api, audit, body, client_ids,
    delete, fail, func, g, now, ok,
    require_role, roles, select, task_complete, uid, user_dto
)


@api.get('/admin/users')
def users():
    require_role('SYSTEM_ADMIN')
    return ok({'items': [user_dto(u) for u in g.db.scalars(select(User).order_by(User.email))]})



@api.patch('/admin/users/<user_id>')
def update_user(user_id):
    require_role('SYSTEM_ADMIN')
    data = body()
    if not data or set(data) - {'roles', 'account_status', 'client_ids'}:
        fail(422, 'INVALID_USER_UPDATE', 'Isi roles, account_status, atau client_ids.')
    if user_id == g.actor.id:
        fail(403, 'SELF_CHANGE_FORBIDDEN', 'Perubahan akses diri sendiri harus dilakukan administrator lain atau provisioning lokal.')
    user = g.db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        fail(404, 'NOT_FOUND', 'Akun tidak ditemukan.')
    before = user_dto(user)
    assigned_roles = data.get('roles', before['roles'])
    assigned_clients = data.get('client_ids', [c['id'] for c in before['clients']])
    status = data.get('account_status', user.account_status)
    if (not isinstance(assigned_roles, list) or any(not isinstance(r, str) or r not in ALL_ROLES for r in assigned_roles)
            or len(assigned_roles) != len(set(assigned_roles))):
        fail(422, 'INVALID_ROLES', 'Role tidak valid.')
    if not isinstance(assigned_clients, list) or any(not isinstance(c, str) or not g.db.get(Client, c) for c in assigned_clients):
        fail(422, 'INVALID_CLIENTS', 'Klien tidak valid.')
    if status not in ('ACTIVE', 'DISABLED', 'PENDING_CLIENT', 'PENDING_ADMIN', 'PENDING_REVIEWER', 'PENDING_COMPANY'):
        fail(422, 'INVALID_STATUS', 'Status akun tidak valid.')
    if 'COMPANY_CLIENT' in assigned_roles and set(assigned_roles)!={'COMPANY_CLIENT'}:
        fail(422,'ROLE_CONFLICT','Akun Klien perusahaan harus terpisah dari uploader, reviewer dan admin.')
    if status == 'ACTIVE' and (not assigned_roles or (set(assigned_roles) & (CLIENT_ROLES|{'COMPANY_CLIENT'}) and not assigned_clients)):
        fail(422, 'ASSIGNMENT_REQUIRED', 'Pilih peran. Assignment klien hanya wajib untuk peran klien/backup; reviewer mengambil tugas dari papan bersama.')
    if 'SYSTEM_ADMIN' in assigned_roles and 'FINANCE_REVIEWER' in assigned_roles:
        fail(422, 'ROLE_CONFLICT', 'System Admin dan Finance Reviewer tidak boleh digabung.')
    if 'SYSTEM_ADMIN' in before['roles'] and ('SYSTEM_ADMIN' not in assigned_roles or status != 'ACTIVE'):
        count = g.db.scalar(select(func.count()).select_from(User).join(Role).where(
            Role.role == 'SYSTEM_ADMIN', User.account_status == 'ACTIVE'))
        if count <= 1:
            fail(409, 'LAST_ADMIN', 'Administrator aktif terakhir tidak dapat dinonaktifkan.')
    g.db.execute(delete(Role).where(Role.user_id == user.id))
    g.db.execute(delete(Membership).where(Membership.user_id == user.id))
    for role in assigned_roles:
        g.db.add(Role(user_id=user.id, role=role))
    for client_id in set(assigned_clients):
        g.db.add(Membership(user_id=user.id, client_id=client_id))
    user.account_status = status
    if status != 'ACTIVE' or 'FINANCE_REVIEWER' not in assigned_roles:
        for req in g.db.scalars(select(WorkRequest).where(WorkRequest.pic_id == user.id).with_for_update()):
            if not task_complete(req):
                req.pic_id, req.updated_at = None, now()
                audit(g.db, 'TASK_RELEASED_BY_ADMIN', g.actor.id, req.id, reason='Akses reviewer dihentikan',
                      changes=[{'field': 'pic_id', 'before': user.id, 'after': None}])
    g.db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    g.db.flush()
    after = user_dto(user)
    audit(g.db, 'USER_ACCESS_UPDATED', g.actor.id, reason='Akses akun diperbarui',
          changes=[{'field': 'user:' + user.id, 'before': before, 'after': after}])
    return ok(after)


@api.patch('/admin/clients/<client_id>')
def rename_client(client_id):
    require_role('SYSTEM_ADMIN')
    data=body();company=g.db.scalar(select(Client).where(Client.id==client_id).with_for_update())
    if not company:fail(404,'NOT_FOUND','Perusahaan tidak ditemukan.')
    name=data.get('name')
    if not isinstance(name,str) or not 2<=len(name.strip())<=200:fail(422,'INVALID_NAME','Nama perusahaan harus 2–200 karakter.')
    if data.get('expected_name')!=company.name:fail(409,'CLIENT_CHANGED','Nama perusahaan berubah. Muat ulang sebelum menyimpan.')
    before=company.name;company.name=name.strip()
    if before!=company.name:audit(g.db,'COMPANY_RENAMED',g.actor.id,changes=[{'field':'client:'+company.id,'before':before,'after':company.name}])
    return ok({'id':company.id,'name':company.name})



@api.get('/admin/clients')
def clients():
    actor_roles = roles(g.db, g.actor)
    if not actor_roles & {'SYSTEM_ADMIN', 'SERVICE_LEAD', 'FINANCE_REVIEWER'}:
        fail(403, 'FORBIDDEN', 'Akses internal diperlukan.')
    query = select(Client)
    if 'SYSTEM_ADMIN' not in actor_roles:
        query = query.where(Client.id.in_(client_ids(g.db, g.actor)))
    return ok({'items': [{'id': c.id, 'name': c.name} for c in g.db.scalars(query.order_by(Client.name))]})



@api.post('/admin/clients')
def create_client():
    require_role('SYSTEM_ADMIN')
    name = body().get('name')
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 200:
        fail(422, 'INVALID_NAME', 'Nama klien harus 2–200 karakter.')
    client = Client(id=uid('cli'), name=name.strip())
    g.db.add(client)
    audit(g.db, 'CLIENT_CREATED', g.actor.id, changes=[{'field': 'client', 'before': None, 'after': {'id': client.id, 'name': client.name}}])
    return ok({'id': client.id, 'name': client.name}, 201)

