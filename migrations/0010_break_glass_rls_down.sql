-- Migration 0010 (down): remove Assume Company Context RLS policies on break_glass_access.

revoke select, insert, update on break_glass_access from authenticated;

drop policy if exists break_glass_insert_own on break_glass_access;
drop policy if exists break_glass_select_own on break_glass_access;
drop policy if exists break_glass_update_own_revoke on break_glass_access;
