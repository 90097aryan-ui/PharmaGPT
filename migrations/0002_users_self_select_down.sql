-- Migration 0002 (down): remove the self-select policy on users.

drop policy if exists users_select_own on users;
