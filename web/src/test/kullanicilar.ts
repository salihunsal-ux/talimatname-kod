import type { Ben } from '../api/oturum';

/** Test kullanıcıları. Adlar uydurma; gerçek kişi verisi yok (ADR-0003). */
export const YONETICI: Ben = {
  id: '00000000-0000-0000-0000-0000000000a1',
  full_name: 'Test Yönetici',
  phone: null,
  roles: [{ role: 'admin', role_label: 'Yönetici', scope_type: 'organization', scope_id: null }],
};

export const SUBE_MUDURU: Ben = {
  id: '00000000-0000-0000-0000-0000000000b1',
  full_name: 'Test Şube Müdürü',
  phone: null,
  roles: [
    {
      role: 'branch_manager',
      role_label: 'Şube müdürü',
      scope_type: 'branch',
      scope_id: '00000000-0000-0000-0000-0000000000c1',
    },
  ],
};

export const BOLGE_MUDURU: Ben = {
  id: '00000000-0000-0000-0000-0000000000d1',
  full_name: 'Test Bölge Müdürü',
  phone: null,
  roles: [
    {
      role: 'region_manager',
      role_label: 'Bölge müdürü',
      scope_type: 'region',
      scope_id: '00000000-0000-0000-0000-0000000000e1',
    },
  ],
};
